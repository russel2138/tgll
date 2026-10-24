#!/usr/bin/env python3
"""Bounded TGLL launch smoke test (Box64 + Wine + ARM64 Xvfb/llvmpipe).

Starts only the user's uploaded game. Does not automate logins or actions.
Stops after 120 seconds at most, logs Wine/Unity and cgroup memory/CPU.
"""
from __future__ import annotations

import os
from pathlib import Path
import platform
import signal
import subprocess
import time

from install_display import (
    BIN as XVFB, ROOT, RUNTIME, XKB_DATA,
    build_xkb_shim, ensure_local_socket_dir, env_for_display, probe_x11,
)

BOX64 = RUNTIME / "box64" / "bin" / "box64"
WINE = RUNTIME / "wine" / "bin" / "wine"
WINESERVER = RUNTIME / "wine" / "bin" / "wineserver"
X64_LIBS = RUNTIME / "x86_64-libs"
GAME = ROOT / "game"
EXE = GAME / "TheGioiLangLa.exe"
UNITY_LOG = GAME / "Player.log"
WINE_LOG = RUNTIME / "game-wine.log"
WINEPREFIX = RUNTIME / "wineprefix-test"
MAX_TEST_SECONDS = 120


def say(message):
    print(message, flush=True)


def cgroup_number(name):
    try:
        value = (Path("/sys/fs/cgroup") / name).read_text().strip()
        return int(value)
    except (ValueError, OSError):
        return None


def cpu_usage_seconds():
    try:
        for line in (Path("/sys/fs/cgroup/cpu.stat")).read_text().splitlines():
            if line.startswith("usage_usec "):
                return int(line.partition(" ")[2]) / 1e6
    except (OSError, ValueError):
        pass
    return None


def pick_display():
    for n in range(90, 100):
        if not Path(f"/tmp/.X11-unix/X{n}").exists() and not Path(
            f"/tmp/.X{n}-lock"
        ).exists():
            return f":{n}"
    raise RuntimeError("No free Xvfb display :90...:99")


def stop_process(process):
    if process is None or process.poll() is not None:
        return
    # Spawn each process into its own group, never signal the Python launcher.
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait(timeout=5)


def tail_file(path, limit=45):
    if not path.is_file():
        say(f"Log not present: {path}")
        return
    from collections import deque
    with path.open(encoding="utf-8", errors="replace") as stream:
        lines = deque(stream, maxlen=limit)
    for line in lines:
        say(line.rstrip())


def validate_setup():
    if platform.machine().lower() not in ("aarch64", "arm64"):
        raise RuntimeError("The runtime is configured for ARM64 Linux")
    for file in (XVFB, BOX64, WINE, EXE, GAME / "UnityPlayer.dll",
                 GAME / "GameAssembly.dll", GAME / "TheGioiLangLa_Data" / "boot.config"):
        if not file.is_file():
            raise RuntimeError(f"Missing required file: {file}")
    lib = X64_LIBS / "libgcc_s.so.1"
    if not lib.is_file():
        raise RuntimeError("Missing amd64 libgcc; run install-wine first")
    if not XKB_DATA.is_dir():
        raise RuntimeError("XKB data not found; run install-display first")


def make_wine_env(base, display):
    env = base.copy()
    # LD_PRELOAD helper is strictly for Xvfb, never inject it into Box64/Wine.
    env.pop("LD_PRELOAD", None)
    env.pop("TGLL_XKBCOMP_PATH", None)
    env["DISPLAY"] = display
    env["WINEPREFIX"] = str(WINEPREFIX)
    env["WINEARCH"] = "win64"
    env["WINEDEBUG"] = "-all"
    env["BOX64_NOBANNER"] = "1"
    env["BOX64_LD_LIBRARY_PATH"] = str(X64_LIBS) + (
        os.pathsep + env["BOX64_LD_LIBRARY_PATH"]
        if env.get("BOX64_LD_LIBRARY_PATH") else ""
    )
    env["LIBGL_ALWAYS_SOFTWARE"] = "1"
    env["WINEESYNC"] = "0"
    env["WINEFSYNC"] = "0"
    return env


def close_private_wineserver(env):
    if not WINESERVER.is_file():
        return
    try:
        subprocess.run(
            [str(BOX64), str(WINESERVER), "-k"], env=env,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            timeout=12, check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        pass


def main():
    validate_setup()
    RUNTIME.mkdir(parents=True, exist_ok=True)
    ensure_local_socket_dir()
    build_xkb_shim()
    xenv = env_for_display()
    display = pick_display()
    xvfb = None
    wine = None
    wenv = make_wine_env(xenv, display)
    xvfb_log = RUNTIME / "game-xvfb.log"

    say(f"TGLL smoke test: Box64 + Wine + Xvfb {display}")
    say(f"Game executable: {EXE}")
    say(f"Maximum run time: {MAX_TEST_SECONDS}s")
    say("No batchmode/nographics: Unity must initialize a real graphics device")
    say("Resolution: 640x480 windowed; GL software rendering enabled")

    cpu_start = cpu_usage_seconds()
    peak_memory = 0
    started = time.monotonic()
    try:
        with xvfb_log.open("w", encoding="utf-8") as stream:
            xvfb = subprocess.Popen([
                str(XVFB), display, "-screen", "0", "640x480x24",
                "-nolisten", "tcp", "-noreset", "-xkbdir", str(XKB_DATA),
            ], cwd=ROOT, env=xenv, stdin=subprocess.DEVNULL,
                stdout=stream, stderr=subprocess.STDOUT, start_new_session=True)
        for _ in range(45):
            if xvfb.poll() is not None:
                raise RuntimeError("Xvfb stopped: see game-xvfb.log")
            if probe_x11(display):
                break
            time.sleep(0.2)
        else:
            raise RuntimeError("Xvfb was not ready")

        WINEPREFIX.mkdir(parents=True, exist_ok=True)
        # Unity 2022 Standalone Player arguments; log path is relative to game cwd.
        arguments = [
            str(BOX64), str(WINE), str(EXE),
            "-screen-fullscreen", "0",
            "-screen-width", "640", "-screen-height", "480",
            "-logFile", "Player.log",
        ]
        say("Starting TGLL Windows executable through Wine (no login automation)")
        with WINE_LOG.open("w", encoding="utf-8") as stream:
            wine = subprocess.Popen(
                arguments, cwd=GAME, env=wenv, stdin=subprocess.DEVNULL,
                stdout=stream, stderr=subprocess.STDOUT, start_new_session=True,
            )

        while True:
            now = time.monotonic()
            elapsed = now - started
            memory = cgroup_number("memory.current")
            if memory is not None:
                peak_memory = max(peak_memory, memory)
            if elapsed >= MAX_TEST_SECONDS:
                say("TIME LIMIT: stopping test after 120 seconds")
                break
            exitcode = wine.poll()
            if exitcode is not None:
                say(f"Wine launcher process exited with code {exitcode} after {elapsed:.1f}s")
                say("This alone does not confirm whether a Wine child launched")
                break
            if xvfb.poll() is not None:
                say("Xvfb exited unexpectedly during game launch")
                break
            if int(elapsed) % 15 < 2:
                cpu_now = cpu_usage_seconds()
                cpu_delta = (cpu_now - cpu_start) if cpu_now is not None and cpu_start is not None else None
                mem_text = f"{memory / 2**20:.0f} MiB" if memory is not None else "n/a"
                cpu_text = f"{cpu_delta:.1f}s" if cpu_delta is not None else "n/a"
                say(f"Resource sample: elapsed {elapsed:.0f}s, container RAM {mem_text}, CPU time {cpu_text}")
            time.sleep(2)
    finally:
        say("Stopping smoke-test processes...")
        stop_process(wine)
        close_private_wineserver(wenv)
        stop_process(xvfb)
        say(f"Peak observed container RAM: {peak_memory / 2**20:.0f} MiB")
        cpu_end = cpu_usage_seconds()
        if cpu_end is not None and cpu_start is not None:
            say(f"Container CPU time during test: {cpu_end - cpu_start:.1f}s")
        say(f"Wine log: {WINE_LOG}")
        say(f"Xvfb log: {xvfb_log}")
        say(f"Unity player log: {UNITY_LOG}")
        say("--- Wine log tail ---")
        tail_file(WINE_LOG, 30)
        say("--- Unity Player.log tail ---")
        tail_file(UNITY_LOG, 35)
        say("TEST COMPLETE: Review process/Unity logs; game usability not yet established")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        say(f"FAILED: {type(error).__name__}: {error}")
        raise SystemExit(1)
