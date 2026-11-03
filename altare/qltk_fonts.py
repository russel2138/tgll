#!/usr/bin/env python3
"""Optional, rootless Unicode fonts for the TiênnVo QLTK WinForms UI.

Only writes inside the private TiênnVo Wine prefix and Altare runtime.
It does not replace system fonts or modify other game Wine prefixes.
"""
from __future__ import annotations

import os
from pathlib import Path
import shutil
import sys
from xml.sax.saxutils import escape

from native_setup import ROOT, RUNTIME, PKGROOT, install_packages

sys.path.insert(0, str(ROOT / "scripts"))
from game_profiles import PROFILES, selected_key

WINEPREFIX = RUNTIME / ("altare-" + PROFILES["tiennvo"]["wineprefix"])
WINDOWS_FONTS = WINEPREFIX / "drive_c/windows/Fonts"
FONTS_CONFIG = RUNTIME / "altare-amd64" / "tiennvo-fontconfig.xml"
FONT_MARKER = WINEPREFIX / ".qltk-unicode-fonts-v1.ok"
SOURCE_FONT_DIR = PKGROOT / "usr/share/fonts/truetype/dejavu"
FONT_FILES = ("DejaVuSans.ttf", "DejaVuSans-Bold.ttf",
              "DejaVuSansMono.ttf", "DejaVuSansCondensed.ttf")
FONT_ALIASES = ("Tahoma", "Arial", "Segoe UI",
                "Microsoft Sans Serif", "MS Sans Serif")


def config_xml(font_dir: Path) -> str:
    """Expose fonts extracted without root; use DejaVu for common UI aliases."""
    family_aliases = "\n".join(
        '  <alias binding="strong"><family>' + escape(family) +
        '</family><prefer><family>DejaVu Sans</family></prefer></alias>'
        for family in FONT_ALIASES
    )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<!DOCTYPE fontconfig SYSTEM "fonts.dtd">\n'
        '<fontconfig>\n'
        '  <include ignore_missing="yes">/etc/fonts/fonts.conf</include>\n'
        '  <dir>' + escape(str(font_dir)) + '</dir>\n'
        + family_aliases + '\n'
        '</fontconfig>\n'
    )


def install_fonts() -> None:
    if selected_key() != "tiennvo":
        raise RuntimeError("Select game-select tiennvo before setting up QLTK fonts")
    if (FONT_MARKER.is_file() and FONTS_CONFIG.is_file() and
        all((WINDOWS_FONTS / filename).is_file() for filename in FONT_FILES)):
        print("[qltk-fonts] Unicode fonts already installed", flush=True)
        return
    if not all((SOURCE_FONT_DIR / filename).is_file() for filename in FONT_FILES):
        print("[qltk-fonts] Installing Debian DejaVu Unicode fonts without root", flush=True)
        install_packages(extra_packages=("fonts-dejavu-core",))
    for name in FONT_FILES:
        if not (SOURCE_FONT_DIR / name).is_file():
            raise RuntimeError("DejaVu font missing after package extraction: " + name)
    WINDOWS_FONTS.mkdir(parents=True, exist_ok=True)
    for name in FONT_FILES:
        dest = WINDOWS_FONTS / name
        if not dest.is_file():
            shutil.copy2(SOURCE_FONT_DIR / name, dest)
    FONTS_CONFIG.parent.mkdir(parents=True, exist_ok=True)
    temp = FONTS_CONFIG.with_suffix(".tmp")
    try:
        temp.write_text(config_xml(SOURCE_FONT_DIR), encoding="utf-8")
        temp.replace(FONTS_CONFIG)
    finally:
        temp.unlink(missing_ok=True)
    FONT_MARKER.parent.mkdir(parents=True, exist_ok=True)
    FONT_MARKER.write_text("DejaVu Sans fonts installed for TiênnVo Wine prefix\n",
                           encoding="utf-8")
    print("[qltk-fonts] Unicode fonts ready; restart the game/QLTK session", flush=True)
    print("[qltk-fonts] Custom glyphs from Guna UI may still need an app-specific font", flush=True)


if __name__ == "__main__":
    try:
        install_fonts()
    except Exception as error:
        print("[qltk-fonts] FAILED: " + str(error), flush=True)
        raise SystemExit(1)
