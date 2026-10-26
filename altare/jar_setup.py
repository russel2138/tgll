#!/usr/bin/env python3
"""Install a rootless Java ME runtime on Altare without touching Wine/TGLL.

Java 17 (Temurin) + MicroEmulator 2.0.4 follow russel2138/test.
Uses the existing native x86-64 package runtime for dependencies and TigerVNC,\nwithout launching Xvfb/x11vnc and without installing Wine.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tarfile
import tempfile
from urllib.parse import urlparse
from urllib.request import Request, urlopen
import zipfile

from native_setup import (ROOT, RUNTIME, BIN_XVFB, BIN_VNC, SHIM,
                          XKB_DATA, install_packages, compile_shim,
                          check_deps, smoke_display, environment)

BASE = RUNTIME / "jar-runtime"
JRE = BASE / "java17"
MICROEMU = BASE / "microemu"
GAME = ROOT / "game.jar"
STATE = BASE / "state"
META_URL = ("https://api.adoptium.net/v3/assets/latest/17/hotspot?"
            "architecture=x64&image_type=jre&jvm_impl=hotspot&os=linux&vendor=eclipse")
MICROEMU_URL = ("https://downloads.sourceforge.net/project/microemulator/"
                "microemulator/2.0.4/microemulator-2.0.4.zip")
DEFAULT_GAME_URL = "https://raw.githubusercontent.com/russel2138/test/main/game.jar"
MAX_JRE = 130 * 1024 * 1024
MAX_EMU = 30 * 1024 * 1024
MAX_GAME = 25 * 1024 * 1024

def log(message):
    print("[altare-jar] " + str(message), flush=True)

def download(url, destination, maximum, expected_sha256=None):
    if urlparse(url).scheme != "https":
        raise RuntimeError("Only HTTPS downloads allowed")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(destination.name + ".part")
    try:
        request = Request(url, headers={"User-Agent": "TGLL-Altare-J2ME/1.0"})
        with urlopen(request, timeout=85) as response, temporary.open("wb") as target:
            total = 0
            digest = hashlib.sha256()
            for chunk in iter(lambda: response.read(1024 * 1024), b""):
                total += len(chunk)
                if total > maximum:
                    raise RuntimeError("Download exceeded size limit: " + url)
                target.write(chunk)
                digest.update(chunk)
        if expected_sha256 and digest.hexdigest().lower() != expected_sha256.lower():
            raise RuntimeError("SHA256 mismatch: refusing " + url)
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)
    return destination

def safe_extract_tar(archive, destination):
    with tarfile.open(archive, "r:gz") as tf:
        members = tf.getmembers()
        if len(members) > 12000 or sum(x.size for x in members if x.isfile()) > 420 * 1024 * 1024:
            raise RuntimeError("JRE archive has unexpected size")
        for x in members:
            if (x.name.startswith("/") or ".." in Path(x.name).parts or x.isdev()):
                raise RuntimeError("Unsafe path/link in Java archive: " + x.name)
        tf.extractall(destination, filter="data")

def java_ready():
    java = JRE / "bin/java"
    if not java.is_file():
        return False
    result = subprocess.run([str(java), "-version"], capture_output=True, text=True,
                            timeout=15, check=False, env=environment())
    if result.returncode == 0 and 'version "17.' in result.stderr:
        return True
    return False

def install_java():
    if java_ready():
        log("Portable Java 17 already installed")
        return
    log("Fetching Temurin 17 JRE metadata (no system Java required)")
    req = Request(META_URL, headers={"User-Agent": "TGLL-Altare-J2ME/1.0"})
    with urlopen(req, timeout=45) as res:
        data = res.read(2 * 1024 * 1024 + 1)
    if len(data) > 2 * 1024 * 1024:
        raise RuntimeError("JRE metadata too large")
    assets = json.loads(data)
    if not isinstance(assets, list) or not assets:
        raise RuntimeError("No Temurin Java 17 JRE x64 build returned")
    package = assets[0]["binary"]["package"]
    url = package["link"]
    digest = package["checksum"]
    if not (urlparse(url).hostname in ("github.com", "api.adoptium.net")
            and len(digest) == 64 and all(c in "0123456789abcdefABCDEF" for c in digest)):
        raise RuntimeError("Unexpected Java package URL/checksum")
    BASE.mkdir(parents=True, exist_ok=True)
    archive = BASE / "java17.tar.gz"
    log("Downloading SHA256-verified Temurin JRE 17")
    download(url, archive, MAX_JRE, digest)
    with tempfile.TemporaryDirectory(prefix="jar-jre-", dir=BASE) as tmp:
        stage = Path(tmp)
        safe_extract_tar(archive, stage)
        java_bins = [p for p in stage.rglob("bin/java") if p.is_file()]
        if len(java_bins) != 1:
            raise RuntimeError("Expected one JRE bin/java in archive")
        extracted_root = java_bins[0].parent.parent
        if JRE.exists():
            shutil.rmtree(JRE)
        shutil.move(str(extracted_root), str(JRE))
    archive.unlink(missing_ok=True)
    if not java_ready():
        raise RuntimeError("Java 17 cannot run on this Altare container")
    log("Temurin Java 17 is ready")

def install_microemu():
    jar = MICROEMU / "microemulator.jar"
    if jar.is_file() and zipfile.is_zipfile(jar):
        log("MicroEmulator already installed")
        return
    BASE.mkdir(parents=True, exist_ok=True)
    archive = BASE / "microemulator-2.0.4.zip"
    log("Downloading MicroEmulator 2.0.4 as in russel2138/test")
    download(MICROEMU_URL, archive, MAX_EMU)
    with tempfile.TemporaryDirectory(prefix="jar-emu-", dir=BASE) as tmp:
        stage = Path(tmp)
        with zipfile.ZipFile(archive) as bundle:
            members = bundle.infolist()
            if len(members) > 3000 or sum(m.file_size for m in members) > 130 * 1024 * 1024:
                raise RuntimeError("MicroEmulator archive size invalid")
            for member in members:
                path = Path(member.filename)
                if (path.is_absolute() or ".." in path.parts or
                    "\\" in member.filename or ":" in member.filename):
                    raise RuntimeError("Unsafe MicroEmulator zip member")
                if member.is_dir():
                    continue
                destination = stage.joinpath(*path.parts)
                destination.parent.mkdir(parents=True, exist_ok=True)
                with bundle.open(member) as src, destination.open("wb") as dst:
                    shutil.copyfileobj(src, dst, 1024 * 1024)
        matches = [p for p in stage.rglob("microemulator.jar") if p.is_file()]
        if len(matches) != 1 or not zipfile.is_zipfile(matches[0]):
            raise RuntimeError("MicroEmulator main jar missing/invalid")
        with zipfile.ZipFile(matches[0]) as mainjar:
            if "org/microemu/app/Main.class" not in mainjar.namelist():
                raise RuntimeError("Downloaded MicroEmulator lacks expected main class")
        if MICROEMU.exists():
            shutil.rmtree(MICROEMU)
        shutil.move(str(matches[0].parent), str(MICROEMU))
    archive.unlink(missing_ok=True)
    log("MicroEmulator 2.0.4 is ready")

def parse_midlet(jar):
    if not jar.is_file() or not zipfile.is_zipfile(jar) or jar.stat().st_size > MAX_GAME:
        raise RuntimeError("game.jar missing or invalid JAR. Upload your Java ME game.jar")
    with zipfile.ZipFile(jar) as z:
        manifest = z.read("META-INF/MANIFEST.MF").decode("utf-8", "replace")
    # JAR manifest long lines may be folded, with subsequent line starting space.
    manifest = manifest.replace("\r\n ", "").replace("\n ", "")
    for line in manifest.splitlines():
        if line.lower().startswith("midlet-1:"):
            klass = line.partition(":")[2].rsplit(",", 1)[-1].strip()
            if klass and all(c.isalnum() or c in "_.$" for c in klass):
                return klass, manifest
    raise RuntimeError("Missing valid MIDlet-1 in game.jar manifest: not a J2ME game")

def ensure_game():
    if not GAME.is_file():
        log("No local game.jar; downloading the default from your russel2138/test repository")
        download(DEFAULT_GAME_URL, GAME, MAX_GAME)
    klass, manifest = parse_midlet(GAME)
    STATE.mkdir(parents=True, exist_ok=True)
    (STATE / "game-manifest.jad").write_text(manifest + "\n", encoding="utf-8")
    log(f"Java ME MIDlet: {klass} ({GAME.stat().st_size // 1024} KiB)")
    return klass

def ensure_display():
    from native_setup import PKGROOT
    font = PKGROOT / "usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
    ready = all(path.exists() for path in
                (BIN_XVFB, BIN_VNC, SHIM, XKB_DATA / "rules/evdev", font))
    if not ready:
        log("Preparing Xvfb/VNC and real TrueType fonts (no Wine install)")
        install_packages(extra_packages=("fontconfig-config", "fonts-dejavu-core",
                                         "fontconfig", "libharfbuzz0b",
                                         "libgraphite2-3"))
        compile_shim()
        check_deps()
        smoke_display()
        if not font.is_file():
            raise RuntimeError("No font files after extraction")
    else:
        log("Reusing Altare Xvfb/VNC and font runtime")

def ensure_tiger():
    """Install TigerVNC for Java ME or fail clearly. No fallback."""
    from jar_tigervnc import ORIGINAL, EXTRA_PACKAGES, prepare_tiger
    if not ORIGINAL.is_file():
        log("Installing TigerVNC rootlessly (required for Java ME)")
        install_packages(extra_packages=EXTRA_PACKAGES)
    prepare_tiger()


def main():
    if platform.machine().lower() not in ("x86_64", "amd64"):
        raise RuntimeError("Altare JAR runtime requires Linux x86_64")
    BASE.mkdir(parents=True, exist_ok=True)
    ensure_display()
    install_java()
    install_microemu()
    ensure_game()
    ensure_tiger()
    log("SUCCESS: Java ME + TigerVNC runtime installed; TGLL/Wine files untouched")
    log("Next: start (existing VNC password and TCP port are retained)")

if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        log(f"FAILED: {type(error).__name__}: {error}")
        raise SystemExit(1)
