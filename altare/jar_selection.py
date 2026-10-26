#!/usr/bin/env python3
"""Select Java ME game and MicroEmulator without changing Unity/Wine installs.

Matches russel2138/test naming: 'stock' emulator, game.jar, games/*.jar,
emulators/*.jar. Each non-default emulator/game pair gets an isolated RMS home.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import zipfile

from jar_setup import ROOT, STATE, MICROEMU, GAME, parse_midlet

GAMES = ROOT / "games"
EMULATORS = ROOT / "emulators"
SELECTION = STATE / "jar-selection.json"
DEFAULT = {"emulator": "stock", "game": "game.jar"}
NAME_RE = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.+\-]{0,127}$")
MAX_EMULATOR_SIZE = 40 * 1024 * 1024


def valid_name(value):
    return (isinstance(value, str) and bool(NAME_RE.fullmatch(value))
            and value not in (".", "..") and not value.startswith(".")
            and "/" not in value and "\\" not in value)


def local_jar(folder, filename, max_size):
    if not valid_name(filename) or not filename.lower().endswith(".jar"):
        raise ValueError("Invalid JAR filename: " + str(filename))
    path = folder / filename
    if path.is_symlink() or not path.is_file():
        raise FileNotFoundError("JAR not found: " + str(path))
    if not 0 < path.stat().st_size <= max_size or not zipfile.is_zipfile(path):
        raise ValueError("Invalid JAR or file too large: " + str(path))
    return path


def available(kind):
    if kind == "game":
        files = ["game.jar"] if GAME.is_file() else []
        base = GAMES
    elif kind == "emulator":
        files = ["stock"] if (MICROEMU / "microemulator.jar").is_file() else []
        base = EMULATORS
    else:
        raise ValueError("Invalid JAR category")
    if base.is_dir():
        files.extend(sorted(p.name for p in base.iterdir()
                            if p.is_file() and not p.is_symlink()
                            and p.name.lower().endswith(".jar")
                            and valid_name(p.name)
                            and not (kind == "game" and p.name == "game.jar")))
    return files


def normalize(kind, label):
    if not valid_name(label):
        raise ValueError("Use a simple filename without spaces or paths")
    choices = available(kind)
    if kind == "emulator" and label == "stock":
        return "stock"
    if kind == "game" and label in ("stock", "game.jar"):
        return "game.jar"
    if label in choices:
        return label
    if not label.lower().endswith(".jar") and label + ".jar" in choices:
        return label + ".jar"
    raise ValueError("Unknown " + kind + " '" + label +
                     "'. Upload to " + ("games/" if kind == "game" else "emulators/") +
                     " then type 'list'.")


def resolve(emulator, game):
    e = normalize("emulator", emulator)
    g = normalize("game", game)
    game_path = GAME if g == "game.jar" else local_jar(GAMES, g, 25 * 1024 * 1024)
    if game_path.is_symlink():
        raise ValueError("Symlink games are not supported")
    midlet, manifest = parse_midlet(game_path)
    if e == "stock":
        emu_path = local_jar(MICROEMU, "microemulator.jar", MAX_EMULATOR_SIZE)
    else:
        emu_path = local_jar(EMULATORS, e, MAX_EMULATOR_SIZE)
    with zipfile.ZipFile(emu_path) as z:
        if "org/microemu/app/Main.class" not in z.namelist():
            raise ValueError("Emulator JAR missing org.microemu.app.Main: " + e)
    if e == "stock" and g == "game.jar":
        # Preserve the data directory used by the original Altare JAR launcher.
        home = STATE / "microemu-home"
    else:
        home = STATE / "profiles" / g.removesuffix(".jar") / (
            "stock" if e == "stock" else e.removesuffix(".jar")) / "microemu-home"
    return {
        "emulator": e, "game": g, "emulator_path": emu_path,
        "game_path": game_path, "home": home,
        "midlet": midlet, "manifest": manifest,
    }


def load():
    if not SELECTION.is_file():
        return DEFAULT.copy()
    value = json.loads(SELECTION.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or not valid_name(value.get("emulator")) or not valid_name(value.get("game")):
        raise ValueError("Invalid saved JAR selection; inspect " + str(SELECTION))
    return {"emulator": value["emulator"], "game": value["game"]}


def save(emulator, game):
    selected = resolve(emulator, game)
    STATE.mkdir(parents=True, exist_ok=True)
    if SELECTION.is_symlink():
        raise ValueError("Refusing to overwrite symlink JAR selection")
    target = SELECTION.with_suffix(".tmp")
    try:
        with os.fdopen(os.open(str(target), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600),
                       "w", encoding="utf-8") as stream:
            json.dump({"emulator": selected["emulator"],
                       "game": selected["game"]}, stream, indent=2)
        os.replace(target, SELECTION)
    finally:
        target.unlink(missing_ok=True)
    return selected


def describe():
    selected = load()
    games = available("game")
    emus = available("emulator")
    lines = [
        "Java ME games (upload new JARs to /home/container/games/):",
        *["  " + name + (" [selected]" if selected["game"] == name else "")
          for name in games],
        "Emulators (upload MicroEmulator-compatible JARs to /home/container/emulators/):",
        *["  " + name + (" [selected]" if selected["emulator"] == name else "")
          for name in emus],
        "Current: " + selected["emulator"] + " + " + selected["game"],
        "Commands: jar-select <emulator> <game> (after stop)",
        "          restart <emulator> <game> (switch and restart)",
        "          restart (reuse current selection)",
    ]
    return "\n".join(lines)
