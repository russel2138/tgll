"""Static integration checks for the user's TiênnVo Up Đệ Basic ZIP.

Do not execute Windows EXEs or open network connections.
"""
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "altare"))
sys.path.insert(0, str(ROOT / "scripts"))
import upde_setup
import native_run
import qltk_setup
from scripts.game_profiles import PROFILES


class UpdeIntegrationTests(unittest.TestCase):
    def test_upde_profile_is_independent(self):
        p = PROFILES["upde"]
        self.assertEqual(p["exe"], "DragonBoy166.exe")
        self.assertEqual(p["manager"], "QLTK.exe")
        self.assertEqual(p["engine"], "unity_mono")
        self.assertNotEqual(p["wineprefix"], PROFILES["tiennvo"]["wineprefix"])
        self.assertEqual(native_run.startup_owner("upde", True), "qltk")
        self.assertEqual(native_run.startup_owner("upde", False), "game")

    def test_complete_zip_and_sha256(self):
        self.assertEqual(upde_setup.SOURCE_BYTES, 60914358)
        self.assertEqual(len(upde_setup.SOURCE_SHA256), 64)
        self.assertTrue(upde_setup.SOURCE_URL.startswith("https://raw.githubusercontent.com/"))
        self.assertIn(upde_setup.PINNED_COMMIT, upde_setup.SOURCE_URL)
        self.assertEqual(upde_setup.sha256(upde_setup.SOURCE), upde_setup.SOURCE_SHA256)
        # Validates safe archive names/links, uncompressed limit, and required files.
        upde_setup.check_archive(upde_setup.SOURCE)

    def test_safe_extraction_keeps_existing_game_files(self):
        import tempfile
        import zipfile
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            archive = root / "example.zip"
            with zipfile.ZipFile(archive, "w") as z:
                z.writestr("QLTK.exe", b"test-qltk")
                z.writestr("DragonBoy166.exe", b"test-game")
                z.writestr("Data/Settings.txt", b"default")
            dest = root / "game-upde"
            with (patch.object(upde_setup, "DEST", dest),
                  patch.object(upde_setup, "ROOT", root),
                  patch.object(upde_setup, "REQUIRED", ("QLTK.exe", "DragonBoy166.exe"))):
                upde_setup.extract_archive(archive)
                self.assertEqual((dest / "DragonBoy166.exe").read_bytes(), b"test-game")
                (dest / "Data/Settings.txt").write_bytes(b"my settings")
                upde_setup.extract_archive(archive)
                self.assertEqual((dest / "Data/Settings.txt").read_bytes(), b"my settings")

    def test_mono_shared_installer_supports_other_prefix(self):
        self.assertTrue(callable(qltk_setup.install_mono_at))
        self.assertEqual(upde_setup.PREFIX.name, "altare-wineprefix-upde")
        self.assertNotEqual(upde_setup.PREFIX, qltk_setup.PREFIX)
        self.assertEqual(upde_setup.QLTK_SETTINGS.name, "upde-qltk.json")


if __name__ == "__main__":
    unittest.main()
