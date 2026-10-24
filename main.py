#!/usr/bin/env python3
"""Small bootstrap: keep PY_FILE=main.py on HidenCloud."""
from pathlib import Path
import os
import sys
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent
APP = ROOT / "app.py"

if not APP.is_file():
    url = "https://raw.githubusercontent.com/russel2138/tgll/main/app.py"
    print("Downloading TGLL launcher from GitHub...", flush=True)
    request = Request(url, headers={"User-Agent": "tgll-bootstrap/1.0"})
    with urlopen(request, timeout=35) as response:
        payload = response.read(2 * 1024 * 1024 + 1)
    if len(payload) > 2 * 1024 * 1024:
        raise RuntimeError("app.py exceeds the bootstrap size limit")
    compile(payload, "app.py", "exec")
    APP.write_bytes(payload)

os.execv(sys.executable, [sys.executable, "-u", str(APP)])
