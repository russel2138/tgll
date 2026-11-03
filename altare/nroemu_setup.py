#!/usr/bin/env python3
"""Install the Java desktop NRO Emulator V2 from the owner's archived EXE.

Launch4j wraps an executable JAR as a PE file. Rebuild a normal JAR without
running the Windows executable or touching Java ME/other game installations.
"""
from __future__ import annotations

import hashlib
import io
import os
from pathlib import Path
import re
from shutil import copyfileobj
import tempfile
from urllib.request import Request, urlopen
import zipfile

from native_setup import ROOT, RUNTIME
from jar_setup import JRE

ARCHIVE_NAME = "NRO EMULATOR V2.zip"
ARCHIVE = ROOT / ARCHIVE_NAME
SOURCE_COMMIT = "01c610bb91c09a23a54e194e92edf602d6f8864f"
SOURCE_URL = (
    "https://raw.githubusercontent.com/russel2138/tgll/" + SOURCE_COMMIT +
    "/NRO%20EMULATOR%20V2.zip"
)
SOURCE_SIZE = 79035404
SOURCE_SHA256 = "36296b7b569e64ac254cb4823c6574998500392027e828400d12dac8cd59314f"
EXE_NAME = "NRO EMULATOR.exe"
MAIN_CLASS = "com.dragonboy.desktop.DesktopLauncher"
WORK = RUNTIME / "nroemu"
TARGET = WORK / "nro-emulator-v2.jar"
SOURCE_MARKER = WORK / "source-sha256.txt"
MAX_EMBEDDED_FILES = 8000
MAX_EMBEDDED_BYTES = 250 * 1024 * 1024


def say(message: str) -> None:
    print("[nroemu-setup] " + str(message), flush=True)


def sha256(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            hasher.update(block)
    return hasher.hexdigest()


def verify_archive(path: Path) -> None:
    if path.stat().st_size != SOURCE_SIZE or sha256(path) != SOURCE_SHA256:
        raise RuntimeError("NRO Emulator V2 ZIP differs from inspected GitHub commit")
    with zipfile.ZipFile(path) as archive:
        names = set(archive.namelist())
        if EXE_NAME not in names:
            raise RuntimeError("NRO Emulator V2 ZIP missing " + EXE_NAME)
        info = archive.getinfo(EXE_NAME)
        if info.file_size > 70 * 1024 * 1024 or info.flag_bits & 1:
            raise RuntimeError("Unexpected EXE size or ZIP encryption")


def obtain_archive() -> Path:
    if ARCHIVE.is_file():
        verify_archive(ARCHIVE)
        say("Found and verified local source ZIP")
        return ARCHIVE
    say("Downloading exact NRO Emulator V2 ZIP from pinned GitHub commit")
    WORK.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(prefix=".nroemu-download-", suffix=".zip",
                                     dir=WORK, delete=False) as f:
        temporary = Path(f.name)
        try:
            req = Request(SOURCE_URL, headers={"User-Agent": "Altare-NROEmu/1.0"})
            with urlopen(req, timeout=150) as response:
                if not response.geturl().startswith("https://"):
                    raise RuntimeError("Refusing non-HTTPS ZIP download redirect")
                received = 0
                while True:
                    block = response.read(1024 * 1024)
                    if not block:
                        break
                    received += len(block)
                    if received > SOURCE_SIZE:
                        raise RuntimeError("Downloaded ZIP exceeds expected size")
                    f.write(block)
            verify_archive(temporary)
            # The ZIP is an immutable source artifact. Keep it for future
            # re-installations but do not overwrite user files on Altare.
            os.replace(temporary, ARCHIVE)
        finally:
            temporary.unlink(missing_ok=True)
    say("Verified source ZIP SHA256: " + SOURCE_SHA256)
    return ARCHIVE


def rebuild_embedded_jar(exe_path: Path, jar_path: Path) -> None:
    """ZipFile understands Launch4j's PE prefix; write only ZIP members."""
    with zipfile.ZipFile(exe_path) as source:
        infos = source.infolist()
        if not 1 <= len(infos) <= MAX_EMBEDDED_FILES:
            raise RuntimeError("Unexpected number of embedded Java members")
        if any(x.flag_bits & 1 for x in infos):
            raise RuntimeError("Embedded Java archive contains encrypted files")
        if sum(x.file_size for x in infos) > MAX_EMBEDDED_BYTES:
            raise RuntimeError("Embedded Java content exceeds allowed size")
        manifest = source.read("META-INF/MANIFEST.MF").decode("utf-8", "replace")
        if not re.search(r"(?im)^Main-Class:\s*com\.dragonboy\.desktop\.DesktopLauncher\s*$", manifest):
            raise RuntimeError("Embedded JAR has unexpected Main-Class")
        required = (
            "com/dragonboy/desktop/DesktopLauncher.class",
            "com/badlogic/gdx/backends/lwjgl3/Lwjgl3Application.class",
            "linux/x64/org/lwjgl/glfw/libglfw.so",
            "linux/x64/org/lwjgl/liblwjgl.so",
            "libgdx64.so",
        )
        if any(name not in source.namelist() for name in required):
            raise RuntimeError("Embedded JAR is missing required Linux native libraries")
        with zipfile.ZipFile(jar_path, "w", allowZip64=True) as output:
            for info in infos:
                # Preserve member names, manifest, resource data and metadata;
                # do not extract third-party files into an arbitrary directory.
                if info.is_dir():
                    output.writestr(info, b"")
                else:
                    with source.open(info) as src, output.open(info, "w", force_zip64=True) as dest:
                        copyfileobj(src, dest, length=1024 * 1024)
    with zipfile.ZipFile(jar_path) as output:
        if output.testzip() is not None:
            raise RuntimeError("Rebuilt JAR failed CRC check")
    say(f"Rebuilt Linux-runnable JAR ({jar_path.stat().st_size // 1024**2} MiB)")


def install() -> None:
    WORK.mkdir(parents=True, exist_ok=True)
    if TARGET.is_file() and SOURCE_MARKER.is_file():
        if SOURCE_MARKER.read_text(encoding="ascii").strip() == SOURCE_SHA256:
            with zipfile.ZipFile(TARGET) as existing:
                if MAIN_CLASS in existing.read("META-INF/MANIFEST.MF").decode("utf-8", "replace"):
                    say("NRO Emulator V2 JAR already extracted; preserving data")
                    return
    archive = obtain_archive()
    with tempfile.TemporaryDirectory(prefix=".nroemu-stage-", dir=WORK) as folder:
        staging = Path(folder)
        exe = staging / EXE_NAME
        with zipfile.ZipFile(archive) as outer, outer.open(EXE_NAME) as stream, exe.open("wb") as output:
            copyfileobj(stream, output, length=1024 * 1024)
        jar = staging / "nro-emulator-v2.jar"
        rebuild_embedded_jar(exe, jar)
        os.replace(jar, TARGET)
    SOURCE_MARKER.write_text(SOURCE_SHA256 + "\n", encoding="ascii")
    java = JRE / "bin/java"
    if not java.is_file():
        say("Java 17 not found. Use 'setup jar' if Java ME installer is already configured.")
        say("You can also install a native Linux JRE 17+ before running 'start'.")
    say("SUCCESS: NRO Emulator V2 JAR ready. Select 'game-select nroemu' then 'start'.")
    say("Wine, QLTK, and MicroEmulator are not used by this profile.")


if __name__ == "__main__":
    try:
        install()
    except Exception as error:
        say(f"FAILED: {type(error).__name__}: {error}")
        raise SystemExit(1)
