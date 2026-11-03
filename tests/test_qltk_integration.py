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
from altare import native_run, qltk_setup
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

    def test_mono_download_checksum_is_pinned(self):
        self.assertEqual(len(qltk_setup.MONO_SHA256), 64)
        self.assertTrue(all(c in "0123456789abcdef" for c in qltk_setup.MONO_SHA256))
        self.assertTrue(qltk_setup.MONO_URL.startswith("https://github.com/wine-mono/"))
        self.assertEqual(qltk_setup.MONO_SIZE, 83348992)


if __name__ == "__main__":
    unittest.main()
