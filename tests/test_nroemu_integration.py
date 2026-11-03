"""Offline integration tests for desktop Java NRO Emulator V2; do not run EXEs."""
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "altare"))
sys.path.insert(0, str(ROOT / "scripts"))
import nroemu_setup
import nroemu_run
from game_profiles import PROFILES


class NROEmulatorV2Tests(unittest.TestCase):
    def test_archived_source_is_immutable(self):
        self.assertEqual(nroemu_setup.ARCHIVE.stat().st_size, 79035404)
        self.assertEqual(nroemu_setup.SOURCE_COMMIT,
                         "01c610bb91c09a23a54e194e92edf602d6f8864f")
        nroemu_setup.verify_archive(nroemu_setup.ARCHIVE)
        self.assertEqual(len(nroemu_setup.SOURCE_SHA256), 64)

    def test_build_linux_jar_from_launch4j(self):
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            exe = folder / "launch4j.exe"
            jar = folder / "nro.jar"
            with ZipFile(nroemu_setup.ARCHIVE) as outer:
                with outer.open("NRO EMULATOR.exe") as source, exe.open("wb") as dest:
                    from shutil import copyfileobj
                    copyfileobj(source, dest)
            nroemu_setup.rebuild_embedded_jar(exe, jar)
            self.assertTrue(jar.is_file())
            with ZipFile(jar) as z:
                self.assertGreater(len(z.namelist()), 3000)
                self.assertEqual(z.testzip(), None)
                manifest = z.read("META-INF/MANIFEST.MF").decode("utf-8","replace")
                self.assertIn("com.dragonboy.desktop.DesktopLauncher", manifest)
                self.assertIn("linux/x64/org/lwjgl/glfw/libglfw.so", z.namelist())
                self.assertIn("libgdx64.so", z.namelist())

    def test_game_profile_does_not_use_wine_or_microemulator(self):
        self.assertEqual(PROFILES["nroemu"]["engine"], "java_desktop")
        self.assertEqual(PROFILES["nroemu"]["jar"], "nro-emulator-v2.jar")
        self.assertNotIn("wineprefix", PROFILES["nroemu"])
        self.assertNotIn("exe", PROFILES["nroemu"])
        self.assertEqual(nroemu_run.DISPLAY_SIZE, "1280x800")

    def test_java_major_parsing_and_heap_guard(self):
        import subprocess
        java=Path("/fake/java")
        with patch.object(nroemu_run.subprocess, "run") as mock:
            mock.return_value = subprocess.CompletedProcess([], 0, "", 'openjdk version "17.0.15"')
            self.assertEqual(nroemu_run.java_major(java), 17)
            mock.return_value = subprocess.CompletedProcess([], 0, "", 'openjdk version "21.0.12.1"')
            self.assertEqual(nroemu_run.java_major(java), 21)
            mock.return_value = subprocess.CompletedProcess([], 0, "", 'java version "1.8.0_451"')
            self.assertEqual(nroemu_run.java_major(java), 1)

    def test_runner_tiger_only(self):
        import inspect
        source = inspect.getsource(nroemu_run.main)
        self.assertIn("start_display(display, port, public", source)
        self.assertNotIn("wine", source.lower())


if __name__ == "__main__":
    unittest.main()
