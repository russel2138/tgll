"""Read-only inventory of NRO EMULATOR V2 archive; never launch or extract EXEs."""
from collections import Counter
from pathlib import Path, PurePosixPath
import hashlib
import io
import re
import struct
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]
ARCHIVE = ROOT / "NRO EMULATOR V2.zip"

def pe_metadata(z, item):
    try:
        with z.open(item) as src:
            raw = src.read(min(item.file_size, 8192))
        if len(raw) < 0x100 or raw[:2] != b"MZ":
            return "not PE"
        offset = struct.unpack_from("<I", raw, 0x3c)[0]
        if offset + 140 > len(raw) or raw[offset:offset+4] != b"PE\0\0":
            return "unrecognized PE"
        machine = struct.unpack_from("<H", raw, offset + 4)[0]
        magic = struct.unpack_from("<H", raw, offset + 24)[0]
        dd_offset = offset+24+(96 if magic == 0x10b else 112)
        is_managed = False
        if dd_offset + 120 <= len(raw):
            rva, size=struct.unpack_from("<II",raw,dd_offset+14*8)
            is_managed = bool(rva and size)
        arch={0x14c:"x86",0x8664:"x64",0xaa64:"arm64"}.get(machine,hex(machine))
        return arch+" "+("managed/.NET" if is_managed else "native")
    except (ValueError, RuntimeError, struct.error, OSError) as e:
        return "metadata-error:"+type(e).__name__

def java_manifest(z,item):
    if item.file_size > 25*1024*1024 or (item.flag_bits & 1):
        return "large/encrypted; not inspected"
    try:
        with z.open(item) as f:
            blob=f.read(25*1024*1024+1)
        with zipfile.ZipFile(io.BytesIO(blob)) as nested:
            names=nested.namelist()
            manifest=(nested.read("META-INF/MANIFEST.MF").decode("utf-8","replace")
                      if "META-INF/MANIFEST.MF" in names else "")
            lines=[x.strip() for x in manifest.splitlines()
                   if x.lower().startswith(("midlet-1:","main-class:","microedition-profile:","microedition-configuration:"))]
            # keep only first 140 chars/line and redact account-looking strings
            return f"members={len(names)} manifest=" + repr([x[:140] for x in lines[:6]])
    except (OSError, ValueError, KeyError, RuntimeError, zipfile.BadZipFile) as e:
        return "nested jar metadata error:"+type(e).__name__

class Inventory(unittest.TestCase):
    def test_inventory(self):
        print("ARCHIVE_EXISTS:",ARCHIVE.is_file(),flush=True)
        self.assertTrue(ARCHIVE.is_file())
        h=hashlib.sha256()
        with ARCHIVE.open("rb") as f:
            for chunk in iter(lambda:f.read(1024*1024),b""):
                h.update(chunk)
        print("ARCHIVE_BYTES:",ARCHIVE.stat().st_size,"SHA256:",h.hexdigest(),flush=True)
        self.assertTrue(zipfile.is_zipfile(ARCHIVE),"Not a ZIP archive")
        with zipfile.ZipFile(ARCHIVE) as z:
            entries=[x for x in z.infolist() if not x.is_dir()]
            print("MEMBERS:",len(entries),"UNCOMPRESSED:",sum(x.file_size for x in entries),flush=True)
            print("EXTENSIONS:",dict(Counter(Path(x.filename).suffix.lower() or "<none>" for x in entries)),flush=True)
            print("TOP_DIRECTORIES:",dict(Counter(PurePosixPath(x.filename).parts[0] for x in entries).most_common(35)),flush=True)
            print("ENCRYPTED_COUNT:",sum(bool(x.flag_bits&1) for x in entries),flush=True)
            for i,item in enumerate(entries[:140]):
                name=item.filename.replace("\r","?").replace("\n","?")
                if len(name)>200:name=name[:200]+"..."
                kind=""
                if item.filename.lower().endswith((".exe",".dll")):kind=" "+pe_metadata(z,item)
                if item.filename.lower().endswith(".jar"):kind=" "+java_manifest(z,item)
                print("FILE",i+1,repr(name),item.file_size,kind,flush=True)
            if len(entries)>140:print("LIST_TRUNCATED:",len(entries)-140,flush=True)
            more=[x for x in entries if x.filename.lower().endswith((".jar",".exe",".bat",".sh",".ps1",".config",".json",".ini",".jad",".zip",".rar",".7z"))]
            print("LAUNCH_CANDIDATES:",len(more),flush=True)
            for i,item in enumerate(more[:150]):
                kind=pe_metadata(z,item) if item.filename.lower().endswith(".exe") else (
                     java_manifest(z,item) if item.filename.lower().endswith(".jar") else "")
                print("TARGET",repr(item.filename[:200]),item.file_size,kind,flush=True)
            # Print user-facing text instructions only, redacting secrets and accounts.
            for item in entries:
                name=item.filename.lower()
                if not (name.endswith((".txt",".md",".readme")) and
                        any(k in name for k in ("huong","hướng","readme","guide","instruction","cai dat","sử dụng")) and
                        item.file_size<=15000 and not (item.flag_bits&1)):
                    continue
                data=z.read(item)
                for encoding in ("utf-8-sig","cp1258","cp1252"):
                    try:
                        t=data.decode(encoding)
                        break
                    except UnicodeDecodeError:
                        continue
                else:
                    t=""
                print("INSTRUCTIONS:",item.filename,flush=True)
                for line in t.splitlines()[:60]:
                    if re.search(r"(?i)pass(word)?|mật khẩu|tài khoản|account|token|key|@|secret|license|proxy",line):
                        continue
                    print("DOC",line[:180],flush=True)
            self.assertGreater(len(entries),0)

if __name__ == "__main__":
    unittest.main()
