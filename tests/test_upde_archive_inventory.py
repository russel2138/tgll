"""Read-only inventory of the developer-provided TiênnVo Up Đệ Basic ZIP.

Run as an ordinary offline test. Does NOT run or unpack any application.
"""
from __future__ import annotations

from collections import Counter
from pathlib import Path
import struct
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]
ARCHIVE = ROOT / "[TiennVo.Net]Tool Up De Basic.zip"

def pe_summary(z, info):
    if not info.filename.lower().endswith((".exe", ".dll")):
        return ""
    if info.flag_bits & 1:
        return "encrypted"
    try:
        with z.open(info) as src:
            data = src.read(min(info.file_size, 40_000_000))
        if len(data) < 0x100 or data[:2] != b"MZ":
            return "not PE"
        offset = struct.unpack_from("<I", data, 0x3c)[0]
        if offset+26 > len(data) or data[offset:offset+4] != b"PE\0\0":
            return "MZ without PE header"
        machine = struct.unpack_from("<H", data, offset+4)[0]
        opt_offset = offset+24
        optional_magic = struct.unpack_from("<H", data, opt_offset)[0]
        arch = {0x14c:"x86",0x8664:"x64",0xaa64:"arm64"}.get(machine,hex(machine))
        kind = {0x10b:"PE32",0x20b:"PE32+"}.get(optional_magic,hex(optional_magic))
        # Check the CLR data-directory entry in the optional header.
        data_dir_offset = opt_offset + (96 if optional_magic==0x10b else 112)
        is_dotnet = False
        if data_dir_offset + (15*8) <= len(data):
            rva, size = struct.unpack_from("<II", data, data_dir_offset+14*8)
            is_dotnet = rva != 0 and size > 0
        return f"{arch} {kind}" + (" .NET CLR" if is_dotnet else " native/unknown")
    except (OSError, RuntimeError, EOFError, ValueError, struct.error) as e:
        return "inspection unavailable: " + type(e).__name__

class ArchiveInventory(unittest.TestCase):
    def test_read_only_zip_inventory(self):
        self.assertTrue(ARCHIVE.is_file(), "Archive not found in repository")
        print("\nARCHIVE:", ARCHIVE.name, "bytes:", ARCHIVE.stat().st_size, flush=True)
        with zipfile.ZipFile(ARCHIVE) as z:
            # Keep any account/credential files private. Only general instructions
            # and runtime metadata are inspected; never execute the archive.
            guide = z.read("Hướng dẫn sử dụng.txt")
            text = ""
            for encoding in ("utf-8-sig", "cp1258", "cp1252"):
                try:
                    text = guide.decode(encoding)
                    break
                except UnicodeDecodeError:
                    pass
            print("GUIDE_PREVIEW (sanitized):",flush=True)
            import re
            for line in text.splitlines()[:60]:
                if re.search(r"password|mật khẩu|tài khoản|token|key|@|sdt|phone|số điện thoại",line,re.I):
                    continue
                print("  ",line[:160],flush=True)
            for name in ("QLTK.exe.config", "QLTK PET.exe.config"):
                data=z.read(name).decode("utf-8-sig", errors="replace")
                runtime=re.findall(r'(?i)(?:supportedRuntime|targetFramework|sku|version)[^\n]{0,160}',data)
                print("CONFIG",name,"runtime",runtime[:8],flush=True)
            for name in ("Run/Dragonboy_vn_v229_Data/globalgamemanagers",
                         "DragonBoy166_Data/globalgamemanagers"):
                b=z.read(name)
                versions=re.findall(rb"20[0-3][0-9]\.[0-9]{1,2}\.[0-9]{1,3}[afbp][0-9]{1,4}",b)
                print("UNITY_VERSION",name,sorted(set(v.decode("ascii") for v in versions))[:8],flush=True)
            entries = [x for x in z.infolist() if not x.is_dir()]
            print("MEMBERS:", len(entries), "UNCOMPRESSED:", sum(x.file_size for x in entries), flush=True)
            print("ENCRYPTED:", sum(bool(x.flag_bits & 1) for x in entries), flush=True)
            print("EXTENSIONS:", dict(Counter(Path(x.filename).suffix.lower() or "<none>" for x in entries)), flush=True)
            for idx, x in enumerate(entries):
                if idx >= 160:
                    print("TRUNCATED (more than 160 entries)", flush=True)
                    break
                name = x.filename.replace("\n","\\n").replace("\r","\\r")
                print(f"MEMBER {idx+1}: {name!r} uncompressed={x.file_size} encrypted={bool(x.flag_bits & 1)} {pe_summary(z,x)}",flush=True)
            self.assertGreater(len(entries),0)

if __name__ == "__main__":
    unittest.main()
