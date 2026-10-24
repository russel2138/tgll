#!/usr/bin/env python3
"""Download and verify a portable x86_64 Wine WOW64 build for Box64, no root."""
from __future__ import annotations

import hashlib
import io
import struct
import ctypes.util
import os
from pathlib import Path, PurePosixPath
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

# Self-contained amd64 libgcc installer; no additional Python module required.
LIB_DIR = RUNTIME / "x86_64-libs"
FILENAME = "libgcc-s1_12.2.0-14+deb12u1_amd64.deb"
PACKAGE_URL = (
    "https://deb.debian.org/debian/pool/main/g/gcc-12/"
    "libgcc-s1_12.2.0-14%2Bdeb12u1_amd64.deb"
)
PACKAGE_SHA256 = "3016e62cb4b7cd8038822870601f5ed131befe942774d0f745622cc77d8a88f7"
MAX_DEB_BYTES = 2 * 1024 * 1024
MAX_LIBRARY_BYTES = 1024 * 1024


def is_amd64_elf(data: bytes) -> bool:
    return (
        len(data) >= 20
        and data[:4] == b"\x7fELF"
        and data[4] == 2
        and data[5] == 1
        and struct.unpack_from("<H", data, 18)[0] == 62
    )


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def get_verified_package() -> bytes:
    cache = RUNTIME / "downloads" / FILENAME
    if cache.is_file():
        data = cache.read_bytes()
        if sha256(data) == PACKAGE_SHA256:
            log("Using cached, SHA256-verified Debian amd64 libgcc-s1")
            return data
        log("Discarding invalid cached libgcc-s1 archive")
        cache.unlink()

    log(f"Downloading Debian amd64 libgcc-s1: {PACKAGE_URL}")
    request = urllib.request.Request(PACKAGE_URL, headers={
        "User-Agent": "TGLL-Launcher/1.0",
    })
    with urllib.request.urlopen(request, timeout=45) as response:
        data = response.read(MAX_DEB_BYTES + 1)
    if len(data) > MAX_DEB_BYTES:
        raise RuntimeError("libgcc-s1 package unexpectedly large")
    if sha256(data) != PACKAGE_SHA256:
        raise RuntimeError("libgcc-s1 SHA256 mismatch; refusing installation")
    cache.parent.mkdir(parents=True, exist_ok=True)
    temp = cache.with_suffix(".part")
    try:
        temp.write_bytes(data)
        os.replace(temp, cache)
    finally:
        temp.unlink(missing_ok=True)
    log("Verified Debian package SHA256")
    return data


def extract_libgcc(data: bytes) -> bytes:
    """Read a .deb ar archive; extract only the amd64 libgcc_s.so.1 ELF."""
    if not data.startswith(b"!<arch>\n"):
        raise RuntimeError("Not a Debian ar archive")
    pos = 8
    while pos + 60 <= len(data):
        header = data[pos:pos + 60]
        if header[58:60] != bytes((96, 10)):
            raise RuntimeError("Invalid ar member header")
        try:
            size = int(header[48:58].strip())
        except ValueError as exc:
            raise RuntimeError("Invalid ar member size") from exc
        name = header[:16].decode("ascii", errors="replace").strip().rstrip("/")
        start = pos + 60
        end = start + size
        if end > len(data):
            raise RuntimeError("Truncated Debian package")
        if name.startswith("data.tar"):
            if name.endswith(".zst"):
                raise RuntimeError("Unexpected zstd data.tar; unsupported archive")
            with tarfile.open(fileobj=io.BytesIO(data[start:end]), mode="r:*") as archive:
                for member in archive:
                    path = PurePosixPath(member.name)
                    if path.name != "libgcc_s.so.1" or not member.isfile():
                        continue
                    if member.size > MAX_LIBRARY_BYTES:
                        raise RuntimeError("libgcc_s.so.1 exceeds expected size")
                    stream = archive.extractfile(member)
                    if stream is None:
                        raise RuntimeError("Unable to extract libgcc_s.so.1")
                    contents = stream.read(MAX_LIBRARY_BYTES + 1)
                    if len(contents) > MAX_LIBRARY_BYTES or not is_amd64_elf(contents):
                        raise RuntimeError("libgcc_s.so.1 is not an amd64 ELF library")
                    return contents
            raise RuntimeError("libgcc_s.so.1 missing from Debian package")
        pos = end + (size % 2)
    raise RuntimeError("Debian package lacks a supported data.tar member")


def ensure_libgcc() -> Path:
    destination = LIB_DIR / "libgcc_s.so.1"
    if destination.is_file():
        if is_amd64_elf(destination.read_bytes()):
            log(f"Using existing amd64 libgcc: {destination}")
            return destination
        raise RuntimeError(f"Existing libgcc_s.so.1 is not x86-64: {destination}")

    data = extract_libgcc(get_verified_package())
    LIB_DIR.mkdir(parents=True, exist_ok=True)
    temp = LIB_DIR / ".libgcc_s.so.1.tmp"
    try:
        temp.write_bytes(data)
        os.replace(temp, destination)
    finally:
        temp.unlink(missing_ok=True)
    log(f"Installed amd64 libgcc_s.so.1 without root: {destination}")
    return destination




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


def box64_env():
    env = os.environ.copy()
    current = env.get("BOX64_LD_LIBRARY_PATH", "")
    paths = [str(LIB_DIR)] if LIB_DIR.is_dir() else []
    if current:
        paths.append(current)
    if paths:
        env["BOX64_LD_LIBRARY_PATH"] = os.pathsep.join(paths)
    return env


def diagnose_wine(wine):
    """Collect actionable Box64 loader errors without installing anything."""
    import collections

    dll = DEST / "lib" / "wine" / "x86_64-unix" / "ntdll.so"
    log("=== Wine/Box64 loader diagnostics ===")
    log(f"Wine ntdll.so: {'present' if dll.is_file() else 'MISSING'} ({dll})")
    log(f"Native libunwind lookup: {ctypes.util.find_library('unwind') or 'not found'}")
    readelf = shutil.which("readelf")
    if readelf and dll.is_file():
        info = subprocess.run(
            [readelf, "-d", str(dll)], capture_output=True, text=True,
            timeout=10, check=False,
        )
        for line in info.stdout.splitlines():
            if "(NEEDED)" in line:
                log("ntdll dependency: " + line.strip())
    else:
        log("readelf unavailable; native libunwind lookup is only a hint")
    env = box64_env()
    env["BOX64_LOG"] = "2"
    env["BOX64_DLSYM_ERROR"] = "1"
    env["BOX64_NOBANNER"] = "0"
    debug_path = RUNTIME / "wine-debug.log"
    log("Capturing Box64 loader diagnostics...")
    try:
        with debug_path.open("w", encoding="utf-8") as stream:
            result = subprocess.run(
                [str(BOX64), str(wine), "--version"],
                stdout=stream, stderr=subprocess.STDOUT, env=env,
                timeout=45, check=False,
            )
        log(f"Verbose Box64 exit code: {result.returncode}")
    except subprocess.TimeoutExpired:
        log("Verbose Box64 command timed out after 45s")
    log(f"Full diagnostic log: {debug_path}")
    keywords = ("error", "cannot", "missing", "symbol", "unwind",
                "relocat", "ntdll", "needed lib", "not found",
                "wine64", "wine preloader", "libc.so")
    # Bounded memory even when Box64 prints a large debug log.
    highlights = collections.deque(maxlen=65)
    tail = collections.deque(maxlen=15)
    with debug_path.open("r", encoding="utf-8", errors="replace") as stream:
        for line in stream:
            tail.append(line.rstrip())
            if any(term in line.lower() for term in keywords):
                highlights.append(line.rstrip())
    log("--- Relevant loader messages (last 65 matches) ---")
    for line in highlights:
        log(line)
    log("--- End of diagnostic output (last 15 lines) ---")
    for line in tail:
        log(line)
    log("No packages were installed by this diagnostic run.")


def wine_version():
    wine = DEST / "bin" / "wine"
    if not wine.is_file():
        raise RuntimeError(f"Wine executable missing: {wine}")
    env = box64_env()
    env["BOX64_NOBANNER"] = "1"
    log(f"Box64 x86_64 library path: {env.get('BOX64_LD_LIBRARY_PATH', '(default)')}")
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
        diagnose_wine(wine)
        raise RuntimeError(
            f"Wine version check failed (exit {result.returncode}). "
            "See diagnostic messages above or .tgll-runtime/wine-debug.log. "
            "Wine files were kept."
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
        if "--diagnose" in sys.argv and not (DEST / "bin" / "wine").is_file():
            raise RuntimeError("Wine is not extracted; run install-wine first")
        if not (DEST / "bin" / "wine").is_file():
            extract(download())
        else:
            log("Existing Wine directory found, reusing it")
        if "--diagnose" not in sys.argv:
            ensure_libgcc()
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
