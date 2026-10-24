#!/usr/bin/env python3
"""Download and verify a portable x86_64 Wine WOW64 build for Box64, no root."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tarfile
import traceback
import urllib.request

ROOT = Path(__file__).resolve().parent.parent
RUNTIME = ROOT / ".tgll-runtime"
BOX64 = RUNTIME / "box64" / "bin" / "box64"
DEST = RUNTIME / "wine"
CACHE = RUNTIME / "downloads"
RESULT = RUNTIME / "wine-setup.result"

# Wine 11.20's release notes warn of a startup segfault on some systems.
# Pin the previous release. SHA256 is supplied by the upstream release.
VERSION = "11.19"
ARCHIVE = f"wine-{VERSION}-amd64-wow64.tar.xz"
SHA256 = "a1fe858b45d12c9b16b91c7601d9b934f68430f7b6b95e240212ab6e2a198d8a"
URL = f"https://github.com/Kron4ek/Wine-Builds/releases/download/{VERSION}/{ARCHIVE}"
MAX_DOWNLOAD = 750 * 1024 * 1024
MAX_UNPACKED = 2500 * 1024 * 1024


def log(message):
    print(message, flush=True)


def sha256_file(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(2 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download():
    CACHE.mkdir(parents=True, exist_ok=True)
    archive = CACHE / ARCHIVE
    if archive.is_file() and sha256_file(archive) == SHA256:
        log("Reusing SHA256-verified Wine archive")
        return archive

    temp = CACHE / (ARCHIVE + ".part")
    temp.unlink(missing_ok=True)
    log(f"Downloading official Wine build: {URL}")
    request = urllib.request.Request(URL, headers={"User-Agent": "TGLL-Launcher/1.0"})
    total = 0
    try:
        with urllib.request.urlopen(request, timeout=60) as response, temp.open("wb") as out:
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > MAX_DOWNLOAD:
                    raise RuntimeError("Wine download exceeded 750 MiB limit")
                out.write(chunk)
                if total // (25 * 1024 * 1024) != (total - len(chunk)) // (25 * 1024 * 1024):
                    log(f"Downloaded {total // (1024 * 1024)} MiB")
        if sha256_file(temp) != SHA256:
            raise RuntimeError("SHA256 verification FAILED; refusing to extract Wine")
        os.replace(temp, archive)
    finally:
        temp.unlink(missing_ok=True)
    log("Wine SHA256 verified")
    return archive


def extract(archive):
    staging = RUNTIME / "wine-extract-tmp"
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True)
    log("Extracting Wine to .tgll-runtime (no sudo)...")
    try:
        with tarfile.open(archive, mode="r:xz") as tar:
            members = tar.getmembers()
            total_size = sum(item.size for item in members if item.isfile())
            if total_size > MAX_UNPACKED:
                raise RuntimeError("Wine expanded size exceeds 2500 MiB limit")
            tar.extractall(staging, filter="data")
        bins = [
            item for item in staging.rglob("wine")
            if item.parent.name == "bin" and item.is_file()
        ]
        if len(bins) != 1:
            raise RuntimeError(f"Expected one Wine executable, found {len(bins)}")
        root = bins[0].parent.parent
        if not (root / "bin").is_dir():
            raise RuntimeError("Invalid Wine archive layout")
        if DEST.exists():
            shutil.rmtree(DEST)
        shutil.move(str(root), str(DEST))
        wine = DEST / "bin" / "wine"
        wine.chmod(wine.stat().st_mode | 0o111)
        log(f"Portable Wine extracted: {wine}")
    finally:
        if staging.exists():
            shutil.rmtree(staging)


def wine_version():
    wine = DEST / "bin" / "wine"
    if not wine.is_file():
        raise RuntimeError(f"Wine executable missing: {wine}")
    env = os.environ.copy()
    env["BOX64_NOBANNER"] = "1"
    log(f"Testing: {BOX64} {wine} --version")
    try:
        result = subprocess.run(
            [str(BOX64), str(wine), "--version"],
            env=env, capture_output=True, text=True,
            timeout=60, check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("Wine version check timed out (missing runtime dependencies?)") from exc
    if result.stdout.strip():
        log(result.stdout.strip()[-4000:])
    if result.stderr.strip():
        log(result.stderr.strip()[-4000:])
    if result.returncode != 0:
        raise RuntimeError(
            f"Wine version check failed (exit {result.returncode}); "
            "the host may lack required native libraries. Wine files were kept."
        )
    log(f"SUCCESS: Portable Wine works through Box64 at {wine}")
    log("Next step is a display server and software rendering; do not run TGLL yet.")


def main():
    RUNTIME.mkdir(parents=True, exist_ok=True)
    log("TGLL Wine WOW64 installer")
    log(f"Host architecture: {platform.machine()}")
    if platform.machine().lower() not in ("aarch64", "arm64"):
        raise RuntimeError("The Wine/Box64 installer targets Linux ARM64")
    if not BOX64.is_file():
        raise RuntimeError("Box64 missing. Run install-box64 first.")
    try:
        if not (DEST / "bin" / "wine").is_file():
            extract(download())
        else:
            log("Existing Wine directory found, reusing it")
        wine_version()
    except Exception as error:
        RESULT.write_text("FAILED: " + str(error), encoding="utf-8")
        log(f"FAILED: {error}")
        traceback.print_exc()
        raise SystemExit(1)
    else:
        RESULT.write_text("SUCCESS", encoding="utf-8")


if __name__ == "__main__":
    main()
