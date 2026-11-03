"""Offline verification of native .NET fallback for Up Đệ QLTK."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import subprocess

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "altare"))
sys.path.insert(0, str(ROOT / "scripts"))
import upde_runtime
import upde_dotnet
from scripts.game_profiles import PROFILES


class UpdeNativeDotnetTests(unittest.TestCase):
    def test_modes_are_isolated_and_rollback_works(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            profile = PROFILES["upde"]
            self.assertEqual(upde_runtime.mode_from_file(root), "mono")
            self.assertEqual(upde_runtime.prefix_for(root, profile, "upde").name,
                             "altare-wineprefix-upde")
            (root / "upde-runtime.json").write_text(json.dumps({"runtime": "netfx"}))
            self.assertEqual(upde_runtime.mode_from_file(root), "netfx")
            self.assertEqual(upde_runtime.prefix_for(root, profile, "upde").name,
                             "altare-wineprefix-upde-netfx")
            self.assertEqual(upde_runtime.prefix_for(root, PROFILES["tiennvo"], "tiennvo").name,
                             "altare-wineprefix-tiennvo")
            (root / "upde-runtime.json").write_text(json.dumps({"runtime": "mono"}))
            self.assertEqual(upde_runtime.prefix_for(root, profile, "upde").name,
                             "altare-wineprefix-upde")
            self.assertEqual(upde_runtime.marker_for(root, "netfx").name, ".netfx48-ok")
            self.assertEqual(upde_runtime.marker_for(root, "mono").name,
                             ".wine-mono-11.3.0.ok")

    def test_invalid_settings_refused(self):
        with tempfile.TemporaryDirectory() as folder:
            file = Path(folder) / "upde-runtime.json"
            for data in ('{"runtime":"random"}', "[]", '{"runtime":null}', "bad"):
                file.write_text(data)
                with self.assertRaises((ValueError, json.JSONDecodeError)):
                    upde_runtime.mode_from_file(Path(folder))

    def test_pinned_winetricks_metadata(self):
        self.assertEqual(len(upde_dotnet.WINETRICKS_COMMIT), 40)
        self.assertEqual(len(upde_dotnet.WINETRICKS_GIT_BLOB), 40)
        self.assertIn(upde_dotnet.WINETRICKS_COMMIT, upde_dotnet.WINETRICKS_URL)
        self.assertEqual(upde_dotnet.git_blob_sha1(b"abc"),
                         "f2ba8f84ab5c1bce84a7b441cb1959cfc7093b7f")
        self.assertTrue(upde_dotnet.WINETRICKS_URL.startswith("https://raw.githubusercontent.com/"))

    def test_dotnet_release_check(self):
        with patch.object(upde_dotnet.subprocess, "run") as run:
            run.return_value = subprocess.CompletedProcess([], 0,
                "    Release    REG_DWORD    0x80eb8", "")
            # 0x80eb8 = 528056, a .NET 4.8 release value.
            self.assertGreaterEqual(upde_dotnet.release_number({}),
                                    upde_dotnet.NETFX_RELEASE)
            command = run.call_args.args[0]
            self.assertEqual(command[1:3], ["reg", "query"])
            run.return_value = subprocess.CompletedProcess([], 1, "", "")
            self.assertIsNone(upde_dotnet.release_number({}))


if __name__ == "__main__":
    unittest.main()
