#!/usr/bin/env python3
"""Build Box64 on HidenCloud Linux ARM64 without root or GNU Make."""
from __future__ import annotations

import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import traceback

ROOT = Path(__file__).resolve().parent.parent
RUNTIME = ROOT / ".tgll-runtime"
SITE = RUNTIME / "build-tools"
SOURCE = RUNTIME / "sources" / "box64"
BUILD = RUNTIME / "build" / "box64"
PREFIX = RUNTIME / "box64"
RESULT = RUNTIME / "box64-setup.result"


def log(message):
    print(message, flush=True)


def run(args, *, cwd=None, env=None):
    log("$ " + " ".join(str(part) for part in args))
    subprocess.run(
        [str(part) for part in args], cwd=cwd,
        env=env, check=True,
    )


def find_tool(name):
    local = SITE / "bin" / name
    return str(local) if local.is_file() else shutil.which(name)


def install_build_tools():
    cmake, ninja = find_tool("cmake"), find_tool("ninja")
    if cmake and ninja:
        return cmake, ninja
    SITE.mkdir(parents=True, exist_ok=True)
    log("Installing CMake and Ninja in user-writable folder (no sudo)")
    run([
        sys.executable, "-m", "pip", "install",
        "--disable-pip-version-check", "--no-input",
        "--upgrade", "--target", str(SITE), "cmake", "ninja",
    ])
    cmake, ninja = find_tool("cmake"), find_tool("ninja")
    if not cmake or not ninja:
        raise RuntimeError("pip completed but CMake/Ninja executables were not found")
    return cmake, ninja


def install():
    log("TGLL Box64 installer")
    log(f"CPU architecture: {platform.machine()}")
    if platform.machine().lower() not in ("aarch64", "arm64"):
        raise RuntimeError("This Box64 build recipe is only for Linux ARM64")
    for name in ("git", "gcc", "g++"):
        if not shutil.which(name):
            raise RuntimeError(f"Missing prerequisite: {name}")
    if not shutil.which("git"):
        raise RuntimeError("Git not found")
    RUNTIME.mkdir(parents=True, exist_ok=True)
    built_binary = BUILD / "box64"
    env = os.environ.copy()

    if built_binary.is_file():
        log(f"Found previously compiled Box64: {built_binary}")
        log("Skipping compilation; the previous attempt failed only at CMake install")
    else:
        cmake, _ = install_build_tools()
        env["PYTHONPATH"] = str(SITE) + os.pathsep + env.get("PYTHONPATH", "")
        env["PATH"] = str(SITE / "bin") + os.pathsep + env.get("PATH", "")

        SOURCE.parent.mkdir(parents=True, exist_ok=True)
        if (SOURCE / ".git").is_dir():
            log("Box64 source already exists, reusing it")
        elif SOURCE.exists():
            raise RuntimeError(f"Source directory exists but is not a git repo: {SOURCE}")
        else:
            run(["git", "clone", "--depth", "1",
                 "https://github.com/ptitSeb/box64.git", str(SOURCE)])
        BUILD.mkdir(parents=True, exist_ok=True)
        run([
            cmake, "-S", str(SOURCE), "-B", str(BUILD),
            "-G", "Ninja",
            "-DARM64=ON", "-DARM_DYNAREC=ON",
            "-DCMAKE_BUILD_TYPE=Release",
            "-DCMAKE_INSTALL_PREFIX=" + str(PREFIX),
            "-DNO_CONF_INSTALL=ON",
        ], env=env)
        run([cmake, "--build", str(BUILD), "--parallel", "2"], env=env)

    if not built_binary.is_file():
        raise RuntimeError(f"Compiled Box64 binary not found: {built_binary}")

    # Do NOT run 'cmake --install': upstream also targets /usr/lib, which the
    # unprivileged HidenCloud container cannot write. Box64 can be launched
    # from its standalone binary without installing system-wide files.
    destination = PREFIX / "bin"
    destination.mkdir(parents=True, exist_ok=True)
    binary = destination / "box64"
    shutil.copy2(built_binary, binary)
    binary.chmod(binary.stat().st_mode | 0o111)
    run([binary, "-v"], env=env)
    log(f"SUCCESS: Box64 installed at {binary}")
    log("Box64 alone cannot run TGLL.exe; Wine64 and display support are not installed.")


def main():
    try:
        install()
    except Exception as error:
        RESULT.write_text("FAILED: " + str(error), encoding="utf-8")
        log(f"FAILED: {error}")
        traceback.print_exc()
        raise SystemExit(1)
    else:
        RESULT.write_text("SUCCESS", encoding="utf-8")


if __name__ == "__main__":
    main()
