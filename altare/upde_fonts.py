#!/usr/bin/env python3
"""Repair Unicode fonts for TiênnVo Up Đệ Mono and native .NET Wine prefixes.

Only touches the two dedicated Up Đệ prefixes, not other games, account data
or the QLTK binary. Can be safely rerun after .NET installation completes.
"""
from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import sys

from native_setup import ROOT, RUNTIME, PKGROOT, environment, install_packages
from qltk_fonts import FONT_FILES, config_xml

sys.path.insert(0, str(ROOT / "scripts"))
from game_profiles import selected_key

WINE = RUNTIME / "wine/bin/wine"
SOURCE_FONTS = PKGROOT / "usr/share/fonts/truetype/dejavu"
FONT_CONFIG = RUNTIME / "altare-amd64/upde-fontconfig.xml"
WINE_FONT_KEY = r"HKCU\Software\Wine\Fonts\Replacements"
FONT_REPLACEMENTS = ("Segoe UI", "Microsoft Sans Serif")
PREFIXES = (
    RUNTIME / "altare-wineprefix-upde",
    RUNTIME / "altare-wineprefix-upde-netfx",
)


def say(message: str) -> None:
    print("[upde-fonts] " + message, flush=True)


def available_prefixes() -> list[Path]:
    """Only modify initialized Up Đệ prefixes; never create a new Wine prefix."""
    return [prefix for prefix in PREFIXES
            if (prefix / "system.reg").is_file() and (prefix / "user.reg").is_file()]


def repair_prefix(prefix: Path) -> None:
    if prefix not in PREFIXES:
        raise ValueError("Refusing to modify a Wine prefix outside Up Đệ")
    fonts_dir = prefix / "drive_c/windows/Fonts"
    fonts_dir.mkdir(parents=True, exist_ok=True)
    for filename in FONT_FILES:
        source = SOURCE_FONTS / filename
        if not source.is_file():
            raise RuntimeError("Missing Debian DejaVu Unicode font: " + filename)
        dest = fonts_dir / filename
        if not dest.is_file() or dest.stat().st_size != source.stat().st_size:
            shutil.copy2(source, dest)
    env = environment()
    env.update({
        "WINEPREFIX": str(prefix),
        "WINEARCH": "win64",
        "WINEDEBUG": "-all",
        "WINEESYNC": "0",
        "WINEFSYNC": "0",
        "FONTCONFIG_FILE": str(FONT_CONFIG),
    })
    for family in FONT_REPLACEMENTS:
        command = [str(WINE), "reg", "add", WINE_FONT_KEY,
                   "/v", family, "/t", "REG_SZ", "/d", "DejaVu Sans", "/f"]
        result = subprocess.run(command, env=env, cwd=ROOT,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                text=True, timeout=90, check=False)
        if result.returncode:
            raise RuntimeError(f"Wine font mapping failed in {prefix.name} for "
                               f"{family}: {result.stdout[-1200:]}")
    say(prefix.name + ": DejaVu Unicode + Wine font aliases installed")


def install() -> None:
    if selected_key() != "upde":
        raise RuntimeError("Run game-select upde first")
    if not WINE.is_file():
        raise RuntimeError("Run setup native first")
    targets = available_prefixes()
    if not targets:
        raise RuntimeError("No initialized Up Đệ prefix; run setup game first")
    if not all((SOURCE_FONTS / filename).is_file() for filename in FONT_FILES):
        say("Installing Debian DejaVu core fonts without root")
        install_packages(extra_packages=("fonts-dejavu-core",))
    FONT_CONFIG.parent.mkdir(parents=True, exist_ok=True)
    temp = FONT_CONFIG.with_suffix(".tmp")
    try:
        temp.write_text(config_xml(SOURCE_FONTS), encoding="utf-8")
        os.replace(temp, FONT_CONFIG)
    finally:
        temp.unlink(missing_ok=True)
    for prefix in targets:
        repair_prefix(prefix)
    say(f"SUCCESS: repaired fonts in {len(targets)} Up Đệ prefix(es); restart QLTK")
    say("Custom Guna UI glyphs may still require their original font")


if __name__ == "__main__":
    try:
        install()
    except Exception as error:
        say("FAILED: " + str(error))
        raise SystemExit(1)
