#!/usr/bin/env python3
"""Rootless, SHA256-pinned Xvfb bootstrap for HidenCloud ARM64.

Downloads Debian Bookworm ARM64 packages, extracts into .tgll-runtime
without sudo or dpkg installation, checks dynamic library dependencies,
then tests a temporary local-only X11 server.
"""
from __future__ import annotations

import ctypes
import hashlib
import os
from pathlib import Path
import platform
import shutil
import subprocess
import tempfile
import time
import urllib.request

ROOT = Path(__file__).resolve().parent.parent
RUNTIME = ROOT / ".tgll-runtime"
PREFIX = RUNTIME / "display"
PACKAGES = RUNTIME / "downloads"
BIN = PREFIX / "usr" / "bin" / "Xvfb"

# The exact package SHA256 checksums are published by packages.debian.org.
# Source: Debian bookworm for glibc 2.36, not the Debian trixie release.
DEBS = (
    (
        "xvfb_21.1.7-3+deb12u13_arm64.deb",
        "https://security.debian.org/debian-security/pool/updates/main/x/xorg-server/xvfb_21.1.7-3%2Bdeb12u13_arm64.deb",
        "2ea0e909a48d1c32768a37ff0cf1621e763c4f133cbeae2f5c00ee4ef2e7119a",
        5 * 1024 * 1024,
    ),
    (
        "libunwind8_1.6.2-3_arm64.deb",
        "https://deb.debian.org/debian/pool/main/libu/libunwind/libunwind8_1.6.2-3_arm64.deb",
        "f83ce7c58caaf15cfb0b6ced538751ea11ded920443aecfe617049ae184b715e",
        1024 * 1024,
    ),
    (
        "libxfont2_2.0.6-1+deb12u1_arm64.deb",
        "https://security.debian.org/debian-security/pool/updates/main/libx/libxfont/libxfont2_2.0.6-1%2Bdeb12u1_arm64.deb",
        "5aa50cbe3b369669354a730767a60db5ee5b8261b3dfce33ee0a47e043bcfd6d",
        1024 * 1024,
    ),
    (
        "libfontenc1_1.1.4-1_arm64.deb",
        "https://deb.debian.org/debian/pool/main/libf/libfontenc/libfontenc1_1.1.4-1_arm64.deb",
        "0ec21487b4e9b23043353fe51be8576d70a8860aef40104ca52df14bf1dc476c",
        1024 * 1024,
    ),
)


def log(message):
    print(message, flush=True)


def checksum(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def download(name, url, expected, maximum):
    PACKAGES.mkdir(parents=True, exist_ok=True)
    path = PACKAGES / name
    if path.is_file() and checksum(path) == expected:
        log(f"Verified cached package: {name}")
        return path
    if path.exists():
        path.unlink()
    log(f"Downloading Debian ARM64 package: {name}")
    req = urllib.request.Request(url, headers={"User-Agent": "TGLL-display/1.0"})
    tmp = PACKAGES / (name + ".partial")
    try:
        total = 0
        with urllib.request.urlopen(req, timeout=60) as response, tmp.open("wb") as out:
            for block in iter(lambda: response.read(1024 * 1024), b""):
                total += len(block)
                if total > maximum:
                    raise RuntimeError(f"Package is larger than expected: {name}")
                out.write(block)
        if checksum(tmp) != expected:
            raise RuntimeError(f"Debian SHA256 mismatch: {name}; refusing to extract")
        tmp.replace(path)
    finally:
        tmp.unlink(missing_ok=True)
    log(f"Verified SHA256: {name}")
    return path


def env_for_display():
    env = os.environ.copy()
    native_paths = [
        PREFIX / "usr/lib/aarch64-linux-gnu",
        PREFIX / "lib/aarch64-linux-gnu",
        PREFIX / "usr/lib",
        PREFIX / "lib",
    ]
    env["LD_LIBRARY_PATH"] = os.pathsep.join(
        [str(path) for path in native_paths if path.is_dir()]
        + ([env["LD_LIBRARY_PATH"]] if env.get("LD_LIBRARY_PATH") else [])
    )
    env["LIBGL_ALWAYS_SOFTWARE"] = "1"
    return env


def check_dependencies(env):
    ldd = shutil.which("ldd")
    if not ldd:
        log("ldd not installed; checking Xvfb directly")
        return
    result = subprocess.run([ldd, str(BIN)], env=env, capture_output=True,
                            text=True, timeout=20, check=False)
    output = result.stdout + result.stderr
    missing = [line.strip() for line in output.splitlines() if "not found" in line]
    if missing:
        log("Missing ARM64 Xvfb libraries:")
        for line in missing:
            log("  " + line)
        raise RuntimeError("Xvfb has missing ARM64 dependencies; see lines above")
    if result.returncode:
        raise RuntimeError("ldd could not inspect Xvfb: " + output[-1200:])
    log("Xvfb dynamic library dependency check passed")


def probe_x11(display):
    lib = ctypes.CDLL("libX11.so.6")
    lib.XOpenDisplay.argtypes = [ctypes.c_char_p]
    lib.XOpenDisplay.restype = ctypes.c_void_p
    lib.XCloseDisplay.argtypes = [ctypes.c_void_p]
    lib.XCloseDisplay.restype = ctypes.c_int
    pointer = lib.XOpenDisplay(display.encode())
    if not pointer:
        return False
    lib.XCloseDisplay(pointer)
    return True


def smoke_test(env):
    with tempfile.TemporaryDirectory(prefix="tgll-xvfb-", dir=RUNTIME) as tmp:
        display = None
        # Avoid interfering with other applications that own an X display.
        for number in range(90, 100):
            if not Path(f"/tmp/.X11-unix/X{number}").exists() and not Path(
                f"/tmp/.X{number}-lock"
            ).exists():
                display = f":{number}"
                break
        if not display:
            raise RuntimeError("All test X11 displays :90..:99 are busy")
        log(f"Starting temporary Xvfb display {display}, 640x480x24")
        command = [
            str(BIN), display, "-screen", "0", "640x480x24",
            "-nolisten", "tcp", "-noreset",
        ]
        output_path = Path(tmp) / "xvfb.log"
        with output_path.open("w", encoding="utf-8") as out:
            process = subprocess.Popen(command, env=env, cwd=ROOT,
                                       stdin=subprocess.DEVNULL,
                                       stdout=out, stderr=subprocess.STDOUT)
            try:
                for _ in range(40):
                    if process.poll() is not None:
                        break
                    if probe_x11(display):
                        log(f"SUCCESS: Xvfb ARM64 display {display} accepts X11 clients")
                        log("Test display shut down after validation; game not launched")
                        return
                    time.sleep(0.2)
                error = output_path.read_text(encoding="utf-8", errors="replace")
                raise RuntimeError(
                    f"Xvfb failed its X11 connection test (exit {process.poll()}): "
                    + error[-2500:]
                )
            finally:
                if process.poll() is None:
                    process.terminate()
                    try:
                        process.wait(timeout=4)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait()


def main():
    log(f"TGLL Xvfb installer on {platform.machine()}")
    if platform.machine().lower() not in ("aarch64", "arm64"):
        raise RuntimeError("This installer is pinned to Debian ARM64 packages")
    if not shutil.which("dpkg-deb"):
        raise RuntimeError("Missing dpkg-deb; cannot safely extract Debian .deb packages")
    PREFIX.mkdir(parents=True, exist_ok=True)
    for name, url, digest, size in DEBS:
        marker = PREFIX / ".installed" / (name + ".ok")
        if marker.is_file() and marker.read_text().strip() == digest:
            log(f"Already extracted: {name}")
            continue
        deb = download(name, url, digest, size)
        log(f"Extracting {name} into private runtime...")
        subprocess.run(["dpkg-deb", "--extract", str(deb), str(PREFIX)],
                       check=True, timeout=90)
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text(digest, encoding="ascii")
    if not BIN.is_file():
        raise RuntimeError(f"Expected Xvfb binary missing at {BIN}")
    env = env_for_display()
    check_dependencies(env)
    smoke_test(env)


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        log(f"FAILED: {error}")
        raise SystemExit(1)
