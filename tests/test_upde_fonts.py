"""Offline regression tests for Up Đệ font repair; never run Wine."""
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "altare"))
sys.path.insert(0, str(ROOT / "scripts"))

import upde_fonts


class UpdeFontTests(unittest.TestCase):
    def test_only_initialized_upde_prefixes_are_modified(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            mono = root / "altare-wineprefix-upde"
            netfx = root / "altare-wineprefix-upde-netfx"
            unrelated = root / "altare-wineprefix-tiennvo"
            for prefix in (mono, netfx, unrelated):
                prefix.mkdir(parents=True)
                for name in ("system.reg", "user.reg"):
                    (prefix / name).write_text("test")
            source = root / "fonts"
            source.mkdir()
            for name in upde_fonts.FONT_FILES:
                (source / name).write_bytes(b"font-bytes")
            wine = root / "wine"
            wine.write_bytes(b"mock-wine")
            config = root / "fontconfig.xml"
            with (patch.object(upde_fonts, "PREFIXES", (mono, netfx)),
                  patch.object(upde_fonts, "SOURCE_FONTS", source),
                  patch.object(upde_fonts, "WINE", wine),
                  patch.object(upde_fonts, "FONT_CONFIG", config),
                  patch.object(upde_fonts, "ROOT", root),
                  patch.object(upde_fonts, "environment", return_value={}),
                  patch.object(upde_fonts, "selected_key", return_value="upde"),
                  patch.object(upde_fonts, "install_packages") as package_install,
                  patch.object(upde_fonts.subprocess, "run",
                               return_value=subprocess.CompletedProcess([], 0, "OK")) as run):
                self.assertEqual(upde_fonts.available_prefixes(), [mono, netfx])
                upde_fonts.install()
                package_install.assert_not_called()
                self.assertEqual(run.call_count, 4)
                self.assertTrue(config.is_file())
                for prefix in (mono, netfx):
                    self.assertTrue((prefix / "drive_c/windows/Fonts/DejaVuSans.ttf").is_file())
                self.assertFalse((unrelated / "drive_c/windows/Fonts").exists())
                families = [call.args[0][5] for call in run.call_args_list]
                self.assertEqual(families, ["Segoe UI", "Microsoft Sans Serif"] * 2)
                for call in run.call_args_list:
                    self.assertIn(call.kwargs["env"]["WINEPREFIX"], (str(mono), str(netfx)))
                upde_fonts.install()   # safe idempotent rerun
                self.assertEqual(run.call_count, 8)

    def test_refuses_other_prefix(self):
        with self.assertRaisesRegex(ValueError, "outside Up Đệ"):
            upde_fonts.repair_prefix(Path("/tmp/foreign-prefix"))

    def test_uninitialized_prefix_is_not_created(self):
        with tempfile.TemporaryDirectory() as tmp:
            mono = Path(tmp) / "altare-wineprefix-upde"
            mono.mkdir()
            with patch.object(upde_fonts, "PREFIXES", (mono,)):
                self.assertEqual(upde_fonts.available_prefixes(), [])
                self.assertFalse((mono / "drive_c").exists())


if __name__ == "__main__":
    unittest.main()
