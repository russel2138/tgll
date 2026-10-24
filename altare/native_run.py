#!/usr/bin/env python3
"""Altare Python Hosting TGLL x86-64: native Wine + private Xvfb/x11vnc."""
from __future__ import annotations

import json
import os
from pathlib import Path
import platform
import signal
import socket
import subprocess
import sys
import time

from native_setup import (
    ROOT, RUNTIME, BIN_XVFB, BIN_VNC, XKB_DATA, PASSWD, SHIM,
    environment,
)

sys.path.insert(0, str(ROOT / "scripts"))
from game_profiles import current_game, selected_key

PROFILE = current_game()
GAME = ROOT / PROFILE["directory"]
EXE = GAME / PROFILE["exe"]
WINE = RUNTIME / "wine/bin/wine"
WINESERVER = RUNTIME / "wine/bin/wineserver"
WINEPREFIX = RUNTIME / ("altare-" + PROFILE["wineprefix"])
SESSION_FILE = RUNTIME / "game-session.json"
VNC_SETTINGS = RUNTIME / "vnc-settings.json"
UNITY_LOG = RUNTIME / ("game-live-" + PROFILE["name"] + "-Player.log")
WINE_LOG = RUNTIME / "game-live-wine.log"
XVFB_LOG = RUNTIME / "game-live-xvfb.log"
VNC_LOG = RUNTIME / "game-live-vnc.log"

STOP = False
CHILDREN = {}

def log(s):
    print("[altare-tgll] " + str(s), flush=True)

def terminate(signum, _frame):
    global STOP
    STOP = True
    log("Graceful stop requested")

def config():
    data = {}
    if VNC_SETTINGS.is_file():
        data = json.loads(VNC_SETTINGS.read_text(encoding="utf-8"))
    port = data.get("port")
    if port is None:
        for key in ("SERVER_PORT", "VNC_PORT", "PORT"):
            value = os.environ.get(key, "")
            if value.isdecimal() and 1024 <= int(value) <= 65535:
                port = int(value)
                break
    port = int(port or 5900)
    if not 1024 <= port <= 65535:
        raise ValueError("Invalid VNC port")
    return data, port, bool(data.get("public", False) or
                            os.environ.get("VNC_PUBLIC") == "1")

def pick_display():
    for d in range(90, 100):
        if not Path(f"/tmp/.X11-unix/X{d}").exists() and not Path(f"/tmp/.X{d}-lock").exists():
            return f":{d}"
    raise RuntimeError("No available X display :90..:99")

def child(name, args, env, logfile, cwd=ROOT):
    with logfile.open("w", encoding="utf-8") as target:
        p = subprocess.Popen(args, cwd=cwd, env=env, stdin=subprocess.DEVNULL,
                             stdout=target, stderr=subprocess.STDOUT,
                             start_new_session=True)
    CHILDREN[name] = p
    log(f"{name} started PID {p.pid}")
    return p

def stop_child(name):
    p = CHILDREN.get(name)
    if p is None or p.poll() is not None:
        return
    try:
        os.killpg(p.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    try:
        p.wait(timeout=5)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(p.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        p.wait(timeout=5)

def await_display(display, p):
    socket_path = Path("/tmp/.X11-unix/X" + display.lstrip(":"))
    for _ in range(70):
        if STOP:
            raise RuntimeError("Stop requested")
        if p.poll() is not None:
            raise RuntimeError("Xvfb failed:\n" + XVFB_LOG.read_text(errors="replace")[-1900:])
        if socket_path.is_socket():
            return
        time.sleep(0.2)
    raise RuntimeError("Xvfb socket was not created:\n" +
                       XVFB_LOG.read_text(errors="replace")[-1900:])

def await_vnc(port, p):
    for _ in range(60):
        if STOP:
            raise RuntimeError("Stop requested")
        if p.poll() is not None:
            raise RuntimeError("x11vnc failed:\n" + VNC_LOG.read_text(errors="replace")[-1900:])
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.3):
                return
        except OSError:
            time.sleep(0.2)
    raise RuntimeError("x11vnc didn't open TCP port " + str(port) +
                       "\n" + VNC_LOG.read_text(errors="replace")[-1900:])

def validate():
    if platform.machine().lower() not in ("x86_64", "amd64"):
        raise RuntimeError("Altare native runner is only for Linux x86_64")
    if selected_key() != "tgll":
        raise RuntimeError("Select TGLL for Altare native test: game-select tgll")
    for path in (BIN_XVFB, BIN_VNC, XKB_DATA / "rules/evdev",
                 SHIM, PASSWD, WINE, WINESERVER, EXE,
                 GAME / "UnityPlayer.dll", GAME / "GameAssembly.dll",
                 GAME / PROFILE["data"] / "boot.config"):
        if not path.is_file():
            raise RuntimeError("Missing " + str(path) +
                               "; run setup native, vnc-password, or setup game")
    if PASSWD.stat().st_mode & 0o077:
        raise RuntimeError("VNC password permissions are not private (expected 0600)")

def main():
    validate()
    settings, port, public = config()
    display = pick_display()
    default_size = (640, 480)
    saved_size = RUNTIME / "game-resolutions.json"
    data = json.loads(saved_size.read_text()) if saved_size.is_file() else {}
    width, height = map(int, data.get("tgll", list(default_size)))
    if not (320 <= width <= 960 and 240 <= height <= 720):
        raise RuntimeError("Resolution out of supported range")
    log(f"Native x86_64 Wine (no Box64): TGLL at {width}x{height}")
    log(f"VNC port={port} bind={'0.0.0.0' if public else '127.0.0.1'}")
    if public:
        log("WARNING: VNC password does not encrypt traffic; use private networking if available")
    WINEPREFIX.mkdir(parents=True, exist_ok=True)
    env_wine = environment(display)
    env_wine["WINEPREFIX"] = str(WINEPREFIX)
    env_wine["WINEARCH"] = "win64"
    env_wine["WINEDEBUG"] = "-all,err+all"
    env_wine["WINEESYNC"] = "0"
    env_wine["WINEFSYNC"] = "0"
    vnc_scale = bool(settings.get("scale", False)) and (width > 640 or height > 480)
    RUNTIME.mkdir(parents=True, exist_ok=True)
    SESSION_FILE.unlink(missing_ok=True)
    try:
        xvfb = child("Xvfb", [
            str(BIN_XVFB), display, "-screen", "0", f"{width}x{height}x24",
            "-nolisten", "tcp", "-noreset", "-xkbdir", str(XKB_DATA)],
            environment(display, for_xvfb=True), XVFB_LOG)
        await_display(display, xvfb)
        vnc_args = [
            str(BIN_VNC), "-norc", "-display", display,
            "-rfbport", str(port),
            "-listen", "0.0.0.0" if public else "127.0.0.1",
            "-no6", "-rfbauth", str(PASSWD),
            "-forever", "-shared", "-ncache", "0", "-deferupdate", "100",
            "-nolookup"]
        if vnc_scale:
            vnc_args += ["-scale", "640x480"]
        vnc = child("VNC", vnc_args, environment(display), VNC_LOG)
        await_vnc(port, vnc)
        args = [str(WINE), str(EXE), "-screen-fullscreen", "0",
                "-screen-width", str(width), "-screen-height", str(height)]
        if os.environ.get("GAME_UNITY_LOG") == "0":
            args.append("-nolog")
        else:
            args += ["-logFile", "Z:" + str(UNITY_LOG).replace("/", "\\")]
        game = child("TGLL", args, env_wine, WINE_LOG, cwd=GAME)
        SESSION_FILE.write_text(json.dumps({
            "display": display, "vnc_port": port, "vnc_public": public,
            "game_resolution": f"{width}x{height}",
            "vnc_resolution": "640x480" if vnc_scale else f"{width}x{height}",
            "game": PROFILE["name"], "game_pid": game.pid, "vnc_pid": vnc.pid,
            "xvfb_pid": xvfb.pid, "cpu_quota": "Altare cgroup (no extra affinity cap)",
            "created": time.strftime("%Y-%m-%d %H:%M:%S"),
        }, indent=2), encoding="utf-8")
        log("Native TGLL session started; connect to Altare VNC endpoint")
        start = time.monotonic()
        while not STOP:
            if game.poll() is not None:
                log(f"Wine process exited with code {game.returncode}")
                log("Wine log tail:\n" + WINE_LOG.read_text(errors="replace")[-1600:])
                break
            if xvfb.poll() is not None or vnc.poll() is not None:
                log("Xvfb or VNC exited; stopping session")
                break
            if int(time.monotonic() - start) % 30 < 2:
                log(f"TGLL uptime {int(time.monotonic() - start)}s")
            time.sleep(2)
    finally:
        log("Stopping TGLL Wine -> wineserver -> VNC -> Xvfb")
        stop_child("TGLL")
        try:
            subprocess.run([str(WINESERVER), "-k"], env=env_wine, timeout=15,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except (OSError, subprocess.TimeoutExpired):
            pass
        stop_child("VNC")
        stop_child("Xvfb")
        SESSION_FILE.unlink(missing_ok=True)
        log("Session stopped; game files and Wine prefix are preserved")

if __name__ == "__main__":
    signal.signal(signal.SIGTERM, terminate)
    signal.signal(signal.SIGINT, terminate)
    try:
        main()
    except Exception as error:
        log(f"FAILED: {type(error).__name__}: {error}")
        raise SystemExit(1)
