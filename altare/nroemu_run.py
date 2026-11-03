#!/usr/bin/env python3
"""Run NRO Emulator V2 desktop Java on Linux with TigerVNC (no Wine/J2ME)."""
from __future__ import annotations

import json
import os
from pathlib import Path
import platform
import re
import shutil
import signal
import socket
import subprocess
import sys
import time

from native_setup import ROOT, RUNTIME, XKB_DATA, PASSWD, environment
from jar_setup import JRE
from jar_run import start_display, terminate as stop_tiger, wait_for_tiger_display
from nroemu_setup import TARGET, WORK, MAIN_CLASS

sys.path.insert(0, str(ROOT / "scripts"))
from game_profiles import selected_key

SESSION = RUNTIME / "game-session.json"
SETTINGS = RUNTIME / "vnc-settings.json"
LOG = RUNTIME / "nroemu-game.log"
STOP = False
JAVA_PROCESS = None
DISPLAY_SIZE = "1280x800"


def say(message: str) -> None:
    print("[nroemu] " + str(message), flush=True)


def on_signal(_signal, _frame) -> None:
    global STOP
    STOP = True
    say("Stop requested")


def java_path() -> Path:
    preferred = JRE / "bin/java"
    if preferred.is_file():
        return preferred
    system = shutil.which("java")
    if system:
        return Path(system)
    raise RuntimeError("Java not available. Run setup jar to install Java 17 first")


def java_major(java: Path) -> int:
    result = subprocess.run([str(java), "-version"],
                            env=environment(), text=True, capture_output=True,
                            timeout=15, check=False)
    if result.returncode:
        raise RuntimeError("Java failed to run: " + (result.stderr or result.stdout)[-1000:])
    line = (result.stderr or result.stdout).splitlines()[0]
    match = re.search(r'version "([0-9]+)(?:[._][0-9]+)*', line)
    if not match:
        match = re.search(r'openjdk ([0-9]+)', line, re.I)
    if not match:
        raise RuntimeError("Cannot determine Java runtime version: " + line[:120])
    return int(match.group(1))


def read_vnc() -> tuple[int, bool]:
    cfg = json.loads(SETTINGS.read_text()) if SETTINGS.is_file() else {}
    value = cfg.get("port") or os.environ.get("SERVER_PORT") or os.environ.get("VNC_PORT") or 5900
    port = int(value)
    if not 1024 <= port <= 65535:
        raise ValueError("VNC port must be 1024..65535")
    public = bool(cfg.get("public", False))
    return port, public


def available_display() -> str:
    for value in range(90, 100):
        if not Path(f"/tmp/.X11-unix/X{value}").exists() and not Path(f"/tmp/.X{value}-lock").exists():
            return f":{value}"
    raise RuntimeError("No free VNC X11 display :90..:99")


def stop_java(process: subprocess.Popen | None) -> None:
    if process is None or process.poll() is not None:
        return
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    try:
        process.wait(timeout=6)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait(timeout=6)


def main() -> None:
    global JAVA_PROCESS
    if selected_key() != "nroemu":
        raise RuntimeError("Select game-select nroemu first")
    if platform.machine().lower() not in ("amd64", "x86_64"):
        raise RuntimeError("NRO Emulator V2 Linux mode requires x86_64")
    if not TARGET.is_file():
        raise RuntimeError("JAR missing: run setup game for nroemu")
    if not PASSWD.is_file() or PASSWD.stat().st_mode & 0o077:
        raise RuntimeError("VNC password missing or insecure: run vnc-password")
    if not (XKB_DATA / "rules/evdev").is_file():
        raise RuntimeError("Linux display libraries missing: run setup native")
    java = java_path()
    major = java_major(java)
    if major < 17:
        raise RuntimeError(f"Java {major} is too old; install native Java 17+")
    port, public = read_vnc()
    display = available_display()
    WORK.mkdir(parents=True, exist_ok=True)
    home = WORK / "home"
    cache = WORK / "cache"
    temp = WORK / "tmp"
    for path in (home, cache, temp):
        path.mkdir(parents=True, exist_ok=True)
    env = environment(display)
    env["HOME"] = str(home)
    env["XDG_CACHE_HOME"] = str(cache)
    env["JAVA_TOOL_OPTIONS"] = ""
    env["TMPDIR"] = str(temp)
    # native_setup.environment already sets Mesa llvmpipe. It is a CPU
    # renderer, not a GPU, and performance must be verified on Altare.
    heap_text = os.environ.get("NROEMU_HEAP_MB", "384")
    if not heap_text.isdecimal():
        raise RuntimeError("NROEMU_HEAP_MB must be a number")
    heap_mb = int(heap_text)
    if not 128 <= heap_mb <= 1536:
        raise RuntimeError("NROEMU_HEAP_MB must be 128..1536")
    args = [
        str(java), "-Xms64m", f"-Xmx{heap_mb}m", "-XX:+UseSerialGC",
        "-Dfile.encoding=UTF-8", "-Djava.awt.headless=false",
        "-Djava.io.tmpdir=" + str(temp),
        "-Duser.home=" + str(home),
        "-jar", str(TARGET)
    ]
    say(f"NRO Emulator V2 Linux JAR | Java {major} | heap={heap_mb} MiB")
    say(f"TigerVNC-only {DISPLAY_SIZE} | port={port} | software GL=llvmpipe")
    SESSION.unlink(missing_ok=True)
    try:
        vnc = start_display(display, port, public, geometry=DISPLAY_SIZE)
        with LOG.open("w", encoding="utf-8") as stream:
            JAVA_PROCESS = subprocess.Popen(args, cwd=WORK, env=env,
                                            stdin=subprocess.DEVNULL,
                                            stdout=stream, stderr=subprocess.STDOUT,
                                            start_new_session=True)
        say(f"Desktop Java launched PID {JAVA_PROCESS.pid}; connect TigerVNC")
        SESSION.write_text(json.dumps({
            "game": "NRO Emulator V2 (native Java desktop)",
            "launch_owner": "java",
            "java_version": major,
            "display": display,
            "vnc_port": port, "vnc_public": public,
            "game_resolution": DISPLAY_SIZE, "vnc_resolution": DISPLAY_SIZE,
            "game_pid": JAVA_PROCESS.pid, "vnc_pid": vnc.pid,
            "vnc_backend": "tigervnc", "graphics": "Mesa llvmpipe",
            "created": time.strftime("%Y-%m-%d %H:%M:%S"),
        }, indent=2), encoding="utf-8")
        started = time.monotonic()
        while not STOP:
            if JAVA_PROCESS.poll() is not None:
                say(f"Java desktop exited code {JAVA_PROCESS.returncode}")
                say("Java log tail:\n" + LOG.read_text(errors="replace")[-3000:])
                break
            if vnc.poll() is not None:
                say("TigerVNC exited; see .tgll-runtime/jar-tigervnc.log")
                break
            time.sleep(2)
        say(f"Session duration {int(time.monotonic() - started)}s")
    finally:
        stop_java(JAVA_PROCESS)
        stop_tiger("TigerVNC")
        SESSION.unlink(missing_ok=True)
        say("Stopped Java desktop and TigerVNC; other game data preserved")


if __name__ == "__main__":
    signal.signal(signal.SIGTERM, on_signal)
    signal.signal(signal.SIGINT, on_signal)
    try:
        main()
    except Exception as error:
        say(f"FAILED: {type(error).__name__}: {error}")
        raise SystemExit(1)
