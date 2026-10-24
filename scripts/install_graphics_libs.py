#!/usr/bin/env python3
"""Install only missing native ARM64 X11/EGL libraries for Box64/Wine.

Debian Bookworm ARM64 package metadata is fetched over HTTPS; each .deb is
SHA256 checked against the authoritative Packages.xz index before extraction
into an isolated local prefix. Host system libraries are left untouched.
"""
from __future__ import annotations

import ctypes
import lzma
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import urllib.request

from install_display import ROOT, RUNTIME, INDEX_URL, download

PREFIX = RUNTIME / "graphics-native"
LIBDIR = PREFIX / "usr" / "lib" / "aarch64-linux-gnu"
MAX_INDEX_COMPRESSED = 25 * 1024 * 1024
MAX_INDEX_UNPACKED = 130 * 1024 * 1024
MAX_DEB_BYTES = 12 * 1024 * 1024

# The first four are exactly what the failed TGLL Wine log reported.
# Remaining packages are direct runtime dependencies of xkbregistry/EGL.
PACKAGES = (
    "libxinerama1", "libxcomposite1", "libxkbregistry0", "libegl1",
    "libxkbcommon0", "libglvnd0", "libegl-mesa0",
)
SONAMES = (
    "libXinerama.so.1", "libXcomposite.so.1",
    "libxkbregistry.so.0", "libEGL.so.1",
)
# Other native libs might already exist in the container. We do not
# overwrite Mesa drivers or glibc packages speculatively.
POSSIBLE_MORE = (
    "libEGL_mesa.so.0", "libxkbcommon.so.0", "libGL.so.1",
)


def log(line):
    print(line, flush=True)


def package_records():
    log("Fetching Debian Bookworm ARM64 package metadata...")
    request = urllib.request.Request(INDEX_URL, headers={
        "User-Agent": "TGLL-graphics/1.0",
        "Accept-Encoding": "identity",
    })
    with urllib.request.urlopen(request, timeout=70) as response:
        compressed = response.read(MAX_INDEX_COMPRESSED + 1)
    if len(compressed) > MAX_INDEX_COMPRESSED:
        raise RuntimeError("Debian Packages.xz unexpectedly large")
    data = lzma.decompress(compressed, memlimit=256 * 1024 * 1024)
    if len(data) > MAX_INDEX_UNPACKED:
        raise RuntimeError("Decompressed package metadata exceeds limit")
    selected = {}
    for block in data.decode("utf-8", errors="replace").split("\n\n"):
        if not block.startswith("Package: "):
            continue
        name = block.partition("\n")[0][len("Package: "):].strip()
        if name not in PACKAGES:
            continue
        fields = {}
        for row in block.splitlines():
            if ": " in row and not row.startswith((" ", "\t")):
                key, value = row.split(": ", 1)
                fields[key] = value
        if fields.get("Architecture") not in ("arm64", "all"):
            continue
        filename = fields.get("Filename", "")
        digest = fields.get("SHA256", "")
        try:
            size = int(fields.get("Size", "0"))
        except ValueError as exc:
            raise RuntimeError("Invalid Debian package size") from exc
        if (not filename.startswith("pool/main/") or ".." in Path(filename).parts
            or len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest)
            or size <= 0 or size > MAX_DEB_BYTES):
            raise RuntimeError(f"Unsafe Debian package metadata for {name}")
        selected[name] = (
            Path(filename).name,
            "https://deb.debian.org/debian/" + filename.replace("+", "%2B"),
            digest,
            size + 1024,
        )
    missing = sorted(set(PACKAGES) - set(selected))
    if missing:
        raise RuntimeError("Missing package metadata: " + ", ".join(missing))
    log("Found 7 official arm64 packages and SHA256 checksums")
    return selected


def env_for_game_graphics(base=None):
    env = (base or os.environ).copy()
    paths = [PREFIX / "usr/lib/aarch64-linux-gnu",
             PREFIX / "lib/aarch64-linux-gnu",
             PREFIX / "usr/lib", PREFIX / "lib"]
    additions = [str(path) for path in paths if path.is_dir()]
    if additions:
        env["LD_LIBRARY_PATH"] = os.pathsep.join(additions + (
            [env["LD_LIBRARY_PATH"]] if env.get("LD_LIBRARY_PATH") else []
        ))
    env["LIBGL_ALWAYS_SOFTWARE"] = "1"
    return env


def add_unversioned_aliases():
    """Some Box64 wrappers dlopen libXinerama.so (without the .1 suffix).

    Debian runtime .deb files usually ship only versioned SONAME symlinks.
    Supply private aliases without modifying /usr/lib or any host paths.
    """
    for name, soname in (
        ("libXinerama.so", "libXinerama.so.1"),
        ("libXcomposite.so", "libXcomposite.so.1"),
        ("libxkbregistry.so", "libxkbregistry.so.0"),
        ("libEGL.so", "libEGL.so.1"),
    ):
        source = LIBDIR / soname
        alias = LIBDIR / name
        if not source.is_file():
            raise RuntimeError(f"Missing extracted library: {source}")
        if alias.is_symlink() or alias.exists():
            continue
        alias.symlink_to(soname)
        log(f"Created private Box64 wrapper alias: {name} -> {soname}")


def inspect_elf_dependencies(env):
    if not LIBDIR.is_dir():
        raise RuntimeError("Graphics native library directory missing")
    log("--- Checking ARM64 native graphics libraries with dynamic loader ---")
    probe = (
        "import ctypes,sys\n"
        "all_ok=True\n"
        "for n in sys.argv[1:]:\n"
        " try:\n"
        "  ctypes.CDLL(n)\n"
        "  print('OK: '+n, flush=True)\n"
        " except OSError as e:\n"
        "  print('UNAVAILABLE: '+n+' : '+str(e),flush=True)\n"
        "  all_ok=False\n"
        "sys.exit(0 if all_ok else 2)\n"
    )
    result = subprocess.run(
        [sys.executable, "-u", "-c", probe, *SONAMES],
        env=env, capture_output=True, text=True,
        timeout=25, check=False,
    )
    log(result.stdout.strip())
    if result.stderr.strip():
        log(result.stderr[-1500:])
    if result.returncode:
        log("Native library dependencies incomplete; inspect the UNAVAILABLE lines")
        raise RuntimeError("At least one required ARM64 graphics library cannot be loaded")
    # Probe EGL Mesa separately, since GLX might already be functional without
    # every vendor-optional plugin required by EGL.
    optional = subprocess.run(
        [sys.executable, "-u", "-c",
         "import ctypes; ctypes.CDLL('libEGL_mesa.so.0')"],
        env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, timeout=20, check=False,
    )
    if optional.returncode:
        log("NOTE: EGL Mesa vendor library could not be dlopened; optional for GLX")
        log(optional.stdout[-1200:])
    else:
        log("Mesa EGL vendor library successfully loaded")
    log("SUCCESS: Required ARM64 X11/EGL libraries can be loaded")


def main():
    log(f"TGLL native graphics library bootstrap on {platform.machine()}")
    if platform.machine().lower() not in ("aarch64", "arm64"):
        raise RuntimeError("Only Debian ARM64 packages are supported")
    if not shutil.which("dpkg-deb"):
        raise RuntimeError("dpkg-deb missing")
    records = package_records()
    PREFIX.mkdir(parents=True, exist_ok=True)
    for name in PACKAGES:
        filename, url, digest, maximum = records[name]
        marker = PREFIX / ".installed" / (filename + ".ok")
        if marker.is_file() and marker.read_text().strip() == digest:
            log(f"Already extracted: {filename}")
            continue
        archive = download(filename, url, digest, maximum)
        log(f"Extracting {filename} into {PREFIX}")
        subprocess.run(["dpkg-deb", "--extract", str(archive), str(PREFIX)],
                       check=True, timeout=90)
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text(digest, encoding="ascii")
    add_unversioned_aliases()
    inspect_elf_dependencies(env_for_game_graphics())


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        log(f"FAILED: {type(error).__name__}: {error}")
        raise SystemExit(1)
