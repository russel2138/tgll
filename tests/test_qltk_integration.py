"""Offline tests: no game EXE is executed, no network is used."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "altare"))
sys.path.insert(0, str(ROOT / "scripts"))

from scripts.game_profiles import PROFILES
import native_run
import qltk_setup
import qltk_fonts
import xml.etree.ElementTree as ET
from scripts.install_game import TIENNVO_QLTK


class QltkIntegrationTest(unittest.TestCase):
    def test_tiennvo_prefix_isolated(self):
        self.assertEqual(qltk_setup.PREFIX.name, "altare-wineprefix-tiennvo")
        self.assertEqual(PROFILES["tiennvo"]["directory"], "game-tiennvo")
        self.assertEqual(len(TIENNVO_QLTK), 7)

    def test_disabled_by_default(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(native_run, "QLTK_SETTINGS", Path(tmp) / "missing.json"):
                with patch.object(native_run, "selected_key", return_value="tiennvo"):
                    self.assertFalse(native_run.qltk_enabled())

    def test_saved_toggle(self):
        with tempfile.TemporaryDirectory() as tmp:
            setting = Path(tmp) / "qltk.json"
            with patch.object(native_run, "QLTK_SETTINGS", setting):
                with patch.object(native_run, "selected_key", return_value="tiennvo"):
                    setting.write_text(json.dumps({"enabled": True}))
                    self.assertTrue(native_run.qltk_enabled())
                    setting.write_text(json.dumps({"enabled": False}))
                    self.assertFalse(native_run.qltk_enabled())
                with patch.object(native_run, "selected_key", return_value="jar"):
                    setting.write_text(json.dumps({"enabled": True}))
                    self.assertFalse(native_run.qltk_enabled())

    def test_reject_unencrypted_or_incomplete_qltk_archive(self):
        with tempfile.TemporaryDirectory() as tmp:
            archive = Path(tmp) / "bad.zip"
            with zipfile.ZipFile(archive, "w") as z:
                z.writestr("MOD_Tiennvo_249.exe", b"MZ")
                for name in TIENNVO_QLTK:
                    z.writestr(name, b"not-encrypted")
            with self.assertRaisesRegex(RuntimeError, "Unexpected encrypted files"):
                qltk_setup.verify_source(archive)


    def test_desktop_separate_from_unity_resolution(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = Path(tmp) / "desktop.json"
            with patch.object(native_run, "QLTK_DISPLAY_SETTINGS", config):
                self.assertEqual(native_run.desktop_dimensions(400, 340, False), (400, 340))
                self.assertEqual(native_run.desktop_dimensions(400, 340, True), (1280, 800))
                config.write_text(json.dumps({"width": 1440, "height": 900}))
                self.assertEqual(native_run.desktop_dimensions(400, 340, True), (1440, 900))
                config.write_text(json.dumps({"width": 800, "height": 600}))
                with self.assertRaises(ValueError):
                    native_run.desktop_dimensions(400, 340, True)

    def test_rootless_font_config(self):
        source = Path("/tmp/Fonts & More")
        config = qltk_fonts.config_xml(source)
        root = ET.fromstring(config)
        self.assertEqual(root.tag, "fontconfig")
        self.assertIn(str(source), [entry.text for entry in root.findall("dir")])
        self.assertIn("DejaVu Sans", config)
        self.assertIn("Tahoma", config)
        self.assertEqual(qltk_fonts.WINEPREFIX.name, "altare-wineprefix-tiennvo")

    def test_rootless_fonts_from_debian_core_only(self):
        self.assertEqual(set(qltk_fonts.FONT_FILES), {
            "DejaVuSans.ttf", "DejaVuSans-Bold.ttf",
            "DejaVuSansMono.ttf", "DejaVuSansMono-Bold.ttf",
        })
        with tempfile.TemporaryDirectory() as tmp:
            basedir = Path(tmp)
            source = basedir / "pkg" / "usr/share/fonts/truetype/dejavu"
            source.mkdir(parents=True)
            for name in qltk_fonts.FONT_FILES:
                (source / name).write_bytes(b"dummy-font-file")
            dest = basedir / "prefix" / "drive_c/windows/Fonts"
            settings = basedir / "tiennvo-fontconfig.xml"
            marker = basedir / "prefix" / ".fonts-ok"
            with (patch.object(qltk_fonts, "SOURCE_FONT_DIR", source),
                  patch.object(qltk_fonts, "WINDOWS_FONTS", dest),
                  patch.object(qltk_fonts, "FONTS_CONFIG", settings),
                  patch.object(qltk_fonts, "FONT_MARKER", marker),
                  patch.object(qltk_fonts, "selected_key", return_value="tiennvo"),
                  patch.object(qltk_fonts, "install_packages") as install_pkg):
                qltk_fonts.install_fonts()
                install_pkg.assert_not_called()
                self.assertTrue(settings.is_file())
                self.assertTrue(marker.is_file())
                self.assertTrue(all((dest / name).is_file() for name in qltk_fonts.FONT_FILES))
                qltk_fonts.install_fonts()
                install_pkg.assert_not_called()

    def test_mono_download_checksum_is_pinned(self):
        self.assertEqual(len(qltk_setup.MONO_SHA256), 64)
        self.assertTrue(all(c in "0123456789abcdef" for c in qltk_setup.MONO_SHA256))
        self.assertTrue(qltk_setup.MONO_URL.startswith("https://github.com/wine-mono/"))
        self.assertEqual(qltk_setup.MONO_SIZE, 83348992)


if __name__ == "__main__":
    unittest.main()
