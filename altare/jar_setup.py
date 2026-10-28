#!/usr/bin/env python3
"""Altare JAR compatibility bridge: installer source lives in russel2138/test.

Keep local constants and MIDlet validation for jar_run.py / jar_selection.py.
Only invoking `setup jar` downloads and executes the canonical installer.
TGLL/Wine, game selections, RMS and existing VNC configuration are untouched.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import runpy
import shutil
import subprocess
import sys
import tempfile
from urllib.request import Request, urlopen
import zipfile

ROOT = Path(__file__).resolve().parent.parent
RUNTIME = ROOT / ".tgll-runtime"
BASE = RUNTIME / "jar-runtime"
JRE = BASE / "java17"
MICROEMU = BASE / "microemu"
GAME = ROOT / "game.jar"
STATE = BASE / "state"
MAX_GAME = 25 * 1024 * 1024

REPO = "russel2138/test"
SOURCE = "altare/jar_setup.py"
LIMIT = 256 * 1024


def parse_midlet(jar):
    """Validate a user-supplied J2ME JAR (also used by jar_selection.py)."""
    if not jar.is_file() or not zipfile.is_zipfile(jar) or jar.stat().st_size > MAX_GAME:
        raise RuntimeError("game.jar missing or invalid JAR. Upload your Java ME game.jar")
    with zipfile.ZipFile(jar) as z:
        manifest = z.read("META-INF/MANIFEST.MF").decode("utf-8", "replace")
    manifest = manifest.replace("\r\n ", "").replace("\n ", "")
    for line in manifest.splitlines():
        if line.lower().startswith("midlet-1:"):
            klass = line.partition(":")[2].rsplit(",", 1)[-1].strip()
            if klass and all(c.isalnum() or c in "_.$" for c in klass):
                return klass, manifest
    raise RuntimeError("Missing valid MIDlet-1 in game.jar manifest: not a J2ME game")


def source_ref():
    """Prefer an immutable Git SHA; shared hosting GitHub API can be rate-limited."""
    git = shutil.which("git")
    if git:
        try:
            result = subprocess.run(
                [git, "-c", "credential.interactive=never", "ls-remote",
                 "--exit-code", f"https://github.com/{REPO}.git", "refs/heads/main"],
                capture_output=True, text=True, timeout=35, check=False,
                env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
            )
            if result.returncode == 0:
                for line in result.stdout.splitlines():
                    fields = line.split()
                    if (len(fields) == 2 and fields[1] == "refs/heads/main"
                            and re.fullmatch(r"[0-9a-f]{40}", fields[0])):
                        return fields[0]
        except (OSError, subprocess.TimeoutExpired):
            pass
    print("[altare-jar] WARNING: could not resolve commit with git; using test/main", flush=True)
    return "main"


def fetch_installer():
    ref = source_ref()
    url = f"https://raw.githubusercontent.com/{REPO}/{ref}/{SOURCE}"
    print(f"[altare-jar] Loading setup from {REPO}@{ref[:12]}/{SOURCE}", flush=True)
    request = Request(url, headers={
        "User-Agent": "Altare-JAR-setup/1.0",
        "Cache-Control": "no-cache",
    })
    with urlopen(request, timeout=45) as response:
        payload = response.read(LIMIT + 1)
    if not payload or len(payload) > LIMIT:
        raise RuntimeError("External JAR installer missing or larger than limit")
    compile(payload, SOURCE, "exec")
    BASE.mkdir(parents=True, exist_ok=True)
    target = BASE / "installer-source.py"
    with tempfile.NamedTemporaryFile(
            mode="wb", dir=BASE, prefix=".jar-installer-", delete=False) as tmp:
        temporary = Path(tmp.name)
        tmp.write(payload)
    try:
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)
    return target


def main():
    source = fetch_installer()
    # The test-repo installer is executed inside this existing Altare runtime.
    # It imports native_setup and jar_tigervnc from the launcher directory.
    folder = str(ROOT / "altare")
    if folder not in sys.path:
        sys.path.insert(0, folder)
    runpy.run_path(str(source), run_name="__main__")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"[altare-jar] FAILED: {type(error).__name__}: {error}", flush=True)
        raise SystemExit(1)
