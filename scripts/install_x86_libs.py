#!/usr/bin/env python3
"""Install minimal amd64 libraries required by Box64/Wine without root.

Only extracts libgcc_s.so.1 from a SHA256-verified Debian 12 amd64 package.
No apt install, sudo, or changes to the host's ARM64 libraries.
"""
from __future__ import annotations

import hashlib
import io
import os
from pathlib import Path, PurePosixPath
import struct
import tarfile
import urllib.request

ROOT = Path(__file__).resolve().parent.parent
RUNTIME = ROOT / ".tgll-runtime"
LIB_DIR = RUNTIME / "x86_64-libs"
FILENAME = "libgcc-s1_12.2.0-14+deb12u1_amd64.deb"
PACKAGE_URL = (
    "https://deb.debian.org/debian/pool/main/g/gcc-12/"
    "libgcc-s1_12.2.0-14%2Bdeb12u1_amd64.deb"
)
PACKAGE_SHA256 = "3016e62cb4b7cd8038822870601f5ed131befe942774d0f745622cc77d8a88f7"
MAX_DEB_BYTES = 2 * 1024 * 1024
MAX_LIBRARY_BYTES = 1024 * 1024


def log(message):
    print(message, flush=True)


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


if __name__ == "__main__":
    ensure_libgcc()
