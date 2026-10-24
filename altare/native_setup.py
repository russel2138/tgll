#!/usr/bin/env python3
"""Rootless native amd64 Wine/Xvfb/x11vnc bootstrap for Altare Python Hosting.

Downloads Debian Bookworm amd64 packages with SHA256 verification from the
signed-by-Debian distribution metadata served over HTTPS. No sudo/apt install.
The HidenCloud ARM64 install path remains unchanged.
"""
from __future__ import annotations

import ctypes
import hashlib
import json
import lzma
import os
from pathlib import Path
import platform
import secrets
import shutil
import socket
import string
import subprocess
import sys
import tempfile
import time
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent.parent
RUNTIME = ROOT / ".tgll-runtime"
PREFIX = RUNTIME / "altare-amd64"
PKGROOT = PREFIX / "root"
CACHE = PREFIX / "cache"
BIN_XVFB = PKGROOT / "usr/bin/Xvfb"
BIN_VNC = PKGROOT / "usr/bin/x11vnc"
XKBCOMP = PKGROOT / "usr/bin/xkbcomp"
XKB_DATA = PKGROOT / "usr/share/X11/xkb"
SHIM = PREFIX / "xkb-shim.so"
VNC_DIR = RUNTIME / "vnc"
PASSWD = VNC_DIR / "passwd"
DISPLAY_PASSWORD = VNC_DIR / "password-display.txt"
INDEX = "https://deb.debian.org/debian/dists/bookworm/main/binary-amd64/Packages.xz"
# Install directly in the private prefix. Existing host libraries remain intact.
PACKAGES = (
    "xvfb", "xserver-common", "x11-xkb-utils", "xkb-data", "libxkbfile1",
    "libunwind8", "libxfont2", "libfontenc1", "libpixman-1-0",
    "libxau6", "libxdmcp6", "libbsd0", "libmd0",
    "x11vnc", "libvncserver1", "libvncclient1",
    "libavahi-client3", "libavahi-common3", "libxtst6",
    "libxdamage1", "liblzo2-2", "libxinerama1",
    "libxi6", "libxrandr2", "libxfixes3", "libxext6",
    "libx11-6", "libx11-xcb1", "libxcb1", "libxcb-shm0", "libxcb-dri2-0",
    "libxcb-dri3-0", "libxcb-glx0", "libxcb-present0", "libxcb-sync1",
    "libxcb-xfixes0", "libxcb-randr0", "libxcb-render0", "libxcb-shape0",
    "libxcb-xkb1", "libxshmfence1", "libxxf86vm1",
    "libgl1", "libglx0", "libglx-mesa0", "libglapi-mesa",
    "libegl1", "libegl-mesa0", "libgbm1", "libgl1-mesa-dri",
    "libdrm2", "libdrm-common", "libdrm-amdgpu1", "libdrm-nouveau2",
    "libdrm-radeon1", "libdrm-intel1", "libpciaccess0",
    "libllvm15", "libstdc++6", "libgcc-s1", "libzstd1", "libz3-4",
    "libffi8", "libexpat1", "libedit2", "libxml2", "liblzma5",
    "libgcrypt20", "libgpg-error0", "libsystemd0", "liblz4-1",
    "libselinux1", "libpcre2-8-0",
    "libjpeg62-turbo", "libpng16-16", "libgnutls30",
    "libnettle8", "libhogweed6", "libp11-kit0", "libtasn1-6",
    "libidn2-0", "libunistring2", "libgmp10",
    "libtinfo6", "libxrender1", "libxcomposite1", "libxcursor1",
    "libfreetype6", "libfontconfig1", "libbrotli1", "libuuid1",
    "libglvnd0", "libaudit1", "libcap-ng0", "zlib1g",
)

def log(message):
    print("[altare-native] " + str(message), flush=True)

def sha256(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

def environment(display=None, for_xvfb=False):
    env = os.environ.copy()
    dirs = [PKGROOT / "usr/lib/x86_64-linux-gnu",
            PKGROOT / "lib/x86_64-linux-gnu", PKGROOT / "usr/lib",
            PKGROOT / "lib"]
    env["LD_LIBRARY_PATH"] = os.pathsep.join(
        [str(p) for p in dirs if p.is_dir()] +
        ([env["LD_LIBRARY_PATH"]] if env.get("LD_LIBRARY_PATH") else []))
    env["PATH"] = str(PKGROOT / "usr/bin") + os.pathsep + env.get("PATH", "")
    env["LIBGL_ALWAYS_SOFTWARE"] = "1"
    env["GALLIUM_DRIVER"] = "llvmpipe"
    env["LIBGL_DRIVERS_PATH"] = str(PKGROOT / "usr/lib/x86_64-linux-gnu/dri")
    env["__EGL_VENDOR_LIBRARY_FILENAMES"] = str(
        PKGROOT / "usr/share/glvnd/egl_vendor.d/50_mesa.json")
    env["XKB_CONFIG_ROOT"] = str(XKB_DATA)
    xdg = PREFIX / "xdg-runtime"
    xdg.mkdir(parents=True, exist_ok=True)
    xdg.chmod(0o700)
    env["XDG_RUNTIME_DIR"] = str(xdg)
    if display:
        env["DISPLAY"] = display
    if for_xvfb:
        env["TGLL_XKBCOMP_PATH"] = str(XKBCOMP)
        env["LD_PRELOAD"] = str(SHIM) + (
            ":" + env["LD_PRELOAD"] if env.get("LD_PRELOAD") else "")
    else:
        env.pop("TGLL_XKBCOMP_PATH", None)
        env.pop("LD_PRELOAD", None)
    return env

def package_index():
    log("Reading official Debian Bookworm amd64 package index")
    CACHE.mkdir(parents=True, exist_ok=True)
    cache = CACHE / "Packages-amd64.xz"
    # Refresh on every setup to reject stale or no longer hosted filenames.
    req = Request(INDEX, headers={"User-Agent": "TGLL-Altare-Installer/1.0",
                                  "Accept-Encoding": "identity"})
    with urlopen(req, timeout=90) as response:
        data = response.read(24 * 1024 * 1024 + 1)
    if len(data) > 24 * 1024 * 1024:
        raise RuntimeError("Debian package index exceeds allowed size")
    plain = lzma.decompress(data, memlimit=256 * 1024 * 1024)
    if len(plain) > 150 * 1024 * 1024:
        raise RuntimeError("Debian package index expanded too far")
    desired = set(PACKAGES)
    packages = {}
    for section in plain.decode("utf-8", "replace").split("\n\n"):
        if not section.startswith("Package: "):
            continue
        name = section.split("\n", 1)[0][9:]
        if name not in desired:
            continue
        fields = {}
        for line in section.split("\n"):
            if ": " in line and not line.startswith(" "):
                k, v = line.split(": ", 1)
                fields[k] = v
        if fields.get("Architecture") not in ("amd64", "all"):
            continue
        fname, digest = fields.get("Filename", ""), fields.get("SHA256", "")
        size = int(fields.get("Size", "0"))
        if (not fname.startswith("pool/main/") or ".." in Path(fname).parts
            or len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest)
            or not 0 < size < 75 * 1024 * 1024):
            raise RuntimeError("Untrusted package index entry for " + name)
        packages[name] = (fname, digest, size)
    missing = desired - packages.keys()
    if missing:
        raise RuntimeError("Debian Bookworm packages unavailable: " + ", ".join(sorted(missing)))
    return packages

def install_packages():
    if platform.machine().lower() not in ("x86_64", "amd64"):
        raise RuntimeError("Altare native installer requires Linux x86_64")
    if platform.libc_ver()[1] != "2.36":
        log("WARNING: packages target Debian Bookworm glibc 2.36; verify compatibility")
    if not shutil.which("dpkg-deb"):
        raise RuntimeError("dpkg-deb missing")
    records = package_index()
    PKGROOT.mkdir(parents=True, exist_ok=True)
    for i, name in enumerate(PACKAGES, 1):
        fname, digest, size = records[name]
        archive = CACHE / Path(fname).name
        marker = PREFIX / ".installed" / (name + ".json")
        if marker.is_file() and BIN_XVFB.is_file():
            try:
                state = json.loads(marker.read_text())
                if state.get("sha256") == digest:
                    continue
            except (ValueError, OSError):
                pass
        if not archive.is_file() or sha256(archive) != digest:
            archive.unlink(missing_ok=True)
            tmp = archive.with_suffix(".part")
            try:
                req = Request("https://deb.debian.org/debian/" + fname.replace("+", "%2B"),
                              headers={"User-Agent": "TGLL-Altare-Installer/1.0"})
                with urlopen(req, timeout=75) as response, tmp.open("wb") as target:
                    downloaded = 0
                    for chunk in iter(lambda: response.read(1024 * 1024), b""):
                        downloaded += len(chunk)
                        if downloaded > size + 1024:
                            raise RuntimeError(name + " exceeded expected size")
                        target.write(chunk)
                if sha256(tmp) != digest:
                    raise RuntimeError(name + " SHA256 mismatch")
                tmp.replace(archive)
            finally:
                tmp.unlink(missing_ok=True)
        log(f"[{i}/{len(PACKAGES)}] {name}")
        subprocess.run(["dpkg-deb", "-x", str(archive), str(PKGROOT)],
                       check=True, timeout=90)
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text(json.dumps({"sha256": digest}), encoding="utf-8")
    for path in (BIN_XVFB, BIN_VNC, XKBCOMP, XKB_DATA / "rules/evdev"):
        if not path.exists():
            raise RuntimeError("Debian package extraction missing " + str(path))
    # Debian alternatives symlinks can point to absolute paths; don't modify /usr.
    log("Debian Xvfb, VNC, Mesa and keyboard assets extracted")

def compile_shim():
    sys.path.insert(0, str(ROOT / "scripts"))
    from install_display import EXEC_SHIM_C, ensure_local_socket_dir
    ensure_local_socket_dir()
    if SHIM.is_file():
        return
    src = PREFIX / "xkb-shim.c"
    src.write_text(EXEC_SHIM_C, encoding="utf-8")
    subprocess.run(["gcc", "-shared", "-fPIC", "-O2",
                    "-o", str(SHIM), str(src)], check=True, timeout=35)
    log("Rootless amd64 XKB helper compiled")

def check_deps():
    env = environment()
    for binary in (BIN_XVFB, BIN_VNC, XKBCOMP):
        result = subprocess.run(["ldd", str(binary)], env=env, text=True,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                timeout=25, check=False)
        missing = [line.strip() for line in result.stdout.splitlines()
                   if "not found" in line]
        if result.returncode or missing:
            raise RuntimeError(f"{binary.name} shared libraries missing:\n" +
                               "\n".join(missing or [result.stdout[-2000:]]))
    log("Native x86-64 display/VNC binary dependencies verified")

def smoke_display():
    for d in range(90, 100):
        if (not Path(f"/tmp/.X11-unix/X{d}").exists()
            and not Path(f"/tmp/.X{d}-lock").exists()):
            display = f":{d}"
            break
    else:
        raise RuntimeError("No unused display number :90..:99")
    output = PREFIX / "xvfb-smoke.log"
    with output.open("w") as f:
        proc = subprocess.Popen([str(BIN_XVFB), display, "-screen", "0",
                                 "640x480x24", "-nolisten", "tcp", "-noreset",
                                 "-xkbdir", str(XKB_DATA)],
                                env=environment(display, for_xvfb=True),
                                stdout=f, stderr=subprocess.STDOUT,
                                stdin=subprocess.DEVNULL)
    try:
        for i in range(40):
            if proc.poll() is not None:
                break
            if Path(f"/tmp/.X11-unix/X{d}").is_socket():
                log(f"Xvfb smoke test passed at {display}")
                return
            time.sleep(0.25)
        raise RuntimeError("Xvfb did not create socket: " +
                           output.read_text(errors="replace")[-2500:])
    finally:
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=4)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()

def install_wine():
    sys.path.insert(0, str(ROOT / "scripts"))
    from install_wine import DEST, download, extract
    if not (DEST / "bin/wine").is_file():
        log("Downloading and verifying upstream Wine 11.19 amd64 WOW64")
        extract(download())
    wine = DEST / "bin/wine"
    result = subprocess.run([str(wine), "--version"], env=environment(),
                            capture_output=True, text=True, timeout=45, check=False)
    if result.returncode:
        raise RuntimeError("Native Wine version check failed: " +
                           (result.stdout + result.stderr)[-2200:])
    log("Native " + result.stdout.strip() + " works")

def set_password():
    if not BIN_VNC.is_file():
        raise RuntimeError("Run setup native first")
    VNC_DIR.mkdir(parents=True, exist_ok=True)
    VNC_DIR.chmod(0o700)
    password = "".join(secrets.choice(string.ascii_letters + string.digits)
                       for _ in range(8))
    tmp = VNC_DIR / "passwd.tmp"
    tmp.unlink(missing_ok=True)
    try:
        result = subprocess.run([str(BIN_VNC), "-norc", "-storepasswd",
                                 password, str(tmp)], env=environment(),
                                capture_output=True, text=True, timeout=25)
        if result.returncode or not tmp.is_file():
            raise RuntimeError("Failed to create VNC password: " + result.stderr[-800:])
        tmp.chmod(0o600)
        tmp.replace(PASSWD)
    finally:
        tmp.unlink(missing_ok=True)
    with os.fdopen(os.open(str(DISPLAY_PASSWORD), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "w", encoding="utf-8") as stream:
        stream.write(password + "\n")
    DISPLAY_PASSWORD.chmod(0o600)
    log("VNC password: " + password)
    log("VNC traffic is NOT encrypted; keep the password private")

def main():
    command = sys.argv[1] if len(sys.argv) > 1 else "install"
    if command == "password":
        set_password()
        return
    if command != "install":
        raise ValueError("Usage: native_setup.py [install|password]")
    RUNTIME.mkdir(parents=True, exist_ok=True)
    log("Installing native x86_64 graphics/VNC/Wine (no Box64, no root)")
    install_packages()
    compile_shim()
    check_deps()
    smoke_display()
    install_wine()
    log("SUCCESS: Altare native runtime installed; upload TGLL ZIP if needed")
    log("Next: vnc-password, vnc-public on <allocated TCP port>, start")

if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        log(f"FAILED: {type(error).__name__}: {error}")
        raise SystemExit(1)
