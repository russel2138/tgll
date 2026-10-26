#!/usr/bin/env python3
"""Altare Java ME supervisor; separate from native_run.py (Wine/Unity)."""
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

from native_setup import (ROOT, RUNTIME, BIN_XVFB, BIN_VNC, XKB_DATA, PASSWD,
                          SHIM, environment)
from jar_setup import (JRE, MICROEMU, GAME, STATE, parse_midlet)
sys.path.insert(0, str(ROOT / "scripts"))
from game_profiles import selected_key

SESSION = RUNTIME / "game-session.json"
SETTINGS = RUNTIME / "vnc-settings.json"
DATA = STATE / "microemu-home"
STOP = False
CHILDREN = {}

def log(s):
    print("[altare-jar] " + str(s), flush=True)

def stop_signal(_signum, _frame):
    global STOP
    STOP = True
    log("Stop requested")

def spawn(name, args, env, logfile):
    with logfile.open("w", encoding="utf-8") as out:
        p = subprocess.Popen(args, cwd=ROOT, env=env,
                             stdout=out, stderr=subprocess.STDOUT,
                             stdin=subprocess.DEVNULL, start_new_session=True)
    CHILDREN[name] = p
    log(f"{name} PID {p.pid}")
    return p

def terminate(name):
    p = CHILDREN.get(name)
    if not p or p.poll() is not None:
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

def wait_for_xvfb(display, p, logfile):
    path = Path("/tmp/.X11-unix/X" + display.lstrip(":"))
    for _ in range(60):
        if STOP or p.poll() is not None:
            break
        if path.is_socket():
            return
        time.sleep(0.2)
    raise RuntimeError("Xvfb unavailable: " + logfile.read_text(errors="replace")[-1800:])

def wait_for_vnc(port, p, logfile):
    for _ in range(60):
        if STOP or p.poll() is not None:
            break
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.25):
                return
        except OSError:
            time.sleep(0.2)
    raise RuntimeError("VNC port unavailable: " + logfile.read_text(errors="replace")[-1800:])

def main():
    if platform.machine().lower() not in ("x86_64", "amd64"):
        raise RuntimeError("Altare Java ME runtime requires Linux x86_64")
    if selected_key() != "jar":
        raise RuntimeError("Select Java ME: game-select jar")
    java = JRE / "bin/java"
    klass, manifest = parse_midlet(GAME)
    for path in (java, MICROEMU / "microemulator.jar", BIN_XVFB, BIN_VNC,
                 XKB_DATA / "rules/evdev", SHIM, PASSWD):
        if not path.is_file():
            raise RuntimeError(f"Missing {path}; run setup jar and vnc-password")
    if PASSWD.stat().st_mode & 0o077:
        raise RuntimeError("VNC password file must have mode 0600")
    if SETTINGS.is_file():
        cfg = json.loads(SETTINGS.read_text(encoding="utf-8"))
    else:
        cfg = {}
    port = cfg.get("port") or os.environ.get("SERVER_PORT") or os.environ.get("VNC_PORT") or "5900"
    port = int(port)
    if not 1024 <= port <= 65535:
        raise RuntimeError("Invalid port")
    public = bool(cfg.get("public", False))
    display = next((f":{i}" for i in range(90, 100)
                    if not Path(f"/tmp/.X11-unix/X{i}").exists()
                    and not Path(f"/tmp/.X{i}-lock").exists()), None)
    if not display:
        raise RuntimeError("No free X11 display :90..:99")
    STATE.mkdir(parents=True, exist_ok=True)
    DATA.mkdir(parents=True, exist_ok=True)
    (DATA / ".microemulator/suite-null").mkdir(parents=True, exist_ok=True)
    jad = STATE / "game-manifest.jad"
    jad.write_text(manifest + "\n", encoding="utf-8")
    heap = int(os.environ.get("JAR_HEAP_MB", "160"))
    if not 32 <= heap <= 512:
        raise RuntimeError("JAR_HEAP_MB must be 32..512")
    rms = os.environ.get("JAR_RMS_MODE", "file").lower()
    if rms not in ("file", "memory"):
        raise RuntimeError("JAR_RMS_MODE must be file or memory")
    env_java = environment(display)
    env_java["HOME"] = str(DATA)
    env_java["JAVA_TOOL_OPTIONS"] = ""
    # Rootless fontconfig can use host config or extracted Debian assets.
    fonts = RUNTIME / "altare-amd64/root/etc/fonts/fonts.conf"
    if fonts.is_file():
        env_java["FONTCONFIG_FILE"] = str(fonts)
    xvfb_log = RUNTIME / "jar-xvfb.log"
    vnc_log = RUNTIME / "jar-vnc.log"
    java_log = RUNTIME / "jar-game.log"
    SESSION.unlink(missing_ok=True)
    log(f"Game: {GAME} | MIDlet: {klass} | heap: {heap} MiB | RMS: {rms}")
    log(f"Display 400x340x16 | VNC {port} ({'public' if public else 'localhost'})")
    try:
        xvfb = spawn("Xvfb", [
            str(BIN_XVFB), display, "-screen", "0", "400x340x16",
            "-nolisten", "tcp", "-noreset", "-xkbdir", str(XKB_DATA)],
            environment(display, for_xvfb=True), xvfb_log)
        wait_for_xvfb(display, xvfb, xvfb_log)
        vnc = spawn("VNC", [
            str(BIN_VNC), "-norc", "-display", display,
            "-rfbport", str(port),
            "-listen", "0.0.0.0" if public else "127.0.0.1",
            "-no6", "-rfbauth", str(PASSWD),
            "-forever", "-shared", "-ncache", "0", "-deferupdate", "100",
            "-nolookup"], environment(display), vnc_log)
        wait_for_vnc(port, vnc, vnc_log)
        cp = ":".join([
            str(MICROEMU / "microemulator.jar"),
            str(MICROEMU / "lib" / "*"),
            str(MICROEMU / "devices" / "*"),
        ])
        java_args = [
            str(java), "-Xms8m", f"-Xmx{heap}m", "-XX:+UseSerialGC",
            "-Djava.awt.headless=false",
            "-Dsun.java2d.opengl=false",
            "-Dsun.java2d.fontpath=" + str(RUNTIME / "altare-amd64/root/usr/share/fonts/truetype/dejavu"),
            "-Duser.home=" + str(DATA),
            "-Dswing.defaultlaf=javax.swing.plaf.nimbus.NimbusLookAndFeel",
            "-cp", cp, "org.microemu.app.Main",
            "--rms", rms, "--resizableDevice", "400", "300",
            "--appclasspath", str(GAME),
            "--propertiesjad", str(jad), "--quit", klass,
        ]
        game = spawn("Java ME game", java_args, env_java, java_log)
        SESSION.write_text(json.dumps({
            "game": "JAR (Java ME)", "display": display, "vnc_port": port,
            "vnc_public": public, "game_resolution": "400x300",
            "vnc_resolution": "400x340", "game_pid": game.pid,
            "vnc_pid": vnc.pid, "xvfb_pid": xvfb.pid,
            "created": time.strftime("%Y-%m-%d %H:%M:%S"),
        }, indent=2), encoding="utf-8")
        start = time.monotonic()
        log("Java ME session launched. Use TigerVNC on allocated TCP port")
        while not STOP:
            if game.poll() is not None:
                log(f"Java process exited code {game.returncode}")
                log("Java log tail:\n" + java_log.read_text(errors="replace")[-2400:])
                break
            if xvfb.poll() is not None or vnc.poll() is not None:
                log("Display or VNC exited")
                break
            time.sleep(2)
        log(f"Java ME session duration {int(time.monotonic() - start)}s")
    finally:
        terminate("Java ME game")
        terminate("VNC")
        terminate("Xvfb")
        SESSION.unlink(missing_ok=True)
        log("Java ME stopped; RMS, TGLL and Wine remain untouched")

if __name__ == "__main__":
    signal.signal(signal.SIGINT, stop_signal)
    signal.signal(signal.SIGTERM, stop_signal)
    try:
        main()
    except Exception as error:
        log(f"FAILED: {type(error).__name__}: {error}")
        raise SystemExit(1)
