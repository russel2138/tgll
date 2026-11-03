"""Select a separate Wine prefix for TiênnVo Up Đệ QLTK .NET runtime.

The original prefix remains untouched. Runtime selection is explicit and
reversible; no game data or accounts are rewritten.
"""
from __future__ import annotations

import json
from pathlib import Path

FILE_NAME = "upde-runtime.json"
MODES = ("mono", "netfx")


def mode_from_file(runtime: Path) -> str:
    path = runtime / FILE_NAME
    if not path.is_file():
        return "mono"
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or value.get("runtime") not in MODES:
        raise ValueError("Invalid upde-runtime.json (expected mono or netfx)")
    return value["runtime"]


def prefix_for(runtime: Path, profile: dict, key: str) -> Path:
    if key == "upde" and mode_from_file(runtime) == "netfx":
        return runtime / "altare-wineprefix-upde-netfx"
    return runtime / ("altare-" + profile["wineprefix"])


def marker_for(runtime: Path, mode: str) -> Path:
    if mode == "netfx":
        return runtime / "altare-wineprefix-upde-netfx/.netfx48-ok"
    if mode == "mono":
        return runtime / "altare-wineprefix-upde/.wine-mono-11.3.0.ok"
    raise ValueError("Unknown Up Đệ runtime")
