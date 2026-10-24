#!/usr/bin/env python3
"""Check native ARM64 OpenGL rendering on temporary rootless Xvfb.

This is a diagnostic, not a game launcher. A subprocess isolates GLX driver
crashes so they cannot take down the persistent HidenCloud app.py.
"""
from __future__ import annotations

import ctypes as C
import ctypes.util
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time

from install_display import (
    BIN, ROOT, RUNTIME, XKB_DATA, build_xkb_shim,
    ensure_local_socket_dir, env_for_display, probe_x11,
)


def say(message):
    print(message, flush=True)


def glx_probe():
    """Runs in a child process with DISPLAY configured."""
    x11_name = ctypes.util.find_library("X11")
    gl_name = ctypes.util.find_library("GL")
    say(f"ARM64 libX11: {x11_name or 'missing'}")
    say(f"ARM64 libGL: {gl_name or 'missing'}")
    if not x11_name or not gl_name:
        raise RuntimeError("Host is missing libX11.so or libGL.so")

    x11 = C.CDLL(x11_name)
    gl = C.CDLL(gl_name)
    x11.XOpenDisplay.argtypes = [C.c_char_p]
    x11.XOpenDisplay.restype = C.c_void_p
    x11.XCloseDisplay.argtypes = [C.c_void_p]
    x11.XCloseDisplay.restype = C.c_int
    x11.XDefaultScreen.argtypes = [C.c_void_p]
    x11.XDefaultScreen.restype = C.c_int
    x11.XFree.argtypes = [C.c_void_p]
    x11.XFree.restype = C.c_int

    gl.glXQueryVersion.argtypes = [C.c_void_p, C.POINTER(C.c_int), C.POINTER(C.c_int)]
    gl.glXQueryVersion.restype = C.c_int
    gl.glXChooseFBConfig.argtypes = [C.c_void_p, C.c_int, C.POINTER(C.c_int), C.POINTER(C.c_int)]
    gl.glXChooseFBConfig.restype = C.POINTER(C.c_void_p)
    gl.glXCreateNewContext.argtypes = [C.c_void_p, C.c_void_p, C.c_int, C.c_void_p, C.c_int]
    gl.glXCreateNewContext.restype = C.c_void_p
    gl.glXCreatePbuffer.argtypes = [C.c_void_p, C.c_void_p, C.POINTER(C.c_int)]
    gl.glXCreatePbuffer.restype = C.c_ulong
    gl.glXMakeContextCurrent.argtypes = [C.c_void_p, C.c_ulong, C.c_ulong, C.c_void_p]
    gl.glXMakeContextCurrent.restype = C.c_int
    gl.glXDestroyPbuffer.argtypes = [C.c_void_p, C.c_ulong]
    gl.glXDestroyContext.argtypes = [C.c_void_p, C.c_void_p]
    gl.glGetString.argtypes = [C.c_uint]
    gl.glGetString.restype = C.c_char_p

    display = x11.XOpenDisplay(os.environ.get("DISPLAY", ":90").encode())
    if not display:
        raise RuntimeError("XOpenDisplay failed")
    pbuffer = 0
    context = None
    configs = None
    try:
        major, minor = C.c_int(), C.c_int()
        if not gl.glXQueryVersion(display, C.byref(major), C.byref(minor)):
            raise RuntimeError("GLX extension unavailable in Xvfb")
        say(f"GLX version: {major.value}.{minor.value}")

        # Prefer a small pbuffer so no window manager or onscreen window is needed.
        GLX_RENDER_TYPE = 0x8011
        GLX_RGBA_BIT = 0x00000001
        GLX_DRAWABLE_TYPE = 0x8010
        GLX_PBUFFER_BIT = 0x00000004
        GLX_RGBA_TYPE = 0x8014
        GLX_PBUFFER_WIDTH = 0x8041
        GLX_PBUFFER_HEIGHT = 0x8040
        attribs = (C.c_int * 7)(
            GLX_DRAWABLE_TYPE, GLX_PBUFFER_BIT,
            GLX_RENDER_TYPE, GLX_RGBA_BIT, 0, 0, 0,
        )
        count = C.c_int()
        configs = gl.glXChooseFBConfig(
            display, x11.XDefaultScreen(display), attribs, C.byref(count)
        )
        if not configs or count.value < 1:
            raise RuntimeError("No GLX pbuffer-capable framebuffer configuration")
        say(f"GLX framebuffer configurations: {count.value}")

        config = configs[0]
        context = gl.glXCreateNewContext(display, config, GLX_RGBA_TYPE, None, 1)
        if not context:
            raise RuntimeError("GLX context creation failed; Mesa driver may be missing")
        dimensions = (C.c_int * 5)(
            GLX_PBUFFER_WIDTH, 64, GLX_PBUFFER_HEIGHT, 64, 0,
        )
        pbuffer = gl.glXCreatePbuffer(display, config, dimensions)
        if not pbuffer:
            raise RuntimeError("GLX pbuffer creation failed")
        if not gl.glXMakeContextCurrent(display, pbuffer, pbuffer, context):
            raise RuntimeError("glXMakeContextCurrent failed; software rendering unavailable")
        labels = ((0x1F00, "GL_VENDOR"), (0x1F01, "GL_RENDERER"),
                  (0x1F02, "GL_VERSION"))
        values = {}
        for ident, name in labels:
            value = gl.glGetString(ident)
            values[name] = value.decode("utf-8", errors="replace") if value else "unavailable"
            say(f"{name}: {values[name]}")
        if values["GL_VERSION"] == "unavailable":
            raise RuntimeError("OpenGL context exists but GL_VERSION unavailable")
        if "llvmpipe" in values["GL_RENDERER"].lower() or "softpipe" in values["GL_RENDERER"].lower():
            say("Software rasterizer confirmed (CPU rendering, not GPU)")
        else:
            say("Renderer is not identified as llvmpipe/softpipe")
        say("SUCCESS: OpenGL context created on virtual X11 display")
    finally:
        if context and pbuffer:
            gl.glXMakeContextCurrent(display, 0, 0, None)
        if pbuffer:
            gl.glXDestroyPbuffer(display, pbuffer)
        if context:
            gl.glXDestroyContext(display, context)
        if configs:
            x11.XFree(configs)
        x11.XCloseDisplay(display)


def main():
    if not BIN.is_file():
        raise RuntimeError("Xvfb not installed: run install-display first")
    if not XKB_DATA.is_dir():
        raise RuntimeError("XKB data unavailable: run install-display first")
    ensure_local_socket_dir()
    build_xkb_shim()
    env = env_for_display()
    with tempfile.TemporaryDirectory(prefix="tgll-glx-", dir=RUNTIME) as tmp:
        number = None
        for candidate in range(90, 100):
            if not Path(f"/tmp/.X11-unix/X{candidate}").exists() and not Path(
                f"/tmp/.X{candidate}-lock"
            ).exists():
                number = candidate
                break
        if number is None:
            raise RuntimeError("No free temporary X11 display from :90 to :99")
        display = f":{number}"
        say(f"Starting temporary Xvfb {display} (640x480x24)")
        command = [
            str(BIN), display, "-screen", "0", "640x480x24",
            "-nolisten", "tcp", "-noreset", "-xkbdir", str(XKB_DATA),
        ]
        xvfb_log = Path(tmp) / "xvfb.log"
        with xvfb_log.open("w", encoding="utf-8") as log_file:
            process = subprocess.Popen(command, env=env, cwd=ROOT,
                                       stdin=subprocess.DEVNULL,
                                       stdout=log_file, stderr=subprocess.STDOUT)
            try:
                for _ in range(40):
                    if process.poll() is not None:
                        raise RuntimeError(
                            "Xvfb exited: " + xvfb_log.read_text(errors="replace")[-3000:]
                        )
                    if probe_x11(display):
                        break
                    time.sleep(0.25)
                else:
                    raise RuntimeError("Xvfb did not accept an X11 connection")
                say("X11 display connection OK")
                probe_env = env.copy()
                probe_env.pop("LD_PRELOAD", None)
                probe_env.pop("TGLL_XKBCOMP_PATH", None)
                probe_env["DISPLAY"] = display
                probe_env["LIBGL_ALWAYS_SOFTWARE"] = "1"
                say("Checking GLX/OpenGL context using native ARM64 libraries...")
                try:
                    result = subprocess.run(
                        [sys.executable, "-u", __file__, "--probe-glx"],
                        env=probe_env, stdout=subprocess.PIPE,
                        stderr=subprocess.STDOUT, text=True,
                        timeout=35, check=False,
                    )
                except subprocess.TimeoutExpired as error:
                    raise RuntimeError("OpenGL probe timed out (35s)") from error
                say(result.stdout[-10000:])
                if result.returncode:
                    say("--- Xvfb log ---")
                    say(xvfb_log.read_text(errors="replace")[-2500:])
                    raise RuntimeError(f"OpenGL probe failed (exit {result.returncode})")
            finally:
                if process.poll() is None:
                    process.terminate()
                    try:
                        process.wait(timeout=4)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait()
    say("Diagnostic Xvfb stopped; game has not been started")


if __name__ == "__main__":
    try:
        if "--probe-glx" in sys.argv:
            glx_probe()
        else:
            main()
    except Exception as error:
        say(f"FAILED: {type(error).__name__}: {error}")
        raise SystemExit(1)
