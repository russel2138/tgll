#!/usr/bin/env python3
"""Install the user-supplied TiênnVo Up Đệ Basic archive on Altare.

Downloads a pinned, SHA256-verified archive from the user's GitHub repository
if not present locally. Extracts only data (never executes the installer/game).
Creates a SEPARATE Wine prefix and installs Wine Mono for 32-bit .NET QLTK.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from shutil import copyfileobj, copy2
import sys
import tempfile
from urllib.request import Request, urlopen
import zipfile

from native_setup import ROOT, RUNTIME, BIN_XVFB, install_packages, PKGROOT

sys.path.insert(0, str(ROOT / "scripts"))
from game_profiles import PROFILES, selected_key
from install_game import validate_archive
from qltk_setup import install_mono_at
from qltk_fonts import FONT_FILES, config_xml

ZIP_NAME = "[TiennVo.Net]Tool Up De Basic.zip"
SOURCE = ROOT / ZIP_NAME
WINE = RUNTIME / "wine/bin/wine"
PINNED_COMMIT = "f45aebcf084676b07333861eda6392b8c01199ab"
SOURCE_URL = ("https://raw.githubusercontent.com/russel2138/tgll/" +
              PINNED_COMMIT + "/%5BTiennVo.Net%5DTool%20Up%20De%20Basic.zip")
SOURCE_SHA256 = "b7bb0302e4a0d7dce961a17538eb2b752319c4eb0ce4ef23bff1c8c822cb5901"
SOURCE_BYTES = 60914358
PROFILE = PROFILES["upde"]
DEST = ROOT / PROFILE["directory"]
PREFIX = RUNTIME / ("altare-" + PROFILE["wineprefix"])
QLTK_SETTINGS = RUNTIME / "upde-qltk.json"
FONTS_CONFIG = RUNTIME / "altare-amd64/upde-fontconfig.xml"
SOURCE_FONTS = PKGROOT / "usr/share/fonts/truetype/dejavu"
TARGET_FONTS = PREFIX / "drive_c/windows/Fonts"
REQUIRED = (
    "QLTK.exe",
    "QLTK.exe.config",
    "DragonBoy166.exe",
    "DragonBoy166_Data/Managed/Assembly-CSharp.dll",
    "DragonBoy166_Data/Managed/UnityEngine.dll",
    "Run/Dragonboy_vn_v229.exe",
    "Run/Dragonboy_vn_v229_Data/Managed/Assembly-CSharp.dll",
)


def say(message: str) -> None:
    print("[upde] " + str(message), flush=True)


def sha256(filename: Path) -> str:
    digest = hashlib.sha256()
    with filename.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def check_archive(filename: Path) -> None:
    if filename.stat().st_size != SOURCE_BYTES or sha256(filename) != SOURCE_SHA256:
        raise RuntimeError("Up Đệ archive differs from the inspected GitHub commit; refusing install")
    with zipfile.ZipFile(filename) as archive:
        members = validate_archive(archive, REQUIRED)
        if any(item.flag_bits & 1 for item in members):
            raise RuntimeError("Unexpected encrypted entries in Up Đệ archive")


def obtain_archive() -> Path:
    if SOURCE.is_file():
        check_archive(SOURCE)
        say("Using verified local ZIP")
        return SOURCE
    say("Downloading ZIP from pinned user GitHub commit (about 61 MB)")
    RUNTIME.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(prefix=".upde-", suffix=".zip", dir=ROOT,
                                     delete=False) as staging:
        tmp = Path(staging.name)
        try:
            request = Request(SOURCE_URL, headers={"User-Agent": "Altare-UpDe/1.0"})
            with urlopen(request, timeout=90) as response:
                if not response.geturl().startswith("https://"):
                    raise RuntimeError("ZIP download redirected outside HTTPS")
                count = 0
                while True:
                    chunk = response.read(1024 * 1024)
                    if not chunk:
                        break
                    count += len(chunk)
                    if count > SOURCE_BYTES:
                        raise RuntimeError("Downloaded ZIP exceeds expected size")
                    staging.write(chunk)
            if tmp.stat().st_size != SOURCE_BYTES:
                raise RuntimeError("Incomplete Up Đệ ZIP download")
            check_archive(tmp)
            os.replace(tmp, SOURCE)
        finally:
            tmp.unlink(missing_ok=True)
    say("Verified SHA256 " + SOURCE_SHA256[:16] + "...; cached archive")
    return SOURCE


def extract_archive(archive_path: Path) -> None:
    if DEST.is_dir() and all((DEST / item).is_file() for item in REQUIRED):
        say("Game already installed; preserving accounts and settings")
        return
    if DEST.exists():
        raise RuntimeError("Incomplete game-upde directory exists; inspect it before retrying")
    with zipfile.ZipFile(archive_path) as archive:
        infos = validate_archive(archive, REQUIRED)
        with tempfile.TemporaryDirectory(prefix=".upde-stage-", dir=ROOT) as folder:
            staging = Path(folder) / "game-upde"
            staging.mkdir()
            for info in infos:
                destination = staging.joinpath(*info.filename.split("/"))
                if info.is_dir():
                    destination.mkdir(parents=True, exist_ok=True)
                    continue
                destination.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(info, "r") as src, destination.open("wb") as dest:
                    copyfileobj(src, dest, length=1024 * 1024)
            if not all((staging / item).is_file() for item in REQUIRED):
                raise RuntimeError("Unpacked Up Đệ payload incomplete")
            os.replace(staging, DEST)
    say("Extracted both 32-bit Unity clients and QLTK; no EXE executed")


def ensure_unicode_fonts() -> None:
    if not all((SOURCE_FONTS / name).is_file() for name in FONT_FILES):
        install_packages(extra_packages=("fonts-dejavu-core",))
    TARGET_FONTS.mkdir(parents=True, exist_ok=True)
    for name in FONT_FILES:
        src = SOURCE_FONTS / name
        if not src.is_file():
            raise RuntimeError("Missing Unicode font: " + name)
        dst = TARGET_FONTS / name
        if not dst.is_file():
            copy2(src, dst)
    FONTS_CONFIG.parent.mkdir(parents=True, exist_ok=True)
    tmp = FONTS_CONFIG.with_suffix(".tmp")
    try:
        tmp.write_text(config_xml(SOURCE_FONTS), encoding="utf-8")
        os.replace(tmp, FONTS_CONFIG)
    finally:
        tmp.unlink(missing_ok=True)
    say("DejaVu Unicode fonts available for the separate Up Đệ Wine prefix")


def main() -> None:
    if selected_key() != "upde":
        raise RuntimeError("Use game-select upde before setup game")
    if not WINE.is_file() or not BIN_XVFB.is_file():
        raise RuntimeError("Run setup native first")
    archive = obtain_archive()
    extract_archive(archive)
    install_mono_at(PREFIX, DEST, "upde")
    ensure_unicode_fonts()
    RUNTIME.mkdir(parents=True, exist_ok=True)
    temp = QLTK_SETTINGS.with_suffix(".tmp")
    try:
        temp.write_text(json.dumps({"enabled": True}), encoding="utf-8")
        temp.chmod(0o600)
        temp.replace(QLTK_SETTINGS)
    finally:
        temp.unlink(missing_ok=True)
    say("SUCCESS: Up Đệ Basic installed, QLTK enabled. Run start, then Login in QLTK.")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        say(f"FAILED: {type(error).__name__}: {error}")
        raise SystemExit(1)
