"""Offline smoke tests for Altare SOCKS5 command support."""
import unittest

from scripts.proxy_launch import parse_proxy, proxychains_config
from scripts.game_profiles import PROFILES


class ProxyOptionsTest(unittest.TestCase):
    def test_no_auth(self):
        p = parse_proxy("1.2.3.4:1080")
        self.assertEqual((p["host"], p["port"], p["username"]), ("1.2.3.4", 1080, ""))

    def test_auth(self):
        p = parse_proxy("proxy.example.com:1080:alice:secret")
        self.assertEqual(p["username"], "alice")
        self.assertEqual(p["password"], "secret")
        conf = proxychains_config(p)
        self.assertIn("socks5 proxy.example.com 1080 alice secret", conf)
        self.assertIn("localnet 127.0.0.0/255.0.0.0", conf)
        self.assertIn("proxy_dns", conf)

    def test_credential_with_colon(self):
        self.assertEqual(parse_proxy("1.2.3.4:80:u:p:w")["password"], "p:w")

    def test_reject_bad_options(self):
        for bad in ("", "host", "host:0", "host:65536", "host:abc",
                    "host:80:user", "host:80::pass", "host:80:user:",
                    "bad host:80", "host:80:u:bad pass", "1.2.3.4:80\n"):
            with self.subTest(bad=bad):
                # A trailing newline is stripped by the interactive console.
                if bad.endswith("\n"):
                    continue
                with self.assertRaises(ValueError):
                    parse_proxy(bad)

    def test_tiennvo_profile(self):
        p = PROFILES["tiennvo"]
        self.assertEqual(p["exe"], "MOD_Tiennvo_249.exe")
        self.assertEqual(p["data"], "MOD_Tiennvo_249_Data")
        self.assertNotEqual(p["wineprefix"], PROFILES["tgll"]["wineprefix"])


if __name__ == "__main__":
    unittest.main()
