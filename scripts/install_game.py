#!/usr/bin/env python3
"""Install the selected user-provided game archive without running its setup EXE.

ModDP250 Setup.exe contains a ZIP SFX payload which zipfile can safely unpack.
Keep TGLL and ModDP250 in separate directories for quick rollback.
"""
from __future__ import annotations

import os
from pathlib import Path, PurePosixPath
import shutil
import stat
import tempfile
import zipfile

from game_profiles import ROOT, current_game, selected_key

MAX_UNPACKED = 400 * 1024 * 1024
MAX_MEMBERS = 6000
MAX_MEMBER = 150 * 1024 * 1024


def say(message):
    print(message, flush=True)


def source_archive(key):
    if key == "tgll":
        candidates = [ROOT / "TGLL_minCPU_v2.zip", ROOT / "game.zip"]
    else:
        candidates = [
            ROOT / "ModDP250_game.zip",
            ROOT / "game-moddp250.zip",
            ROOT / "(PC) ModDp250_Setup(1).exe",
            ROOT / "(PC) ModDp250_Setup.exe",
            ROOT / "ModDp250_Setup.exe",
        ]
        candidates += sorted(
            path for path in ROOT.iterdir()
            if path.is_file()
            and path.suffix.lower() in (".exe", ".zip")
            and "moddp250" in path.name.lower()
            and path not in candidates
        )
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    if key == "moddp250":
        raise FileNotFoundError(
            "Upload (PC) ModDp250_Setup(1).exe to /home/container, then run setup game"
        )
    raise FileNotFoundError("Upload TGLL_minCPU_v2.zip to /home/container")


def validate_archive(archive, required):
    infos = archive.infolist()
    if not infos or len(infos) > MAX_MEMBERS:
        raise ValueError("Unexpected archive entry count")
    total = 0
    names = set()
    for info in infos:
        path = PurePosixPath(info.filename)
        if (not info.filename or path.is_absolute()
            or ".." in path.parts or "\\" in info.filename
            or ":" in info.filename or not path.parts):
            raise ValueError("Unsafe archive entry: " + info.filename)
        if stat.S_IFMT(info.external_attr >> 16) == stat.S_IFLNK:
            raise ValueError("Archive symlinks are not allowed")
        if not info.is_dir():
            total += info.file_size
            if info.file_size > MAX_MEMBER or total > MAX_UNPACKED:
                raise ValueError("Archive content exceeds safe size limit")
            if info.filename in names:
                raise ValueError("Duplicate archive entry: " + info.filename)
            names.add(info.filename)
    for path in required:
        if path not in names:
            raise ValueError("Game archive missing file: " + path)
    say(f"Validated {len(infos)} entries, {total / 1024**2:.1f} MiB unpacked")
    return infos


def main():
    game = current_game()
    key = selected_key()
    destination = ROOT / game["directory"]
    required = (
        game["exe"], "UnityPlayer.dll", "GameAssembly.dll",
        game["data"] + "/boot.config",
    )
    if (destination / game["exe"]).is_file():
        say(f"{game['name']} already installed at {destination}; nothing overwritten")
        return
    if destination.exists():
        raise RuntimeError(f"Directory exists without game executable: {destination}")
    source = source_archive(key)
    say(f"Installing {game['name']} from {source}")
    with zipfile.ZipFile(source, "r") as archive:
        entries = validate_archive(archive, required)
        with tempfile.TemporaryDirectory(prefix=".game-install-", dir=ROOT) as tmp:
            stage = Path(tmp) / "game"
            stage.mkdir()
            for entry in entries:
                dest = stage.joinpath(*PurePosixPath(entry.filename).parts)
                if entry.is_dir():
                    dest.mkdir(parents=True, exist_ok=True)
                else:
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    with archive.open(entry, "r") as stream, dest.open("wb") as writer:
                        shutil.copyfileobj(stream, writer, length=1024 * 1024)
            for name in required:
                if not (stage / name).is_file():
                    raise RuntimeError(f"Extraction incomplete: {name}")
            os.replace(stage, destination)
    say(f"SUCCESS: {game['name']} installed at {destination}")
    say("Archive retained. Run 'start' or 'setup test-game'. No Windows setup was run.")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        say(f"FAILED: {type(error).__name__}: {error}")
        raise SystemExit(1)
