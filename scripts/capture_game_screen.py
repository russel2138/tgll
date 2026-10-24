#!/usr/bin/env python3
"""Capture an X11 display into a PNG using libX11 and Python stdlib only.

Runs as a short-lived subprocess; no Pillow, ffmpeg, xwd or X11 permissions
beyond the existing local DISPLAY socket are needed.
"""
from __future__ import annotations

import ctypes as C
import os
from pathlib import Path
import struct
import sys
import zlib


class XImage(C.Structure):
    _fields_ = [
        ("width", C.c_int), ("height", C.c_int),
        ("xoffset", C.c_int), ("format", C.c_int),
        ("data", C.c_void_p), ("byte_order", C.c_int),
        ("bitmap_unit", C.c_int), ("bitmap_bit_order", C.c_int),
        ("bitmap_pad", C.c_int), ("depth", C.c_int),
        ("bytes_per_line", C.c_int), ("bits_per_pixel", C.c_int),
        ("red_mask", C.c_ulong), ("green_mask", C.c_ulong),
        ("blue_mask", C.c_ulong),
    ]


class WindowAttrs(C.Structure):
    _fields_ = [
        ("x", C.c_int), ("y", C.c_int), ("width", C.c_int),
        ("height", C.c_int), ("border_width", C.c_int),
        ("depth", C.c_int), ("visual", C.c_void_p),
        ("root", C.c_ulong), ("class_", C.c_int),
        ("bit_gravity", C.c_int), ("win_gravity", C.c_int),
        ("backing_store", C.c_int), ("backing_planes", C.c_ulong),
        ("backing_pixel", C.c_ulong), ("save_under", C.c_int),
        ("colormap", C.c_ulong), ("map_installed", C.c_int),
        ("map_state", C.c_int), ("all_event_masks", C.c_long),
        ("your_event_mask", C.c_long), ("do_not_propagate_mask", C.c_long),
        ("override_redirect", C.c_int), ("screen", C.c_void_p),
    ]


def png_chunk(tag, payload):
    return (
        struct.pack(">I", len(payload)) + tag + payload
        + struct.pack(">I", zlib.crc32(tag + payload) & 0xffffffff)
    )


def png_rgb(width, height, data, pixel_stride, line_stride, byteorder, masks):
    if pixel_stride not in (3, 4):
        raise RuntimeError(f"Unsupported X11 pixel size {pixel_stride}")
    shifts = []
    for mask in masks:
        if mask == 0:
            raise RuntimeError("TrueColor X11 mask missing")
        lowbit = (mask & -mask).bit_length() - 1
        bitcount = (mask >> lowbit).bit_count()
        if bitcount < 5 or bitcount > 16:
            raise RuntimeError("Unsupported X11 TrueColor component width")
        shifts.append((mask, lowbit, (1 << bitcount) - 1))
    rows = bytearray()
    for y in range(height):
        rows.append(0)
        offset = y * line_stride
        for x in range(width):
            start = offset + x * pixel_stride
            raw = int.from_bytes(data[start:start + pixel_stride], byteorder)
            for mask, shift, full in shifts:
                channel = (raw & mask) >> shift
                rows.append((channel * 255 + full // 2) // full)
    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + png_chunk(b"IHDR", header)
        + png_chunk(b"IDAT", zlib.compress(rows, 4))
        + png_chunk(b"IEND", b"")
    )


def main():
    if len(sys.argv) != 2:
        raise RuntimeError("Usage: capture_game_screen.py /home/container/game-screen.png")
    output = Path(sys.argv[1]).resolve()
    # Only allow writing to the TGLL runtime or top-level game screenshots.
    root = Path(__file__).resolve().parent.parent
    if output.parent != root or not output.name.startswith("game-screen-") or output.suffix != ".png":
        raise RuntimeError("Output must be /home/container/game-screen-*.png")
    xlib = C.CDLL("libX11.so.6")
    xlib.XOpenDisplay.argtypes = [C.c_char_p]
    xlib.XOpenDisplay.restype = C.c_void_p
    xlib.XDefaultScreen.argtypes = [C.c_void_p]
    xlib.XDefaultScreen.restype = C.c_int
    xlib.XRootWindow.argtypes = [C.c_void_p, C.c_int]
    xlib.XRootWindow.restype = C.c_ulong
    xlib.XDisplayWidth.argtypes = [C.c_void_p, C.c_int]
    xlib.XDisplayWidth.restype = C.c_int
    xlib.XDisplayHeight.argtypes = [C.c_void_p, C.c_int]
    xlib.XDisplayHeight.restype = C.c_int
    xlib.XGetImage.argtypes = [
        C.c_void_p, C.c_ulong, C.c_int, C.c_int,
        C.c_uint, C.c_uint, C.c_ulong, C.c_int,
    ]
    xlib.XGetImage.restype = C.POINTER(XImage)
    xlib.XDestroyImage.argtypes = [C.POINTER(XImage)]
    xlib.XDestroyImage.restype = C.c_int
    xlib.XCloseDisplay.argtypes = [C.c_void_p]
    xlib.XCloseDisplay.restype = C.c_int

    display = xlib.XOpenDisplay(os.environ.get("DISPLAY", ":90").encode())
    if not display:
        raise RuntimeError("Cannot connect to Xvfb display")
    image = None
    try:
        screen = xlib.XDefaultScreen(display)
        root_window = xlib.XRootWindow(display, screen)
        width = xlib.XDisplayWidth(display, screen)
        height = xlib.XDisplayHeight(display, screen)
        if not (1 <= width <= 1920 and 1 <= height <= 1080):
            raise RuntimeError(f"Unexpected virtual display {width}x{height}")
        image = xlib.XGetImage(
            display, root_window, 0, 0, width, height,
            C.c_ulong(-1).value, 2,
        )
        if not image:
            raise RuntimeError("XGetImage returned NULL")
        pixels = image.contents
        if pixels.bits_per_pixel not in (24, 32) or pixels.bytes_per_line < width * 3:
            raise RuntimeError(f"Unexpected XImage format: depth={pixels.depth}, bpp={pixels.bits_per_pixel}")
        size = pixels.bytes_per_line * height
        if size > 10 * 1024 * 1024:
            raise RuntimeError("XImage buffer exceeds safety limit")
        raw = C.string_at(pixels.data, size)
        png = png_rgb(
            width, height, raw, pixels.bits_per_pixel // 8,
            pixels.bytes_per_line,
            "little" if pixels.byte_order == 0 else "big",
            (pixels.red_mask, pixels.green_mask, pixels.blue_mask),
        )
        temp = output.with_suffix(".png.part")
        try:
            temp.write_bytes(png)
            temp.replace(output)
        finally:
            temp.unlink(missing_ok=True)
        print(f"SCREENSHOT: {output} ({width}x{height}, {len(png)} bytes)", flush=True)
    finally:
        if image:
            xlib.XDestroyImage(image)
        xlib.XCloseDisplay(display)


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"SCREENSHOT FAILED: {type(error).__name__}: {error}", flush=True)
        raise SystemExit(1)
