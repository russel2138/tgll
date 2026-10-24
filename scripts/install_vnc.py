#!/usr/bin/env python3
"""Rootless ARM64 x11vnc installation for the TGLL/Xvfb game session.

Uses Debian Bookworm package SHA256 digests from its official Packages.xz;
does not install desktop environments, run sudo, or open any network ports.
"""
from __future__ import annotations

import hashlib
import lzma
import os
from pathlib import Path
import platform
import secrets
import shutil
import string
import subprocess
import sys
import urllib.request

from install_display import INDEX_URL, RUNTIME, PREFIX as DISPLAY_PREFIX, download
from install_graphics_libs import PREFIX as GRAPHICS_PREFIX

VNC_DIR = RUNTIME / "vnc"
PREFIX = VNC_DIR / "native"
BIN = PREFIX / "usr" / "bin" / "x11vnc"
PASSWORD_FILE = VNC_DIR / "passwd"
DISPLAY_PASSWORD = VNC_DIR / "password-display.txt"
PACKAGES = (
    "x11vnc",
    "libvncserver1",
    "libvncclient1",
    "libavahi-client3",
    "libavahi-common3",
    # x11vnc/LibVNCServer runtime dependencies absent in minimal HidenCloud.
    # Map the exact missing ARM64 SONAMEs from the real container log:
    # libXtst.so.6 -> libxtst6
    # libXdamage.so.1 -> libxdamage1
    # liblzo2.so.2 -> liblzo2-2
    "libxtst6",
    "libxdamage1",
    "liblzo2-2",
)
MAX_INDEX_COMPRESSED = 25 * 1024 * 1024
MAX_INDEX_UNPACKED = 130 * 1024 * 1024
MAX_DEB_SIZE = 6 * 1024 * 1024


def say(text):
    print(text, flush=True)


def index_packages():
    say("Reading Debian Bookworm ARM64 package index for x11vnc and dependencies...")
    req = urllib.request.Request(INDEX_URL, headers={
        "User-Agent": "TGLL-VNC/1.0", "Accept-Encoding": "identity",
    })
    with urllib.request.urlopen(req, timeout=80) as response:
        compressed = response.read(MAX_INDEX_COMPRESSED + 1)
    if len(compressed) > MAX_INDEX_COMPRESSED:
        raise RuntimeError("Debian package index exceeds 25 MiB")
    data = lzma.decompress(compressed, memlimit=256 * 1024 * 1024)
    if len(data) > MAX_INDEX_UNPACKED:
        raise RuntimeError("Debian package index decompresses above 130 MiB")
    found = {}
    for part in data.decode("utf-8", errors="replace").split("\n\n"):
        if not part.startswith("Package: "):
            continue
        pkg = part.partition("\n")[0][9:].strip()
        if pkg not in PACKAGES:
            continue
        fields = {}
        for line in part.splitlines():
            if ": " in line and not line.startswith((" ", "\t")):
                name, value = line.split(": ", 1)
                fields[name] = value
        if fields.get("Architecture") != "arm64":
            continue
        filepath = fields.get("Filename", "")
        digest = fields.get("SHA256", "")
        try:
            size = int(fields.get("Size", "0"))
        except ValueError as exc:
            raise RuntimeError("Invalid Debian package metadata") from exc
        if (not filepath.startswith("pool/main/") or ".." in Path(filepath).parts
            or len(digest) != 64 or
            any(ch not in "0123456789abcdef" for ch in digest)
            or not 1 <= size <= MAX_DEB_SIZE):
            raise RuntimeError("Untrusted metadata for " + pkg)
        found[pkg] = (
            Path(filepath).name,
            "https://deb.debian.org/debian/" + filepath.replace("+", "%2B"),
            digest,
            size + 1024,
        )
    missing = set(PACKAGES) - set(found)
    if missing:
        raise RuntimeError("Debian packages absent: " + ", ".join(sorted(missing)))
    return found


def env_for_vnc(base=None):
    env = (base or os.environ).copy()
    env.pop("LD_PRELOAD", None)
    env.pop("TGLL_XKBCOMP_PATH", None)
    directories = [
        PREFIX / "usr/lib/aarch64-linux-gnu",
        PREFIX / "lib/aarch64-linux-gnu",
        GRAPHICS_PREFIX / "usr/lib/aarch64-linux-gnu",
        GRAPHICS_PREFIX / "lib/aarch64-linux-gnu",
        DISPLAY_PREFIX / "usr/lib/aarch64-linux-gnu",
        DISPLAY_PREFIX / "lib/aarch64-linux-gnu",
    ]
    parts = [str(p) for p in directories if p.is_dir()]
    if env.get("LD_LIBRARY_PATH"):
        parts.append(env["LD_LIBRARY_PATH"])
    env["LD_LIBRARY_PATH"] = os.pathsep.join(parts)
    return env


def check_libraries():
    result = subprocess.run(
        ["ldd", str(BIN)], env=env_for_vnc(),
        capture_output=True, text=True, timeout=20, check=False,
    )
    output = result.stdout + result.stderr
    missing = [x.strip() for x in output.splitlines() if "not found" in x]
    if missing:
        for line in missing:
            say("MISSING: " + line)
        raise RuntimeError("x11vnc has missing native ARM64 dependencies")
    if result.returncode:
        raise RuntimeError("ldd could not validate x11vnc: " + output[-1500:])
    say("SUCCESS: Native ARM64 x11vnc dependencies resolved")


def set_password():
    if not BIN.is_file():
        raise RuntimeError("x11vnc is not installed; run install-vnc")
    # RFB classic authentication uses only the first 8 password bytes.
    password = "".join(secrets.choice(string.ascii_letters + string.digits)
                       for _ in range(8))
    VNC_DIR.mkdir(parents=True, exist_ok=True)
    os.chmod(VNC_DIR, 0o700)
    target = PASSWORD_FILE.with_name("passwd.tmp")
    target.unlink(missing_ok=True)
    try:
        result = subprocess.run(
            [str(BIN), "-norc", "-storepasswd", password, str(target)],
            env=env_for_vnc(), stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, text=True, timeout=20, check=False,
        )
        if result.returncode != 0 or not target.is_file():
            raise RuntimeError("Failed to create x11vnc RFB auth file: " + result.stdout[-800:])
        target.chmod(0o600)
        target.replace(PASSWORD_FILE)
        PASSWORD_FILE.chmod(0o600)
    finally:
        target.unlink(missing_ok=True)
    # User explicitly requested a repeatable vnc-info display. Keep the
    # optional plain-text copy in this unshared container only, never GitHub.
    # A separate 0600 file avoids passing the password in process arguments.
    display_tmp = DISPLAY_PASSWORD.with_name("password-display.tmp")
    try:
        with os.fdopen(os.open(str(display_tmp), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "w") as stream:
            stream.write(password + "\n")
        display_tmp.chmod(0o600)
        display_tmp.replace(DISPLAY_PASSWORD)
    finally:
        display_tmp.unlink(missing_ok=True)
    say("VNC PASSWORD (keep private): " + password)
    say("Run vnc-info anytime to view this password and connection info.")
    say(f"Password file: {PASSWORD_FILE} (mode 0600)")
    say("RFB legacy password authentication is NOT transport encryption.")
    say("Changing the password while VNC runs requires game-restart.")


def main():
    if platform.machine().lower() not in ("aarch64", "arm64"):
        raise RuntimeError("x11vnc installer targets Linux ARM64")
    if not shutil.which("dpkg-deb") or not shutil.which("ldd"):
        raise RuntimeError("dpkg-deb and ldd are required")
    VNC_DIR.mkdir(parents=True, exist_ok=True)
    VNC_DIR.chmod(0o700)
    PREFIX.mkdir(parents=True, exist_ok=True)
    records = index_packages()
    for name in PACKAGES:
        filename, url, digest, limit = records[name]
        marker = PREFIX / ".installed" / (filename + ".ok")
        if marker.is_file() and marker.read_text().strip() == digest:
            say("Already extracted: " + filename)
            continue
        deb = download(filename, url, digest, limit)
        say("Extracting VNC dependency: " + filename)
        subprocess.run(["dpkg-deb", "--extract", str(deb), str(PREFIX)],
                       check=True, timeout=75)
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text(digest, encoding="ascii")
    if not BIN.is_file():
        raise RuntimeError(f"x11vnc executable not found: {BIN}")
    check_libraries()
    if PASSWORD_FILE.is_file():
        say("Private VNC password file already exists; preserving it.")
    else:
        say("VNC authentication not yet configured: run vnc-password in launcher console")
        say("The password will be shown once in the console, not stored in installer logs.")
    say("SUCCESS: Rootless x11vnc installed.")
    say("Default VNC bind is localhost; enable public access only explicitly.")


if __name__ == "__main__":
    try:
        if "--password" in sys.argv:
            set_password()
        else:
            main()
    except Exception as error:
        say(f"FAILED: {type(error).__name__}: {error}")
        raise SystemExit(1)
