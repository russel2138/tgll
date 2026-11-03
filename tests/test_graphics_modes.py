"""Offline tests: WineD3D config applies to QLTK children; Unity flags only direct."""
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "altare"))
from graphics_modes import MODES, MANAGER_MODES, read_mode, configure_environment, settings_for


class GraphicsModesTests(unittest.TestCase):
    def test_default_does_not_override_csmt(self):
        env = {"WINE_D3D_CONFIG": "csmt=0"}
        self.assertEqual(configure_environment(env, "default", True), ())
        self.assertNotIn("WINE_D3D_CONFIG", env)

    def test_qltk_spawn_inherits_wined3d_shader_mode(self):
        env = {"WINEPREFIX": "/tmp/tiennvo"}
        self.assertEqual(configure_environment(env, "glsl-vkd3d", True), ())
        self.assertEqual(env["WINE_D3D_CONFIG"], "shader_backend=glsl-vkd3d")
        self.assertEqual(env["WINEPREFIX"], "/tmp/tiennvo")
        self.assertIn("glsl-vkd3d", MANAGER_MODES)

    def test_unity_flags_direct_only(self):
        expected = {
            "bitblt": ("-force-d3d11-bitblt-model",),
            "glcore": ("-force-glcore",),
            "singlethread": ("-force-d3d11-singlethreaded",),
        }
        for mode, flags in expected.items():
            with self.subTest(mode=mode):
                env = {}
                self.assertEqual(configure_environment(env, mode, False), flags)
                self.assertNotIn("WINE_D3D_CONFIG", env)
                with self.assertRaisesRegex(ValueError, "qltk off"):
                    settings_for(mode, True)

    def test_persisted_mode_validation(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "graphics.json"
            self.assertEqual(read_mode(path), "default")
            for mode in MODES:
                path.write_text(json.dumps({"mode": mode}))
                self.assertEqual(read_mode(path), mode)
            for content in ('{"mode":"csmt-off"}', '{"mode":3}', '[]', 'invalid'):
                path.write_text(content)
                with self.assertRaises(ValueError):
                    read_mode(path)


if __name__ == "__main__":
    unittest.main()
