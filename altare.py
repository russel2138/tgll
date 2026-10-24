#!/usr/bin/env python3
"""Altare Python Hosting bootstrap for the existing TGLL launcher.

This file does not install Wine or start a game on its own. It prints an
architecture/resource preflight, selects TGLL for new installations, and
starts the existing interactive Python launcher.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import platform
import shutil
import sys
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent
STATE = ROOT / ".tgll-runtime"
SELECTED = STATE / "game-selection.json"
APP = ROOT / "app.py"
APP_URL = "https://raw.githubusercontent.com/russel2138/tgll/main/app.py"


def show_preflight():
    arch = platform.machine().lower()
    print(f"[altare] Python {platform.python_version()}, Linux CPU: {arch}", flush=True)
    print(f"[altare] libc: {platform.libc_ver()}; root: {ROOT}", flush=True)
    for path in ("cpu.max", "memory.max"):
        try:
            value = (Path("/sys/fs/cgroup") / path).read_text().strip()
        except OSError:
            value = "unavailable"
        print(f"[altare] cgroup {path}: {value}", flush=True)
    for name in ("python3", "git", "gcc", "g++", "cmake", "dpkg-deb", "Xvfb", "x11vnc", "wine"):
        print(f"[altare] {name}: {shutil.which(name) or 'not installed'}", flush=True)
    ports = []
    for key in ("SERVER_PORT", "PORT", "APP_PORT", "VNC_PORT"):
        value = os.environ.get(key, "")
        if value.isascii() and value.isdecimal() and 0 < int(value) < 65536:
            ports.append(f"{key}={value}")
    print("[altare] port variables: " + (", ".join(ports) if ports else "none detected"), flush=True)
    if arch in ("x86_64", "amd64"):
        print("[altare] x86_64 detected: native amd64 Wine is needed; "
              "DO NOT run ARM64 Box64/Xvfb/VNC installer commands", flush=True)
    elif arch in ("aarch64", "arm64"):
        print("[altare] ARM64 detected: existing Box64/Wine installer may be usable "
              "if libc, utilities, and network access are compatible", flush=True)
    else:
        print("[altare] Unknown CPU architecture; only run setup after compatibility checks", flush=True)


def select_tgll_once():
    if SELECTED.is_file():
        print("[altare] Keeping existing game selection", flush=True)
        return
    STATE.mkdir(parents=True, exist_ok=True)
    temp = SELECTED.with_suffix(".tmp")
    try:
        temp.write_text(json.dumps({"game": "tgll"}), encoding="utf-8")
        temp.chmod(0o600)
        os.replace(temp, SELECTED)
    finally:
        temp.unlink(missing_ok=True)
    print("[altare] New server: TGLL selected (not ModDP250)", flush=True)


def bootstrap_launcher():
    if APP.is_file():
        return
    print("[altare] Fetching existing TGLL Python launcher", flush=True)
    request = Request(APP_URL, headers={"User-Agent": "tgll-altare-bootstrap/1.0"})
    with urlopen(request, timeout=35) as response:
        payload = response.read(2 * 1024 * 1024 + 1)
    if len(payload) > 2 * 1024 * 1024:
        raise RuntimeError("app.py exceeded 2 MiB bootstrap limit")
    compile(payload, "app.py", "exec")
    tmp = APP.with_suffix(".py.tmp")
    try:
        tmp.write_bytes(payload)
        os.replace(tmp, APP)
    finally:
        tmp.unlink(missing_ok=True)


def main():
    show_preflight()
    select_tgll_once()
    bootstrap_launcher()
    print("[altare] First Console commands: update, status, game-select tgll", flush=True)
    print("[altare] Upload your own TGLL_minCPU_v2.zip; "
          "never start game before architecture-specific prerequisites exist", flush=True)
    os.execv(sys.executable, [sys.executable, "-u", str(APP)])


if __name__ == "__main__":
    main()
