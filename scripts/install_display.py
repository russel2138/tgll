#!/usr/bin/env python3
"""Rootless, SHA256-pinned Xvfb bootstrap for HidenCloud ARM64.

Downloads Debian Bookworm ARM64 packages, extracts into .tgll-runtime
without sudo or dpkg installation, checks dynamic library dependencies,
then tests a temporary local-only X11 server.
"""
from __future__ import annotations

import ctypes
import json
import lzma
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
XKBCOMP = PREFIX / "usr" / "bin" / "xkbcomp"
XKB_DATA = PREFIX / "usr" / "share" / "X11" / "xkb"
SHIM = PREFIX / "exec-xkbcomp.so"

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



# Debian Bookworm apt indexes supply package SHA256 and filenames over HTTPS.
# This is used only for the three additional XKB packages, not the packages
# already installed and SHA256-pinned in DEBS above.
XKB_PACKAGES = {
    "x11-xkb-utils": "7.7+7",
    "libxkbfile1": "1:1.1.0-1",
    "xkb-data": "2.35.1-1",
}
INDEX_URL = "https://deb.debian.org/debian/dists/bookworm/main/binary-arm64/Packages.xz"
MAX_INDEX_BYTES = 20 * 1024 * 1024

# Xorg Debian's Xvfb is compiled with /usr/bin/xkbcomp. Since an
# unprivileged container cannot install into /usr/bin, intercept only
# calls to execl("/bin/sh", "sh", "-c", ".../usr/bin/xkbcomp ...")
# and replace that exact command with the locally extracted xkbcomp.
# This does not patch the Xvfb executable or modify system libraries.
EXEC_SHIM_C = r"""
#define _GNU_SOURCE
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

int execl(const char *path, const char *arg, ...) {
    char *argv[128];
    int i;
    va_list ap;
    argv[0] = (char *)arg;
    va_start(ap, arg);
    for (i = 1; i < 128; ++i) {
        argv[i] = va_arg(ap, char *);
        if (argv[i] == NULL) break;
    }
    va_end(ap);
    if (i == 128) { return -1; }
    if (path && strcmp(path, "/bin/sh") == 0 &&
        argv[0] && strcmp(argv[0], "sh") == 0 &&
        i >= 3 && argv[1] && strcmp(argv[1], "-c") == 0 &&
        argv[2]) {
        const char *old = "/usr/bin/xkbcomp";
        const char *found = strstr(argv[2], old);
        const char *replacement = getenv("TGLL_XKBCOMP_PATH");
        if (found && replacement && replacement[0] == '/') {
            size_t cmdlen = strlen(argv[2]);
            size_t oldlen = strlen(old);
            size_t newlen = strlen(replacement);
            if (cmdlen + newlen < 16384) {
                char *newcmd = malloc(cmdlen + newlen + 1);
                if (newcmd) {
                    size_t before = (size_t)(found - argv[2]);
                    memcpy(newcmd, argv[2], before);
                    memcpy(newcmd + before, replacement, newlen);
                    strcpy(newcmd + before + newlen, found + oldlen);
                    argv[2] = newcmd;
                    fprintf(stderr, "[tgll] Redirecting /usr/bin/xkbcomp to private runtime\n");
                }
            }
        }
    }
    return execv(path, argv);
}
"""


def debian_xkb_packages():
    """Find authoritative package digests in Debian's Bookworm Packages.xz."""
    log("Reading Debian Bookworm ARM64 package index for XKB dependencies...")
    request = urllib.request.Request(INDEX_URL, headers={
        "User-Agent": "TGLL-display/1.0", "Accept-Encoding": "identity",
    })
    with urllib.request.urlopen(request, timeout=70) as stream:
        compressed = stream.read(MAX_INDEX_BYTES + 1)
    if len(compressed) > MAX_INDEX_BYTES:
        raise RuntimeError("Debian package index exceeds 20 MiB limit")
    data = lzma.decompress(compressed).decode("utf-8", errors="replace")
    selected = {}
    for paragraph in data.split("\n\n"):
        if not paragraph.startswith("Package: "):
            continue
        package_name = paragraph[9:paragraph.find("\n")]
        if package_name not in XKB_PACKAGES:
            continue
        fields = {}
        for line in paragraph.splitlines():
            if ": " in line and not line.startswith(" "):
                name, value = line.split(": ", 1)
                fields[name] = value
        if fields.get("Version") == XKB_PACKAGES[package_name]:
            filename = fields.get("Filename", "")
            digest = fields.get("SHA256", "")
            size = int(fields.get("Size", "0"))
            if not filename.startswith("pool/main/") or len(digest) != 64:
                raise RuntimeError("Invalid Debian package metadata: " + package_name)
            if size < 1 or size > 4 * 1024 * 1024:
                raise RuntimeError("Unexpected XKB Debian package size: " + package_name)
            selected[package_name] = (
                Path(filename).name,
                "https://deb.debian.org/debian/" + filename.replace("+", "%2B"),
                digest,
                max(size + 1024, 1 * 1024 * 1024),
            )
    missing = set(XKB_PACKAGES) - set(selected)
    if missing:
        raise RuntimeError("Missing Bookworm XKB package metadata: " + ", ".join(sorted(missing)))
    return selected


def install_xkb_packages():
    existing_data = XKB_DATA / "rules" / "evdev"
    if XKBCOMP.is_file() and existing_data.is_file():
        log("Reusing previously installed local xkbcomp and XKB keymaps")
        return
    packages = debian_xkb_packages()
    for name in XKB_PACKAGES:
        filename, url, digest, size = packages[name]
        marker = PREFIX / ".installed" / (filename + ".ok")
        if marker.is_file() and marker.read_text().strip() == digest:
            log(f"Already extracted: {filename}")
            continue
        pkg = download(filename, url, digest, size)
        log("Extracting private XKB package: " + filename)
        subprocess.run(["dpkg-deb", "--extract", str(pkg), str(PREFIX)],
                       check=True, timeout=90)
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text(digest, encoding="ascii")
    if not XKBCOMP.is_file() or not existing_data.is_file():
        raise RuntimeError("xkbcomp or XKB rules missing after Debian extraction")


def build_xkb_shim():
    if SHIM.is_file():
        log("Using existing private XKB redirection shim")
        return
    gcc = shutil.which("gcc")
    if not gcc:
        raise RuntimeError("gcc unavailable; cannot create rootless XKB helper")
    source = PREFIX / "exec-xkbcomp.c"
    source.write_text(EXEC_SHIM_C, encoding="utf-8")
    log("Building small ARM64 XKB exec redirector (private LD_PRELOAD)...")
    subprocess.run([gcc, "-shared", "-fPIC", "-O2",
                    "-o", str(SHIM), str(source)],
                   check=True, timeout=40)
    if not SHIM.is_file():
        raise RuntimeError("Failed to compile private XKB helper")


def ensure_local_socket_dir():
    """Create /tmp/.X11-unix only when absent, without sudo or touching others."""
    directory = Path("/tmp/.X11-unix")
    if directory.is_symlink():
        raise RuntimeError("Refusing symlink at /tmp/.X11-unix")
    if not directory.exists():
        try:
            directory.mkdir(mode=0o1777)
            directory.chmod(0o1777)
            log("Created /tmp/.X11-unix with sticky mode 1777 (unprivileged user)")
        except OSError as error:
            raise RuntimeError(
                "Cannot create /tmp/.X11-unix as this container user; "
                "X11 Unix sockets may be unavailable"
            ) from error
    if not directory.is_dir():
        raise RuntimeError("/tmp/.X11-unix exists but is not a directory")
    if directory.stat().st_mode & 0o7777 != 0o1777:
        raise RuntimeError("/tmp/.X11-unix has unexpected permissions (expected 1777)")


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
    xdg = PREFIX / "xdg-runtime"
    xdg.mkdir(parents=True, exist_ok=True, mode=0o700)
    xdg.chmod(0o700)
    env["XDG_RUNTIME_DIR"] = str(xdg)
    env["LD_PRELOAD"] = str(SHIM) + ((":" + env["LD_PRELOAD"]) if env.get("LD_PRELOAD") else "")
    env["TGLL_XKBCOMP_PATH"] = str(XKBCOMP)
    return env


def check_dependencies(env):
    ldd = shutil.which("ldd")
    if not ldd:
        log("ldd not installed; checking Xvfb directly")
        return
    for binary in (BIN, XKBCOMP):
        result = subprocess.run([ldd, str(binary)], env=env, capture_output=True,
                                text=True, timeout=20, check=False)
        output = result.stdout + result.stderr
        missing = [line.strip() for line in output.splitlines() if "not found" in line]
        if missing:
            log(f"Missing ARM64 libraries for {binary.name}:")
            for line in missing:
                log("  " + line)
            raise RuntimeError(f"{binary.name} has missing ARM64 dependencies")
        if result.returncode:
            raise RuntimeError(f"ldd could not inspect {binary.name}: " + output[-1200:])
    log("Xvfb and xkbcomp ARM64 dynamic library dependency checks passed")


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
            "-xkbdir", str(XKB_DATA),
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
    install_xkb_packages()
    build_xkb_shim()
    ensure_local_socket_dir()
    env = env_for_display()
    check_dependencies(env)
    smoke_test(env)


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        log(f"FAILED: {error}")
        raise SystemExit(1)
