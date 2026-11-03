#!/usr/bin/env python3
"""Optional, rootless Microsoft .NET Framework 4.8 for Up Đệ QLTK.

Installs into a NEW private Wine prefix. The existing Mono prefix, TiênnVo
game, accounts and VNC settings are not modified. Mode selection is separate.
Winetricks uses vendor-hosted .NET installers and its own checksums.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import time
from urllib.request import Request, urlopen

from native_setup import (ROOT, RUNTIME, PKGROOT, BIN_XVFB, XKB_DATA,
                          environment, install_packages)
from upde_runtime import marker_for

sys.path.insert(0, str(ROOT / "scripts"))
from game_profiles import selected_key, PROFILES

GAME = ROOT / PROFILES["upde"]["directory"]
WINE = RUNTIME / "wine/bin/wine"
WINESERVER = RUNTIME / "wine/bin/wineserver"
PREFIX = RUNTIME / "altare-wineprefix-upde-netfx"
MARKER = marker_for(RUNTIME, "netfx")
RUNNER = RUNTIME / "altare-amd64/winetricks-pinned.sh"
LOG = RUNTIME / "upde-dotnet48-install.log"
CACHE = RUNTIME / "upde-dotnet-download-cache"
WINETRICKS_COMMIT = "f3890f670867b5ffbc3938726db45c0f7d16c8ba"
WINETRICKS_GIT_BLOB = "c166340f33c9af2bcc76a90618fdcf99d90c2253"
WINETRICKS_SIZE = 873846
WINETRICKS_URL = ("https://raw.githubusercontent.com/Winetricks/winetricks/" +
                  WINETRICKS_COMMIT + "/src/winetricks")
NETFX_RELEASE = 528040


def say(message: str) -> None:
    print("[upde-netfx] " + str(message), flush=True)


def git_blob_sha1(raw: bytes) -> str:
    # Matches the immutable GitHub blob for the pinned winetricks source.
    header = ("blob " + str(len(raw)) + "\0").encode("ascii")
    return hashlib.sha1(header + raw).hexdigest()


def fetch_winetricks() -> None:
    if RUNNER.is_file():
        raw = RUNNER.read_bytes()
        if len(raw) == WINETRICKS_SIZE and git_blob_sha1(raw) == WINETRICKS_GIT_BLOB:
            return
    RUNNER.parent.mkdir(parents=True, exist_ok=True)
    say("Downloading verified Winetricks script from pinned upstream Git commit")
    request = Request(WINETRICKS_URL, headers={"User-Agent": "TGLL-UpDe-NetFx/1.0"})
    with urlopen(request, timeout=90) as response:
        if not response.geturl().startswith("https://"):
            raise RuntimeError("Winetricks redirected to non-HTTPS URL")
        raw = response.read(WINETRICKS_SIZE + 1)
    if len(raw) != WINETRICKS_SIZE or git_blob_sha1(raw) != WINETRICKS_GIT_BLOB:
        raise RuntimeError("Winetricks source checksum mismatch; refusing to execute")
    with tempfile.NamedTemporaryFile(dir=RUNNER.parent, prefix=".winetricks-",
                                     delete=False) as file:
        temp = Path(file.name)
        try:
            file.write(raw)
            file.flush()
            temp.chmod(0o700)
            os.replace(temp, RUNNER)
        finally:
            temp.unlink(missing_ok=True)


def find_display() -> tuple[int, str]:
    for number in range(90, 100):
        if not Path(f"/tmp/.X11-unix/X{number}").exists() and not Path(f"/tmp/.X{number}-lock").exists():
            return number, f":{number}"
    raise RuntimeError("No available Xvfb display for .NET installer")


def release_number(env: dict) -> int | None:
    reg_key = r"HKLM\Software\Microsoft\NET Framework Setup\NDP\v4\Full"
    cmd = [str(WINE), "reg", "query", reg_key, "/v", "Release"]
    result = subprocess.run(cmd, env=env, cwd=GAME, capture_output=True,
                            text=True, timeout=45, check=False)
    if result.returncode:
        return None
    match = re.search(r"\bRelease\s+REG_DWORD\s+(0x[0-9a-fA-F]+|\d+)", result.stdout)
    return int(match.group(1), 0) if match else None


def install() -> None:
    if selected_key() != "upde":
        raise RuntimeError("Select game-select upde before setup upde-dotnet")
    if not (GAME / "QLTK.exe").is_file() or not WINE.is_file() or not BIN_XVFB.is_file():
        raise RuntimeError("Run setup game and setup native first")
    if MARKER.is_file():
        say("Microsoft .NET 4.8 already installed in isolated Up Đệ prefix")
        return
    if shutil.disk_usage(ROOT).free < 2 * 1024**3:
        raise RuntimeError("At least 2 GB free disk is recommended for .NET installation")
    # Cabextract and wget are used by Winetricks. Debian packages are fetched
    # through native_setup's SHA256-checked package-index mechanism.
    say("Installing rootless cabextract, unzip and wget helpers")
    install_packages(extra_packages=("cabextract", "libmspack0", "unzip", "wget"))
    fetch_winetricks()
    CACHE.mkdir(parents=True, exist_ok=True)
    PREFIX.mkdir(parents=True, exist_ok=True)
    num, display = find_display()
    env = environment(display)
    env.update({
        "WINE": str(WINE),
        "WINESERVER": str(WINESERVER),
        "WINEPREFIX": str(PREFIX),
        "WINEARCH": "win64",
        "WINEDEBUG": "-all",
        "WINEESYNC": "0",
        "WINEFSYNC": "0",
        "W_CACHE": str(CACHE),
        "WINETRICKS_GUI": "none",
        "LANG": "C.UTF-8",
    })
    with (RUNTIME / "upde-netfx-xvfb.log").open("w", encoding="utf-8") as output:
        xvfb = subprocess.Popen(
            [str(BIN_XVFB), display, "-screen", "0", "1024x768x24",
             "-nolisten", "tcp", "-noreset", "-xkbdir", str(XKB_DATA)],
            env=environment(display, for_xvfb=True),
            stdout=output, stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL, start_new_session=True,
        )
    try:
        for _ in range(70):
            if xvfb.poll() is not None:
                raise RuntimeError("Xvfb exited during .NET setup; see upde-netfx-xvfb.log")
            if Path(f"/tmp/.X11-unix/X{num}").is_socket():
                break
            time.sleep(.2)
        else:
            raise RuntimeError("Xvfb did not start for .NET setup")
        say("Initializing SEPARATE Wine prefix for Microsoft .NET")
        with LOG.open("w", encoding="utf-8") as out:
            init = subprocess.run([str(WINE), "wineboot", "-u"], env=env,
                                  cwd=GAME, stdout=out, stderr=subprocess.STDOUT,
                                  stdin=subprocess.DEVNULL, timeout=150, check=False)
        if init.returncode:
            raise RuntimeError("Initial wineboot failed; inspect " + str(LOG))
        # Winetricks -q automatically removes Wine Mono before adding native
        # Microsoft .NET runtime, only in this new prefix.
        say("Installing Microsoft .NET Framework 4.8 using Winetricks (-q dotnet48)")
        say("Installer output: .tgll-runtime/upde-dotnet48-install.log")
        with LOG.open("a", encoding="utf-8") as out:
            result = subprocess.run(["sh", str(RUNNER), "-q", "dotnet48"],
                                    env=env, cwd=GAME, stdout=out,
                                    stderr=subprocess.STDOUT,
                                    stdin=subprocess.DEVNULL,
                                    timeout=1500, check=False)
        if result.returncode:
            tail = LOG.read_text(errors="replace")[-2200:]
            raise RuntimeError(f"Winetricks exited code {result.returncode}:\n{tail}")
        release = release_number(env)
        if release is None or release < NETFX_RELEASE:
            raise RuntimeError("Installer returned success but native .NET 4.8 Release value "
                               "not found; review upde-dotnet48-install.log")
        MARKER.write_text(f"Microsoft .NET Framework Release={release}\n", encoding="utf-8")
        say(f"SUCCESS: Microsoft .NET Framework 4.8 installed (Release={release})")
        say("Use upde-runtime netfx, then start. Mono prefix is preserved.")
    finally:
        # Keep the partial .NET prefix for log inspection / retry, but do not
        # select it until native .NET passed verification and user opts in.
        if xvfb.poll() is None:
            xvfb.terminate()
            try:
                xvfb.wait(timeout=6)
            except subprocess.TimeoutExpired:
                xvfb.kill()
                xvfb.wait()


if __name__ == "__main__":
    try:
        install()
    except Exception as exc:
        say("FAILED: " + str(exc))
        raise SystemExit(1)
