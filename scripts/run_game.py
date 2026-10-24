#!/usr/bin/env python3
"""Persistent low-overhead Unity game session for HidenCloud ARM64.

Owns Xvfb, x11vnc, Wine+Box64, and one private WINEPREFIX. A supervisor keeps
the session alive until game-stop; no desktop environment or GPU emulator.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import platform
import signal
import socket
import subprocess
import time

from game_profiles import current_game, selected_key
from install_display import (
    BIN as XVFB, ROOT, RUNTIME, XKB_DATA,
    build_xkb_shim, ensure_local_socket_dir, env_for_display, probe_x11,
)
from install_graphics_libs import env_for_game_graphics, LIBDIR
from install_vnc import (
    BIN as VNC, PASSWORD_FILE, env_for_vnc,
)

BOX64 = RUNTIME / "box64/bin/box64"
WINE = RUNTIME / "wine/bin/wine"
WINESERVER = RUNTIME / "wine/bin/wineserver"
X64_LIBS = RUNTIME / "x86_64-libs"
PROFILE = current_game()
GAME = ROOT / PROFILE["directory"]
EXE = GAME / PROFILE["exe"]
WINEPREFIX = RUNTIME / PROFILE["wineprefix"]
SESSION_FILE = RUNTIME / "game-session.json"
VNC_SETTINGS = RUNTIME / "vnc-settings.json"
UNITY_LOG = RUNTIME / f"game-live-{PROFILE['name']}-Player.log"
WINE_LOG = RUNTIME / "game-live-wine.log"
XVFB_LOG = RUNTIME / "game-live-xvfb.log"
VNC_LOG = RUNTIME / "game-live-vnc.log"

STOP = False
CHILDREN = {}


def log(message):
    print(message, flush=True)


def terminate(signum, _frame):
    global STOP
    STOP = True
    log(f"Stop requested (signal {signum})")


def cg_value(path):
    try:
        value = (Path("/sys/fs/cgroup") / path).read_text().strip()
        return int(value)
    except (OSError, ValueError):
        return 0


def memory_stats():
    values = {}
    try:
        for line in Path("/sys/fs/cgroup/memory.stat").read_text().splitlines():
            name, count = line.split()
            values[name] = int(count)
    except (OSError, ValueError):
        pass
    current = cg_value("memory.current")
    maximum = cg_value("memory.max")
    anon = values.get("anon", 0)
    cache = values.get("file", 0)
    inactive = values.get("inactive_file", 0)
    working = max(0, current - inactive)
    return current, maximum, anon, cache, inactive, working


def resources():
    current, maximum, anon, cache, inactive, working = memory_stats()
    mb = lambda value: value / (1024 * 1024)
    log("RAM cgroup: "
        f"current {mb(current):.0f} MiB / max {mb(maximum):.0f} MiB, "
        f"anon {mb(anon):.0f}, file {mb(cache):.0f}, "
        f"inactive_file {mb(inactive):.0f}, working_est {mb(working):.0f}")
    if maximum > 0 and working > maximum * 0.92:
        log("WARNING: Working RAM estimate exceeds 92% cap; possible OOM")
    if maximum > 0 and current > maximum * 0.94:
        log("NOTE: total cgroup memory is near limit (includes reclaimable page cache)")


def validate():
    if platform.machine().lower() not in ("aarch64", "arm64"):
        raise RuntimeError("Requires Linux ARM64")
    for path in (XVFB, VNC, BOX64, WINE, EXE, PASSWORD_FILE,
                 LIBDIR / "libEGL.so.1",
                 X64_LIBS / "libgcc_s.so.1",
                 GAME / "UnityPlayer.dll", GAME / "GameAssembly.dll",
                 GAME / PROFILE["data"] / "boot.config"):
        if not path.is_file():
            raise RuntimeError(f"Missing: {path}; install dependencies first")
    if not XKB_DATA.is_dir():
        raise RuntimeError("XKB data missing: run install-display")
    if PASSWORD_FILE.stat().st_mode & 0o077:
        raise RuntimeError("VNC password file permissions must not allow group/other access")


def config():
    values = {}
    if VNC_SETTINGS.is_file():
        values = json.loads(VNC_SETTINGS.read_text(encoding="utf-8"))
    public = bool(values.get("public", False))
    port = values.get("port")
    if port is None:
        for key in ("VNC_PORT", "SERVER_PORT", "PORT"):
            candidate = os.environ.get(key, "")
            if candidate.isdecimal() and 1024 <= int(candidate) < 65536:
                port = int(candidate)
                break
    port = int(port or 5900)
    if not 1024 <= port <= 65535:
        raise ValueError(f"Invalid VNC port {port} (range 1024...65535)")
    if os.environ.get("VNC_PUBLIC", "") == "1":
        public = True
    return public, port


def pick_display():
    for n in range(90, 100):
        if not Path(f"/tmp/.X11-unix/X{n}").exists() and not Path(
            f"/tmp/.X{n}-lock"
        ).exists():
            return f":{n}"
    raise RuntimeError("No free X11 display :90...:99")


def spawn(name, argv, env, log_path, cwd=ROOT):
    stream = log_path.open("w", encoding="utf-8")
    try:
        proc = subprocess.Popen(
            argv, cwd=cwd, env=env, stdin=subprocess.DEVNULL,
            stdout=stream, stderr=subprocess.STDOUT, start_new_session=True,
        )
    finally:
        stream.close()
    CHILDREN[name] = proc
    log(f"{name} started PID {proc.pid}")
    return proc


def terminate_child(name):
    process = CHILDREN.get(name)
    if process is None or process.poll() is not None:
        return
    # Own session, never signal the persistent parent launcher.
    import os as _os
    try:
        _os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    try:
        process.wait(timeout=4)
    except subprocess.TimeoutExpired:
        try:
            _os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait(timeout=4)


def wine_env(base, display):
    env = env_for_game_graphics(base)
    env.pop("LD_PRELOAD", None)
    env.pop("TGLL_XKBCOMP_PATH", None)
    env.update({
        "DISPLAY": display,
        "WINEPREFIX": str(WINEPREFIX),
        "WINEARCH": "win64",
        "WINEDEBUG": "-all,err+all",
        "BOX64_LOG": "0",
        "BOX64_NOBANNER": "1",
        "LIBGL_ALWAYS_SOFTWARE": "1",
        "WINEESYNC": "0", "WINEFSYNC": "0",
        "BOX64_LD_LIBRARY_PATH": str(X64_LIBS) + (
            os.pathsep + env["BOX64_LD_LIBRARY_PATH"]
            if env.get("BOX64_LD_LIBRARY_PATH") else ""
        ),
    })
    return env


def stop_private_wine(env):
    if not WINESERVER.is_file():
        return
    try:
        subprocess.run([str(BOX64), str(WINESERVER), "-k"],
                       env=env, timeout=15, check=False,
                       stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL)
    except (OSError, subprocess.TimeoutExpired):
        pass


def await_listening(port, proc):
    for _ in range(50):
        if STOP:
            raise RuntimeError("Stop requested")
        if proc.poll() is not None:
            raise RuntimeError(f"x11vnc exited early with code {proc.returncode}")
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.4):
                return
        except OSError:
            time.sleep(0.2)
    raise RuntimeError(f"x11vnc did not listen on TCP port {port}")


def main():
    validate()
    ensure_local_socket_dir()
    build_xkb_shim()
    public, port = config()
    display = pick_display()
    # Keep independent resolutions for TGLL and ModDP250. ModDP250's
    # 800x600 UI is clipped by the old 640x480 Xvfb framebuffer.
    default_size = (800, 600) if selected_key() == "moddp250" else (640, 480)
    resolution_file = RUNTIME / "game-resolutions.json"
    if resolution_file.is_file():
        saved = json.loads(resolution_file.read_text(encoding="utf-8"))
        size = saved.get(selected_key(), list(default_size))
    else:
        size = default_size
    width = int(os.environ.get("GAME_WIDTH", size[0]))
    height = int(os.environ.get("GAME_HEIGHT", size[1]))
    if not 320 <= width <= 960 or not 240 <= height <= 720:
        raise ValueError("Game resolution out of supported range 320x240...960x720")
    RUNTIME.mkdir(parents=True, exist_ok=True)
    xenv = env_for_display()
    wenv = wine_env(xenv, display)
    venv = env_for_vnc(xenv)
    venv["DISPLAY"] = display
    start = time.monotonic()
    memory_max = 0
    log(f"Starting {PROFILE['name']} VPS session on Xvfb {display} {width}x{height}x24")
    log("Optimization: shared headless Xvfb, no desktop environment, "
        "no VNC framebuffer cache, suppressed Box64/Wine debug logs")
    log(f"VNC TCP port {port}, bind {'0.0.0.0 (PUBLIC)' if public else '127.0.0.1 (LOCAL ONLY)'}")
    if public:
        log("SECURITY: classic VNC uses weak 8-character authentication, no transport encryption.")
        log("Use an SSH tunnel/private network where possible; never share VNC credentials.")
    if SESSION_FILE.exists():
        SESSION_FILE.unlink()

    try:
        xvfb = spawn("Xvfb", [
            str(XVFB), display, "-screen", "0", f"{width}x{height}x24",
            "-nolisten", "tcp", "-noreset", "-xkbdir", str(XKB_DATA),
        ], xenv, XVFB_LOG)
        for _ in range(60):
            if STOP:
                raise RuntimeError("Stop requested")
            if xvfb.poll() is not None:
                raise RuntimeError(f"Xvfb exited early: {xvfb.returncode}")
            if probe_x11(display):
                break
            time.sleep(0.2)
        else:
            raise RuntimeError("Xvfb X11 socket failed")

        # Render the complete game at its native virtual framebuffer size,
        # but send a smaller 640x480 VNC image for compact remote viewing.
        # x11vnc maps mouse coordinates back to the full X11 display.
        vnc_scale = (PROFILE["name"] == "ModDP250" and
                     (width > 640 or height > 480))
        if VNC_SETTINGS.is_file():
            vnc_scale = bool(json.loads(VNC_SETTINGS.read_text(
                encoding="utf-8")).get("scale", vnc_scale))
        vnc_args = [
            str(VNC), "-norc", "-display", display,
            "-rfbport", str(port),
            "-listen", "0.0.0.0" if public else "127.0.0.1",
            "-no6", "-rfbauth", str(PASSWORD_FILE),
            "-forever", "-shared", "-ncache", "0",
            "-deferupdate", "100", "-nolookup",
        ]
        if vnc_scale:
            vnc_args += ["-scale", "640x480"]
            log(f"VNC output: 640x480 (full game framebuffer: {width}x{height})")
        else:
            log(f"VNC output: {width}x{height} (1:1)")
        vnc = spawn("x11vnc", vnc_args, venv, VNC_LOG)
        await_listening(port, vnc)
        log("VNC server ready; use TigerVNC Viewer with host:port")

        WINEPREFIX.mkdir(parents=True, exist_ok=True)
        exe_args = [
            str(BOX64), str(WINE), str(EXE),
            "-screen-fullscreen", "0",
            "-screen-width", str(width), "-screen-height", str(height),
        ]
        if os.environ.get("GAME_UNITY_LOG", "1") == "0":
            exe_args.append("-nolog")
            log("Unity Player.log disabled for long-term low-I/O operation")
        else:
            exe_args.extend(["-logFile", "Z:" + str(UNITY_LOG).replace("/", "\\")])
        game = spawn(PROFILE["name"], exe_args, wenv, WINE_LOG, GAME)
        SESSION_FILE.write_text(json.dumps({
            "display": display,
            "vnc_port": port,
            "vnc_public": public,
            "game_resolution": f"{width}x{height}",
            "vnc_resolution": "640x480" if vnc_scale else f"{width}x{height}",
            "game": PROFILE["name"],
            "game_pid": game.pid,
            "vnc_pid": vnc.pid,
            "xvfb_pid": xvfb.pid,
            "created": time.strftime("%Y-%m-%d %H:%M:%S"),
        }, indent=2), encoding="utf-8")
        log(f"{PROFILE['name']} running as PID {game.pid}; supervisor persists until game-stop")
        last_sample = -30
        while not STOP:
            now = time.monotonic()
            if game.poll() is not None:
                log(f"{PROFILE['name']} launcher exited (code {game.returncode}); stopping session")
                break
            if xvfb.poll() is not None:
                log("Xvfb exited unexpectedly; stopping session")
                break
            if vnc.poll() is not None:
                log("VNC exited unexpectedly; stopping session")
                break
            if now - start - last_sample >= 30:
                last_sample = now - start
                current = cg_value("memory.current")
                memory_max = max(memory_max, current)
                log(f"Uptime {int(now - start)}s")
                resources()
                if UNITY_LOG.is_file():
                    log(f"Unity log size: {UNITY_LOG.stat().st_size / 1024:.0f} KiB")
            time.sleep(2)
    finally:
        log(f"Stopping {PROFILE['name']} session: Wine -> wineserver -> VNC -> Xvfb")
        terminate_child(PROFILE["name"])
        stop_private_wine(wenv)
        terminate_child("x11vnc")
        terminate_child("Xvfb")
        SESSION_FILE.unlink(missing_ok=True)
        log(f"Peak cgroup RAM observed: {memory_max / 2**20:.0f} MiB")
        resources()
        log(f"{PROFILE['name']} session stopped; files, prefix and VNC credentials preserved")


if __name__ == "__main__":
    signal.signal(signal.SIGTERM, terminate)
    signal.signal(signal.SIGINT, terminate)
    try:
        main()
    except Exception as error:
        log(f"FAILED: {type(error).__name__}: {error}")
        raise SystemExit(1)
