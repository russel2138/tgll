#!/usr/bin/env python3
"""Show the configured TGLL VNC endpoint and locally saved login hint."""
from __future__ import annotations

import json
import os
from pathlib import Path

from install_display import RUNTIME

SESSION = RUNTIME / "game-session.json"
SETTINGS = RUNTIME / "vnc-settings.json"
LOCAL_CREDENTIAL = RUNTIME / "vnc" / "password-display.txt"


def load(path):
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def running(pid):
    try:
        value = int(pid)
        if value < 1:
            return False
        stat = Path(f"/proc/{value}/stat").read_text(encoding="ascii")
        return stat.rsplit(")", 1)[-1].strip().split()[0] not in ("Z", "X")
    except (OSError, ValueError, TypeError, IndexError):
        return False


def main():
    session = load(SESSION)
    settings = load(SETTINGS)
    active = running(session.get("game_pid")) and running(session.get("vnc_pid"))
    altare = os.uname().machine.lower() in ("x86_64", "amd64")
    port_fallback = os.environ.get("SERVER_PORT", "5900") if altare else "24663"
    port = session.get("vnc_port") if active else settings.get("port", port_fallback)
    public = bool(session.get("vnc_public")) if active else bool(settings.get("public"))
    host = (os.environ.get("VNC_HOST") or settings.get("host") or
            ("<Altare Network hostname>" if altare else "vicky.hidencloud.com"))
    game = session.get("game") if active else None
    if not game:
        try:
            from game_profiles import selected_key, PROFILES
            game = PROFILES[selected_key()]["name"]
        except (ValueError, KeyError, OSError):
            game = "TGLL"
    print(str(game) + ": " + ("RUNNING" if active else "STOPPED"))
    print("VNC: " + ("RUNNING" if active else "STOPPED"))
    print(f"VNC port: {port} | {'public' if public else 'localhost only'}")
    print(f"TigerVNC connection: {host}::{port}")
    if altare and host == "<Altare Network hostname>":
        print("Use the actual TCP address shown in Altare Network; this placeholder is not a hostname")
    if LOCAL_CREDENTIAL.is_file() and LOCAL_CREDENTIAL.stat().st_mode & 0o077 == 0:
        print("VNC password: " + LOCAL_CREDENTIAL.read_text(encoding="utf-8").strip())
    else:
        print("VNC password: unavailable in local display cache")
        print("Existing VNC auth remains valid. Use vnc-password to generate a new viewable password.")
    if not public:
        print("To connect remotely: vnc-public on " + str(port) + " then game-restart")
    print("Keep password private. VNC connections are not end-to-end encrypted.")


if __name__ == "__main__":
    main()
