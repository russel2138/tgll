#!/usr/bin/env python3
"""Install TiênnVo's encrypted QLTK add-on and a private Wine Mono runtime.

The Unity game is already installed by setup game. This script operates only
on game-tiennvo and its dedicated Wine prefix. It never launches QLTK.exe.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
from urllib.request import Request, urlopen
import zipfile

from native_setup import (ROOT, RUNTIME, PKGROOT, BIN_XVFB, XKB_DATA,
                          SHIM, environment, install_packages)

sys.path.insert(0, str(ROOT / "scripts"))
from game_profiles import selected_key, PROFILES
from install_game import (TIENNVO_QLTK, source_archive, validate_archive)

GAME = ROOT / PROFILES["tiennvo"]["directory"]
PREFIX = RUNTIME / ("altare-" + PROFILES["tiennvo"]["wineprefix"])
WINE = RUNTIME / "wine/bin/wine"
SEVEN_Z = PKGROOT / "usr/bin/7zz"
SETTINGS = RUNTIME / "tiennvo-qltk.json"
MONO_VERSION = "11.3.0"
MONO_MSI = RUNTIME / ("wine-mono-" + MONO_VERSION + "-x86.msi")
MONO_URL = ("https://github.com/wine-mono/wine-mono/releases/download/"
            "wine-mono-" + MONO_VERSION + "/wine-mono-" + MONO_VERSION + "-x86.msi")
MONO_SHA256 = "df2dfc1665c2511882e7cabd56eafd0c0a3d94e5a7e86f969277f6c189d418d3"
MONO_SIZE = 83348992
MONO_MARKER = PREFIX / (".wine-mono-" + MONO_VERSION + ".ok")


def say(message: str) -> None:
    print("[qltk] " + str(message), flush=True)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as inp:
        for chunk in iter(lambda: inp.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_source(archive_path: Path) -> None:
    with zipfile.ZipFile(archive_path) as archive:
        validate_archive(archive, ("MOD_Tiennvo_249.exe", *sorted(TIENNVO_QLTK)))
        encrypted_names = {entry.filename for entry in archive.infolist()
                           if entry.flag_bits & 1}
        if encrypted_names != TIENNVO_QLTK:
            raise RuntimeError("Unexpected encrypted files: only the seven QLTK files are supported")
        for filename in TIENNVO_QLTK:
            info = archive.getinfo(filename)
            if not 0 < info.file_size < 8 * 1024 * 1024:
                raise RuntimeError("Unexpected QLTK file size: " + filename)


def ensure_7zip() -> None:
    if SEVEN_Z.is_file():
        return
    say("Installing Debian 7-Zip to private runtime (root not needed)")
    install_packages(extra_packages=("7zip",))
    if not SEVEN_Z.is_file():
        raise RuntimeError("7zz unavailable after rootless installation")


def unpack_qltk(archive: Path) -> None:
    if all((GAME / filename).is_file() and (GAME / filename).stat().st_size > 0
           for filename in TIENNVO_QLTK):
        say("QLTK files already present; preserving them")
        return
    verify_source(archive)
    ensure_7zip()
    # Extract ONLY the seven known root-level files, into a private temporary
    # directory. Never let 7-Zip write arbitrary paths from a supplied archive.
    with tempfile.TemporaryDirectory(prefix=".qltk-extract-", dir=GAME) as tmp:
        stage = Path(tmp)
        args = [str(SEVEN_Z), "e", str(archive), "-y", "-bso0", "-bsp0",
                "-p123", "-o" + str(stage), *sorted(TIENNVO_QLTK)]
        completed = subprocess.run(args, env=environment(), stdout=subprocess.PIPE,
                                   stderr=subprocess.STDOUT, text=True, timeout=120,
                                   check=False)
        if completed.returncode:
            raise RuntimeError("7-Zip could not decrypt the QLTK files (wrong archive/password?)")
        with zipfile.ZipFile(archive) as z:
            for name in TIENNVO_QLTK:
                source = stage / name
                if not source.is_file() or source.is_symlink():
                    raise RuntimeError("Missing extracted QLTK file: " + name)
                if source.stat().st_size != z.getinfo(name).file_size:
                    raise RuntimeError("QLTK extracted size mismatch: " + name)
        for name in sorted(TIENNVO_QLTK):
            target = GAME / name
            if target.exists():
                say("Keeping existing file " + name)
                continue
            os.replace(stage / name, target)
    say("QLTK.exe and its six dependencies extracted alongside Unity game")


def download_mono() -> None:
    if MONO_MSI.is_file() and MONO_MSI.stat().st_size == MONO_SIZE and sha256(MONO_MSI) == MONO_SHA256:
        say("Verified Wine Mono MSI already cached")
        return
    MONO_MSI.unlink(missing_ok=True)
    tmp = MONO_MSI.with_suffix(".part")
    tmp.unlink(missing_ok=True)
    say("Downloading SHA256-verified Wine Mono " + MONO_VERSION + " (about 80 MiB)")
    try:
        with urlopen(Request(MONO_URL, headers={"User-Agent": "Altare-QLTK/1.0"}),
                     timeout=90) as response, tmp.open("wb") as out:
            if not response.geturl().startswith("https://"):
                raise RuntimeError("Wine Mono download redirected to non-HTTPS URL")
            total = 0
            for block in iter(lambda: response.read(1024 * 1024), b""):
                total += len(block)
                if total > MONO_SIZE:
                    raise RuntimeError("Wine Mono exceeds expected size")
                out.write(block)
        if tmp.stat().st_size != MONO_SIZE or sha256(tmp) != MONO_SHA256:
            raise RuntimeError("Wine Mono SHA256 or size mismatch")
        os.replace(tmp, MONO_MSI)
    finally:
        tmp.unlink(missing_ok=True)


def free_display() -> tuple[int, str]:
    for num in range(90, 100):
        if not Path(f"/tmp/.X11-unix/X{num}").exists() and not Path(f"/tmp/.X{num}-lock").exists():
            return num, ":" + str(num)
    raise RuntimeError("No free X11 display for Mono setup")


def install_mono() -> None:
    if MONO_MARKER.is_file():
        say("Wine Mono was already installed for this TiênnVo prefix")
        return
    download_mono()
    if not BIN_XVFB.is_file() or not SHIM.is_file() or not WINE.is_file():
        raise RuntimeError("Run setup native before setup qltk")
    num, display = free_display()
    env = environment(display)
    env.update({"WINEPREFIX": str(PREFIX), "WINEARCH": "win64",
                "WINEDEBUG": "-all,err+all", "WINEESYNC": "0", "WINEFSYNC": "0"})
    PREFIX.mkdir(parents=True, exist_ok=True)
    log_file = RUNTIME / "qltk-xvfb.log"
    with log_file.open("w", encoding="utf-8") as out:
        xvfb = subprocess.Popen(
            [str(BIN_XVFB), display, "-screen", "0", "800x600x24",
             "-nolisten", "tcp", "-noreset", "-xkbdir", str(XKB_DATA)],
            env=environment(display, for_xvfb=True),
            stdout=out, stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL, start_new_session=True,
        )
    try:
        for _ in range(70):
            if xvfb.poll() is not None:
                raise RuntimeError("Xvfb exited while preparing Wine Mono; see qltk-xvfb.log")
            if Path(f"/tmp/.X11-unix/X{num}").is_socket():
                break
            time.sleep(0.2)
        else:
            raise RuntimeError("Xvfb did not create display for Wine Mono install")
        say("Initializing dedicated Wine prefix (32-bit QLTK via WOW64)")
        init = subprocess.run([str(WINE), "wineboot", "-u"], env=env, cwd=GAME,
                              capture_output=True, text=True, timeout=120, check=False)
        if init.returncode:
            raise RuntimeError("Wine prefix initialization failed: " + init.stderr[-1300:])
        say("Installing Wine Mono .NET compatibility runtime into TiênnVo prefix")
        proc = subprocess.run([str(WINE), "msiexec", "/i", str(MONO_MSI),
                               "/qn", "/norestart"], env=env, cwd=GAME,
                              capture_output=True, text=True, timeout=240, check=False)
        if proc.returncode:
            raise RuntimeError("Wine Mono installer returned code " + str(proc.returncode) +
                               ": " + proc.stderr[-1200:])
        MONO_MARKER.write_text(MONO_SHA256 + "\n", encoding="utf-8")
        say("Wine Mono MSI installed successfully (does not prove QLTK compatibility)")
    finally:
        if xvfb.poll() is None:
            xvfb.terminate()
            try:
                xvfb.wait(timeout=5)
            except subprocess.TimeoutExpired:
                xvfb.kill()
                xvfb.wait()


def main() -> None:
    if selected_key() != "tiennvo":
        raise RuntimeError("Select game-select tiennvo before setup qltk")
    if not (GAME / "MOD_Tiennvo_249.exe").is_file():
        raise RuntimeError("Run setup game before setup qltk")
    if not WINE.is_file() or not BIN_XVFB.is_file():
        raise RuntimeError("Run setup native before setup qltk")
    RUNTIME.mkdir(parents=True, exist_ok=True)
    archive = source_archive("tiennvo")
    verify_source(archive)
    unpack_qltk(archive)
    install_mono()
    temp = SETTINGS.with_suffix(".tmp")
    try:
        temp.write_text(json.dumps({"enabled": True}), encoding="utf-8")
        temp.chmod(0o600)
        temp.replace(SETTINGS)
    finally:
        temp.unlink(missing_ok=True)
    say("SUCCESS: QLTK installed and enabled; start will open game + QLTK on one display")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        say("FAILED: " + str(exc))
        raise SystemExit(1)
