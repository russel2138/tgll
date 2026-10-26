#!/usr/bin/env python3
"""Rootless TigerVNC executable for the Altare Java ME runtime.

Uses the same xkbcomp relocation technique as russel2138/test's Raven/
Zampto/Ezonic runner, without touching an executable that is already running.
"""
from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import tempfile

from native_setup import PREFIX, PKGROOT, XKBCOMP, XKB_DATA, environment, log

ORIGINAL = PKGROOT / "usr/bin/Xtigervnc"
TIGER = PREFIX / "Xtigervnc-jar"
# Exactly the same length as /usr/bin; the Raven launcher uses this path too.
XKB_WRAPPER = Path("/tmp/xxx/xkbcomp")

EXTRA_PACKAGES = (
    "tigervnc-standalone-server",
    "tigervnc-common",
    "libpam0g",
    "xauth",
)


def prepare_tiger():
    if not ORIGINAL.is_file() or not XKBCOMP.is_file():
        raise RuntimeError("TigerVNC/XKB binaries missing; run setup jar")
    if not (XKB_DATA / "rules/evdev").is_file():
        raise RuntimeError("XKB data missing")

    # Unlike a system-wide /usr/bin, an unprivileged Altare container cannot
    # guarantee this location exists. Create a private helper that can be run
    # from the patched TigerVNC binary, matching the existing Raven technique.
    XKB_WRAPPER.parent.mkdir(parents=True, exist_ok=True)
    script = (
        "#!/bin/sh\n"
        + "exec " + '"' + str(XKBCOMP) + '" -I"' + str(XKB_DATA) + '" "$@"\n'
    )
    temp = XKB_WRAPPER.with_name("xkbcomp.tmp." + str(os.getpid()))
    try:
        temp.write_text(script, encoding="utf-8")
        temp.chmod(0o700)
        os.replace(temp, XKB_WRAPPER)
    finally:
        temp.unlink(missing_ok=True)

    data = ORIGINAL.read_bytes()
    # Match the working Raven/Zampto relocation: Xtigervnc may assemble
    # its xkbcomp command from a /usr/bin string plus the executable name.
    # Both prefixes are 8 bytes, so ELF offsets and lengths do not change.
    old, new = b"/usr/bin", b"/tmp/xxx"
    if old not in data or len(old) != len(new):
        raise RuntimeError("Unexpected TigerVNC XKB command path; cannot patch safely")
    data = data.replace(old, new)

    if TIGER.is_file() and TIGER.read_bytes() == data:
        pass
    else:
        with tempfile.NamedTemporaryFile(dir=PREFIX, prefix=".Xtigervnc-", delete=False) as f:
            temp_name = f.name
            f.write(data)
        try:
            os.chmod(temp_name, 0o700)
            os.replace(temp_name, TIGER)
        finally:
            if os.path.exists(temp_name):
                os.unlink(temp_name)

    p = subprocess.run(["ldd", str(TIGER)], env=environment(),
                       capture_output=True, text=True, timeout=20, check=False)
    if p.returncode or "not found" in p.stdout:
        raise RuntimeError("TigerVNC libraries missing: " + (p.stdout + p.stderr)[-2500:])
    log("TigerVNC executable prepared (Raven-compatible XKB helper)")
    return TIGER
