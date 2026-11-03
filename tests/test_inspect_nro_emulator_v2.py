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
    def test_embedded_jar_linux_support(self):
        with zipfile.ZipFile(ARCHIVE) as outer:
            exe=outer.read("NRO EMULATOR.exe")
        with zipfile.ZipFile(io.BytesIO(exe)) as inner:
            names=inner.namelist()
            print("EMBEDDED_JAR_COUNT:",len(names),flush=True)
            print("EMBEDDED_CLASSES:",sum(x.endswith(".class") for x in names),flush=True)
            print("EMBEDDED_LINUX_LIBS:",[x for x in names if x.endswith(".so")][:70],flush=True)
            print("EMBEDDED_WINDOWS_LIBS:",[x for x in names if x.endswith(".dll")][:20],flush=True)
            print("GLFW_CLASS_PRESENT:",any("org/lwjgl/glfw/GLFW.class" in x for x in names),flush=True)
            print("LWJGL_LIBS:",[x for x in names if any(k in x.lower() for k in (
                "liblwjgl", "glfw", "libopenal", "libgdx", "libjemalloc", "libstb")) and
                (x.endswith(".so") or x.endswith(".dylib") or x.endswith(".dll"))][:90],flush=True)
            print("APP_CLASSES_SAMPLE:",[x for x in names if x.startswith("com/dragonboy/") and x.endswith(".class")][:50],flush=True)
            main="com/dragonboy/desktop/DesktopLauncher.class"
            print("MAIN_CLASS_FOUND:",main in names,flush=True)
            if main in names:
                b=inner.read(main)
                print("MAIN_CLASS_MAJOR:",struct.unpack_from(">H",b,6)[0],flush=True)
            jar_main="META-INF/MANIFEST.MF"
            print("JAR_MANIFEST:",repr(inner.read(jar_main).decode("utf-8","replace")[:1600]),flush=True)

    def test_exe_wrapper_and_bundled_java(self):
        with zipfile.ZipFile(ARCHIVE) as z:
            names=set(z.namelist())
            for file in sorted(name for name in names if name.startswith("jre/") and
                               (name.endswith("/release") or name.endswith("/modules"))):
                info=z.getinfo(file)
                if file.endswith("/release") and info.file_size < 2000:
                    t=z.read(file).decode("utf-8","replace")
                    print("JRE_RELEASE:",re.sub(r'(?i)password|token|secret',"[redacted]",t[:1400]),flush=True)
                else:
                    print("JRE_LIBRARY:",file,info.file_size,flush=True)
            data=z.read("NRO EMULATOR.exe")
            print("EXE_BYTES:",len(data),flush=True)
            print("EXE_PE_PREFIX:",repr(data[:8]),flush=True)
            markers=[
                b"PK\x03\x04",b"PK\x05\x06",b"META-INF/MANIFEST.MF",
                b"javaw.exe",b"java.exe",b"jvm.dll",b"jre\\bin",
                b"jre/bin",b"JNI_CreateJavaVM",b"Launch4j",b"launch4j",
                b"exe4j",b"EXE4J",b"Inno Setup",b"NSIS",
                b"7z\xbc\xaf\x27\x1c",b"graalvm",b"GraalVM",
                b"org/microemu",b"org/microemu/app/Main",b"Midlet",
                b"MIDlet",b"JAR",b".jar",b"jpackage",b"Jar2Exe",
            ]
            for marker in markers:
                print("EXE_MARKER",repr(marker),data.find(marker),flush=True)
            embedded=zipfile.is_zipfile(io.BytesIO(data))
            print("EXE_VALID_ZIP_CONTAINER:",embedded,flush=True)
            if embedded:
                with zipfile.ZipFile(io.BytesIO(data)) as inner:
                    files=inner.namelist()
                    print("EXE_INTERNAL_ENTRIES:",len(files),flush=True)
                    print("EXE_INTERNAL_NAMES:",repr(files[:80]),flush=True)
                    for manifest_name in ("META-INF/MANIFEST.MF","MANIFEST.MF"):
                        if manifest_name in files:
                            b=inner.read(manifest_name).decode("utf-8","replace")
                            print("EXE_MANIFEST",repr([ln[:170] for ln in b.splitlines()[:25]]),flush=True)
            # PE overlay = bytes after last physical section; useful for finding
            # compressed/embedded Java artifacts without running the program.
            ptr=struct.unpack_from("<I",data,0x3c)[0]
            num_sections=struct.unpack_from("<H",data,ptr+6)[0]
            optional_size=struct.unpack_from("<H",data,ptr+20)[0]
            table=ptr+24+optional_size
            ends=[]
            for i in range(min(num_sections,96)):
                x=table+i*40
                if x+40>len(data): break
                raw_size=struct.unpack_from("<I",data,x+16)[0]
                raw_pos=struct.unpack_from("<I",data,x+20)[0]
                ends.append(raw_pos+raw_size)
            overlay_start=max(ends) if ends else 0
            print("PE_SECTIONS:",num_sections,"OVERLAY_START:",overlay_start,
                  "OVERLAY_BYTES:",max(0,len(data)-overlay_start),flush=True)

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
