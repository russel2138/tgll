#!/usr/bin/env python3
"""Opt-in, reversible graphics tests for NRO TiennVo on Altare.

No registry modifications and no changes to the supplied EXE. WineD3D
settings are inherited by Unity spawned from QLTK. Unity CLI switches
apply only when the launcher starts the game directly.
"""
from __future__ import annotations

import json
from pathlib import Path

MODES = ("default", "glsl-vkd3d", "bitblt", "glcore", "singlethread")
MANAGER_MODES = frozenset(("default", "glsl-vkd3d"))
MODE_SETTINGS = {
    "default": (None, ()),
    "glsl-vkd3d": ("shader_backend=glsl-vkd3d", ()),
    "bitblt": (None, ("-force-d3d11-bitblt-model",)),
    "glcore": (None, ("-force-glcore",)),
    "singlethread": (None, ("-force-d3d11-singlethreaded",)),
}


def settings_for(mode: str, qltk_enabled: bool) -> tuple[str | None, tuple[str, ...]]:
    if mode not in MODE_SETTINGS:
        raise ValueError("Unsupported TiennVo graphics mode")
    if qltk_enabled and mode not in MANAGER_MODES:
        raise ValueError(
            "This mode needs qltk off: QLTK launches Unity itself and "
            "does not forward Unity flags"
        )
    return MODE_SETTINGS[mode]


def read_mode(file: Path) -> str:
    if not file.is_file():
        return "default"
    payload = json.loads(file.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or not isinstance(payload.get("mode"), str):
        raise ValueError("Invalid TiênnVo graphics settings file")
    mode = payload["mode"]
    if mode not in MODES:
        raise ValueError("Unknown TiênnVo graphics mode")
    return mode


def configure_environment(env: dict, mode: str, qltk_enabled: bool) -> tuple[str, ...]:
    wine_config, unity_args = settings_for(mode, qltk_enabled)
    # A stale variable from the outer service must not unexpectedly override
    # the selected mode; CSMT registry keys remain untouched.
    env.pop("WINE_D3D_CONFIG", None)
    if wine_config:
        env["WINE_D3D_CONFIG"] = wine_config
    return unity_args
