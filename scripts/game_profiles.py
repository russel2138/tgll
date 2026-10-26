#!/usr/bin/env python3
"""Small shared game selector; switching games never deletes either install."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RUNTIME = ROOT / ".tgll-runtime"
SELECTION_FILE = RUNTIME / "game-selection.json"
DEFAULT_GAME = "moddp250"
PROFILES = {
    "tgll": {
        "name": "TGLL",
        "directory": "game",
        "exe": "TheGioiLangLa.exe",
        "data": "TheGioiLangLa_Data",
        "wineprefix": "wineprefix-test",
    },
    "jar": {
        "name": "Java ME (game.jar)",
        "directory": "jar-game",
        "jar": "game.jar",
    },
    "moddp250": {
        "name": "ModDP250",
        "directory": "game-moddp250",
        "exe": "ModDP250.exe",
        "data": "ModDP250_Data",
        "wineprefix": "wineprefix-moddp250",
    },
}


def selected_key():
    if not SELECTION_FILE.is_file():
        return DEFAULT_GAME
    data = json.loads(SELECTION_FILE.read_text(encoding="utf-8"))
    value = data.get("game")
    if value not in PROFILES:
        raise ValueError("Invalid selected game in .tgll-runtime/game-selection.json")
    return value


def current_game():
    return PROFILES[selected_key()].copy()
