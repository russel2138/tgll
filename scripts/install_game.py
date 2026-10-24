#!/usr/bin/env python3
"""Install the user-uploaded TGLL ZIP into a private game directory.

No remote download, no modification to the executable, no root privileges.
"""
from __future__ import annotations

import os
from pathlib import Path, PurePosixPath
import shutil
import stat
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parent.parent
GAME = ROOT / "game"
REQUIRED = (
    "TheGioiLangLa.exe",
    "UnityPlayer.dll",
    "GameAssembly.dll",
    "TheGioiLangLa_Data/boot.config",
)
MAX_UNPACKED = 400 * 1024 * 1024
MAX_MEMBERS = 6000
MAX_MEMBER = 150 * 1024 * 1024


def say(message):
    print(message, flush=True)


def find_zip():
    candidates = [ROOT / "TGLL_minCPU_v2.zip", ROOT / "game.zip"]
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    raise FileNotFoundError(
        "Upload TGLL_minCPU_v2.zip (or game.zip) to /home/container using File Manager"
    )


def validate_archive(archive):
    infos = archive.infolist()
    if not infos or len(infos) > MAX_MEMBERS:
        raise ValueError("Unexpected number of ZIP entries")
    total = 0
    names = set()
    for info in infos:
        path = PurePosixPath(info.filename)
        if (not info.filename or path.is_absolute()
            or ".." in path.parts or "\\" in info.filename
            or ":" in info.filename or not path.parts):
            raise ValueError("Unsafe ZIP entry: " + info.filename)
        if (info.external_attr >> 16) & stat.S_IFMT == stat.S_IFLNK:
            raise ValueError("ZIP symbolic link not allowed: " + info.filename)
        if not info.is_dir():
            total += info.file_size
            if info.file_size > MAX_MEMBER or total > MAX_UNPACKED:
                raise ValueError("ZIP content exceeds safe size limit")
            if info.filename in names:
                raise ValueError("Duplicate ZIP entry: " + info.filename)
            names.add(info.filename)
    for required in REQUIRED:
        if required not in names:
            raise ValueError(f"ZIP does not contain required file: {required}")
    say(f"Validated {len(infos)} ZIP entries; uncompressed size {total / 1024**2:.1f} MiB")
    return infos


def main():
    if (GAME / "TheGioiLangLa.exe").is_file():
        say(f"Game is already installed at {GAME}; nothing overwritten")
        return
    if GAME.exists():
        raise RuntimeError(f"{GAME} exists but does not contain the expected executable")
    source = find_zip()
    say(f"Installing from local upload: {source}")
    with zipfile.ZipFile(source, "r") as archive:
        entries = validate_archive(archive)
        with tempfile.TemporaryDirectory(prefix=".tgll-game-", dir=ROOT) as tmp:
            stage = Path(tmp) / "game"
            stage.mkdir()
            for item in entries:
                path = stage.joinpath(*PurePosixPath(item.filename).parts)
                if item.is_dir():
                    path.mkdir(parents=True, exist_ok=True)
                else:
                    path.parent.mkdir(parents=True, exist_ok=True)
                    with archive.open(item, "r") as src, path.open("wb") as dst:
                        shutil.copyfileobj(src, dst, length=1024 * 1024)
            for required in REQUIRED:
                if not (stage / required).is_file():
                    raise RuntimeError("Extraction incomplete: " + required)
            os.replace(stage, GAME)
    say(f"SUCCESS: TGLL game extracted to {GAME}")
    say("ZIP retained; test with 'test-game'. No executable was launched.")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        say(f"FAILED: {type(error).__name__}: {error}")
        raise SystemExit(1)
