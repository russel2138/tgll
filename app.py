#!/usr/bin/env python3
"""HidenCloud TGLL launcher. Python 3.10+, no third-party runtime deps."""
from __future__ import annotations

import ast
import json
import os
from pathlib import Path, PurePosixPath
import platform
import queue
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request

VERSION = "2026.10.24.16"
ROOT = Path(__file__).resolve().parent
RUNTIME = ROOT / ".tgll-runtime"
COMMAND_FILE = ROOT / ".tgll-command"
JOB_FILE = RUNTIME / "job.json"
MANAGED_FILES = ("app.py", "main.py", "scripts/install_box64.py", "scripts/install_wine.py", "scripts/install_x86_libs.py", "scripts/install_display.py", "scripts/test_graphics.py", "scripts/install_game.py", "scripts/install_graphics_libs.py", "scripts/test_game.py", "scripts/capture_game_screen.py", "scripts/install_vnc.py", "scripts/run_game.py", "scripts/vnc_info.py", "README.md")
RAW_BASE = "https://raw.githubusercontent.com/russel2138/tgll/main/"
COMMANDS: queue.Queue[str] = queue.Queue()
SHELL_MODE = False
SHELL_CWD = ROOT
CURRENT_JOB = None
STOPPING = False


def say(message=""):
    print(message, flush=True)


def is_running(pid):
    """Do not treat an exited but unreaped Linux zombie as a live job."""
    try:
        pid = int(pid)
        if pid <= 0:
            return False
        stat_path = Path(f"/proc/{pid}/stat")
        if stat_path.is_file():
            stat = stat_path.read_text(encoding="ascii", errors="replace")
            # /proc/<pid>/stat: pid (comm) state ...
            state = stat.rsplit(")", 1)[-1].strip().split()[0]
            if state in ("Z", "X"):
                return False
        os.kill(pid, 0)
        return True
    except (OSError, ValueError, TypeError, IndexError):
        return False


def job_info():
    if not JOB_FILE.is_file():
        return None
    try:
        data = json.loads(JOB_FILE.read_text(encoding="utf-8"))
        data["running"] = is_running(data.get("pid"))
        return data
    except (ValueError, OSError):
        return None


def memory_value(name):
    try:
        return (Path("/sys/fs/cgroup") / name).read_text().strip()
    except OSError:
        return "unavailable"


def status():
    say(f"Launcher: {VERSION}")
    say(f"Platform: {platform.system()} {platform.machine()} | Python {platform.python_version()}")
    say(f"Root: {ROOT}")
    cpu = memory_value("cpu.max").split()
    if len(cpu) == 2 and cpu[0] != "max":
        try:
            say(f"CPU quota: {int(cpu[0]) / int(cpu[1]):g} vCPU")
        except (ValueError, ZeroDivisionError):
            say(f"CPU quota raw: {' '.join(cpu)}")
    else:
        say(f"CPU quota raw: {' '.join(cpu)}")
    for name in ("memory.max", "memory.current"):
        value = memory_value(name)
        if value.isdigit():
            value = f"{int(value) / 2**30:.2f} GiB"
        say(f"{name}: {value}")
    for name in ("git", "gcc", "g++", "bash", "wine", "Xvfb"):
        say(f"{name}: {shutil.which(name) or 'missing'}")
    box64 = RUNTIME / "box64" / "bin" / "box64"
    say(f"Box64: {box64 if box64.is_file() else 'not installed'}")
    wine = RUNTIME / "wine" / "bin" / "wine"
    say(f"Wine64: {wine if wine.is_file() else 'not installed'}")
    compat_lib = RUNTIME / "x86_64-libs" / "libgcc_s.so.1"
    say(f"amd64 libgcc: {compat_lib if compat_lib.is_file() else 'not installed'}")
    display = RUNTIME / "display" / "usr" / "bin" / "Xvfb"
    say(f"Xvfb local: {display if display.is_file() else 'not installed'}")
    vnc = RUNTIME / "vnc/native/usr/bin/x11vnc"
    say(f"x11vnc: {vnc if vnc.is_file() else 'not installed'}")
    job = job_info()
    if job:
        say(f"Job: {job.get('name')} PID {job.get('pid')} {'running' if job['running'] else 'stopped'}")
    else:
        say("Job: none")


def tail(path, count=40):
    if not path.is_file():
        say(f"Log not found: {path}")
        return
    try:
        from collections import deque
        with path.open("r", encoding="utf-8", errors="replace") as stream:
            lines = deque(stream, maxlen=count)
        say("".join(lines).rstrip())
    except OSError as error:
        say(f"Cannot read log: {error}")


def download(url):
    request = urllib.request.Request(url, headers={
        "User-Agent": "tgll-launcher/1.0",
        "Accept": "application/vnd.github+json" if "api.github.com/" in url else "*/*",
        "Cache-Control": "no-cache",
    })
    with urllib.request.urlopen(request, timeout=35) as response:
        content = response.read(2 * 1024 * 1024 + 1)
    if len(content) > 2 * 1024 * 1024:
        raise ValueError("Remote file exceeds 2 MiB")
    return content


def latest_commit_sha():
    # Never fetch mutable /main/ raw files: CDN caches can make 'update'
    # silently report 'Already up to date' after a new GitHub commit.
    url = (
        "https://api.github.com/repos/russel2138/tgll/commits/main"
        f"?cache_bust={time.time_ns()}"
    )
    response = json.loads(download(url))
    sha = response.get("sha", "")
    if len(sha) != 40 or any(ch not in "0123456789abcdef" for ch in sha):
        raise ValueError("GitHub API did not return a valid commit SHA")
    return sha


def managed_files_in_remote_app(app_payload):
    """Discover files from the NEW launcher, not the currently running one.

    This prevents missing new dependencies when the current release did not
    know about them (as happened with scripts/install_x86_libs.py).
    """
    tree = ast.parse(app_payload.decode("utf-8"), filename="app.py")
    for statement in tree.body:
        if isinstance(statement, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "MANAGED_FILES"
            for target in statement.targets
        ):
            files = ast.literal_eval(statement.value)
            if not isinstance(files, (list, tuple)) or not 1 <= len(files) <= 64:
                raise ValueError("Invalid MANAGED_FILES in remote app")
            if not all(isinstance(path, str) for path in files):
                raise ValueError("MANAGED_FILES must contain strings")
            if "app.py" not in files or len(set(files)) != len(files):
                raise ValueError("MANAGED_FILES missing app.py or has duplicates")
            return files
    raise ValueError("Remote app.py does not declare MANAGED_FILES")


def update():
    say("Checking GitHub updates...")
    if (ROOT / ".git").exists():
        result = subprocess.run(["git", "-C", str(ROOT), "pull", "--ff-only"],
                                cwd=ROOT, check=False)
        if result.returncode:
            say(f"Git pull failed (exit {result.returncode}); launcher unchanged")
            return
        restart()
        return

    sha = latest_commit_sha()
    say(f"Latest GitHub commit: {sha[:12]}")
    remote_url = f"https://raw.githubusercontent.com/russel2138/tgll/{sha}/"
    app_payload = download(remote_url + "app.py")
    remote_files = managed_files_in_remote_app(app_payload)
    say(f"Syncing {len(remote_files)} managed files from remote manifest")
    with tempfile.TemporaryDirectory(prefix=".tgll-update-", dir=ROOT) as tmp:
        staging = Path(tmp)
        changed = []
        for relative in remote_files:
            path = PurePosixPath(relative)
            if not relative or path.is_absolute() or ".." in path.parts:
                raise ValueError("Unsafe update path")
            # All files use the same immutable Git commit; use the remote
            # manifest to include any dependencies added by this release.
            payload = app_payload if relative == "app.py" else download(remote_url + relative)
            if relative.endswith(".py"):
                compile(payload, relative, "exec")
            dest = ROOT / relative
            if dest.is_symlink():
                raise ValueError(f"Refusing to replace symlink: {relative}")
            (staging / relative).parent.mkdir(parents=True, exist_ok=True)
            (staging / relative).write_bytes(payload)
            if not dest.exists() or dest.read_bytes() != payload:
                changed.append(relative)
        if not changed:
            say(f"Already up to date at commit {sha[:12]}")
            return
        for relative in changed:
            source = staging / relative
            destination = ROOT / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            os.replace(source, destination)
        say("Updated: " + ", ".join(changed))
    restart()


def restart():
    say("Restarting Python launcher...")
    sys.stdout.flush()
    os.execv(sys.executable, [sys.executable, str(ROOT / "app.py")])


def run_bash(command, cwd=None):
    if shutil.which("bash") is None:
        say("bash is not installed")
        return
    try:
        result = subprocess.run(["bash", "-lc", command], cwd=str(cwd or ROOT),
                                check=False)
        say(f"[bash] exit code: {result.returncode}")
    except OSError as error:
        say(f"[bash] {error}")


def launch_job(name, script, args=()):
    job = job_info()
    if job and job["running"]:
        say(f"Another job is running: {job.get('name')} PID {job.get('pid')}")
        return
    if not script.is_file():
        say("Installer missing: run update first")
        return
    RUNTIME.mkdir(parents=True, exist_ok=True)
    log_file = RUNTIME / f"{name}.log"
    try:
        with log_file.open("w", encoding="utf-8") as stream:
            proc = subprocess.Popen(
                [sys.executable, "-u", str(script), *args],
                cwd=ROOT,
                stdin=subprocess.DEVNULL,
                stdout=stream,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
        JOB_FILE.write_text(json.dumps({
            "name": name, "pid": proc.pid, "log": str(log_file),
            "started": time.strftime("%Y-%m-%d %H:%M:%S"),
        }, indent=2), encoding="utf-8")
        say(f"Started {name} PID {proc.pid}")
        say(f"Use 'logs 50' or 'job' to check progress")
    except OSError as error:
        say(f"Could not start {name}: {error}")


def private_memory_stats():
    """Show meaningful memory pressure instead of treating page cache as anon RSS."""
    values = {}
    try:
        for line in (Path("/sys/fs/cgroup/memory.stat")).read_text().splitlines():
            key, value = line.split()
            values[key] = int(value)
    except (OSError, ValueError):
        pass
    current = memory_value("memory.current")
    maximum = memory_value("memory.max")
    try:
        used = int(current)
        limit = int(maximum)
        anon = values.get("anon", 0)
        cache = values.get("file", 0)
        inactive = values.get("inactive_file", 0)
        mib = lambda size: f"{size / (1024 * 1024):.1f} MiB"
        say(f"memory.current={mib(used)} / memory.max={mib(limit)}")
        say(f"anon={mib(anon)} | file cache={mib(cache)} | inactive_file={mib(inactive)}")
        say(f"estimated working set (current - inactive_file)={mib(max(0, used-inactive))}")
        say(f"headroom before cgroup limit={mib(max(0, limit-used))}; cache may be reclaimed")
    except (ValueError, TypeError):
        say("Cgroup memory stats not available")
    for key in ("memory.swap.current", "memory.events"):
        try:
            say(f"{key}: " + Path("/sys/fs/cgroup", key).read_text().strip().replace("\n", " | "))
        except OSError:
            pass


def vnc_options(line):
    settings = RUNTIME / "vnc-settings.json"
    config = {}
    if settings.is_file():
        try:
            config = json.loads(settings.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            say("Invalid VNC settings; refusing to overwrite them")
            return
    parts = line.split()
    if not parts:
        say("VNC public: " + ("on" if config.get("public") else "off (localhost only)"))
        say("VNC port: " + str(config.get("port", "auto (VNC_PORT/SERVER_PORT/PORT/5900)")))
        say("Usage: vnc-public on [allocated_tcp_port] | vnc-public off")
        return
    if parts[0] not in ("on", "off") or len(parts) > 2:
        say("Usage: vnc-public on [allocated_tcp_port] | vnc-public off")
        return
    if len(parts) > 1:
        try:
            port = int(parts[1])
            if not 1024 <= port <= 65535:
                raise ValueError()
        except ValueError:
            say("VNC TCP port must be between 1024 and 65535")
            return
        config["port"] = port
    config["public"] = parts[0] == "on"
    RUNTIME.mkdir(parents=True, exist_ok=True)
    tmp = settings.with_suffix(".tmp")
    try:
        tmp.write_text(json.dumps(config, indent=2), encoding="utf-8")
        tmp.chmod(0o600)
        tmp.replace(settings)
    finally:
        tmp.unlink(missing_ok=True)
    say(f"VNC bind mode set to {'public (0.0.0.0)' if config['public'] else 'localhost only'}")
    if config["public"]:
        say("WARNING: classic VNC password auth does not encrypt the connection.")
        say("Only use a hosting-panel allocated TCP port; prefer tunnel/private network.")
    say("Mode takes effect the next time game-start or game-restart runs")


def stop_live_game():
    info = job_info()
    if not info or not info["running"]:
        say("Game session is not running")
        return True
    if info.get("name") != "game-live":
        say(f"Cannot stop: other job '{info.get('name')}' is active")
        return False
    try:
        # Signal supervisor only, allowing orderly Wine/VNC/Xvfb cleanup.
        os.kill(int(info["pid"]), signal.SIGTERM)
    except ProcessLookupError:
        return True
    except OSError as error:
        say(f"Unable to stop game: {error}")
        return False
    for _ in range(55):
        if not is_running(info["pid"]):
            say("Game session stopped")
            return True
        time.sleep(0.25)
    say("Stop timeout: inspect game-live.log and process status")
    return False


def stop_job():
    job = job_info()
    if not job or not job["running"]:
        say("No active job")
        return
    try:
        os.killpg(int(job["pid"]), signal.SIGTERM)
        say("Stop signal sent to job process group")
    except OSError as error:
        say(f"Failed to stop job: {error}")


def handle(line):
    global SHELL_MODE, SHELL_CWD, STOPPING
    line = line.strip()
    if not line:
        return
    if SHELL_MODE:
        if line in ("exit", "quit", "back"):
            SHELL_MODE = False
            say("Exited bash mode")
            return
        if line == "pwd":
            say(str(SHELL_CWD))
            return
        if line == "cd" or line.startswith("cd "):
            target = line[2:].strip() or str(ROOT)
            target = os.path.expanduser(target)
            new_cwd = (SHELL_CWD / target).resolve()
            if new_cwd.is_dir():
                SHELL_CWD = new_cwd
                say(f"cwd: {SHELL_CWD}")
            else:
                say(f"No such directory: {new_cwd}")
            return
        run_bash(line, SHELL_CWD)
        return

    cmd, _, arg = line.partition(" ")
    cmd = cmd.lower()
    # Everyday one-word commands control the game, never the launcher.
    aliases = {
        "start": "game-start",
        "stop": "game-stop",
        "restart": "game-restart",
        "status": "game-status",
        "vnc": "vnc-info",
    }
    cmd = aliases.get(cmd, cmd)
    if cmd in ("help", "?"):
        if arg.strip().lower() in ("advanced", "setup"):
            say("Maintenance (not needed for daily VPS use):")
            say("  setup [box64|wine|display|graphics|vnc|game|test-game|test-graphics|wine-diagnose]")
            say("  launcher-status | launcher-restart | job | job-stop")
            say("  game-screenshot | bash [command] | bash | quit")
            say("  Tip: launcher stays online after stopping the game.")
        else:
            say("TGLL VPS Commands:")
            say("  start           Start game + VNC")
            say("  stop            Stop game + Wine + VNC (launcher stays online)")
            say("  restart         Restart game + VNC")
            say("  status          Game/VNC status and RAM")
            say("  vnc-info        Show TigerVNC address and locally saved password")
            say("  vnc-password    Set new VNC password")
            say("  vnc-public on|off [port]   Remote access settings")
            say("  mem | logs [N] | update | game-autostart on|off")
            say("  help advanced   Installer/testing/diagnostic commands")
    elif cmd == "launcher-status":
        status()
    elif cmd == "update":
        update()
    elif cmd == "launcher-restart":
        restart()
    elif cmd == "setup":
        action = arg.strip().lower()
        jobs = {
            "box64": ("box64-setup", "install_box64.py", ()),
            "wine": ("wine-setup", "install_wine.py", ()),
            "display": ("display-setup", "install_display.py", ()),
            "graphics": ("graphics-libs-setup", "install_graphics_libs.py", ()),
            "vnc": ("vnc-setup", "install_vnc.py", ()),
            "game": ("game-install", "install_game.py", ()),
            "test-game": ("game-test", "test_game.py", ()),
            "test-graphics": ("graphics-test", "test_graphics.py", ()),
            "wine-diagnose": ("wine-diagnose", "install_wine.py", ("--diagnose",)),
        }
        if action not in jobs:
            say("Usage: setup [box64|wine|display|graphics|vnc|game|test-game|test-graphics|wine-diagnose]")
        else:
            name, filename, options = jobs[action]
            launch_job(name, ROOT / "scripts" / filename, options)
    elif cmd == "vnc-password":
        installer = ROOT / "scripts" / "install_vnc.py"
        if not installer.is_file():
            say("VNC installer missing; run update first")
        else:
            result = subprocess.run(
                [sys.executable, "-u", str(installer), "--password"],
                cwd=ROOT, capture_output=True, text=True, timeout=30, check=False,
            )
            say(result.stdout.strip())
            if result.stderr.strip():
                say(result.stderr.strip()[-1200:])
            if result.returncode:
                say(f"VNC password generation failed (exit {result.returncode})")
    elif cmd == "vnc-info":
        helper = ROOT / "scripts" / "vnc_info.py"
        if not helper.is_file():
            say("VNC info helper missing; run update first")
        else:
            result = subprocess.run(
                [sys.executable, "-u", str(helper)],
                cwd=ROOT, capture_output=True, text=True,
                timeout=20, check=False,
            )
            say(result.stdout.strip() or result.stderr.strip())
            if result.returncode:
                say(f"VNC info failed (exit {result.returncode})")
    elif cmd == "vnc-public":
        vnc_options(arg)
    elif cmd == "game-autostart":
        enabled_file = RUNTIME / "game-autostart.json"
        if arg not in ("on", "off"):
            enabled = False
            if enabled_file.is_file():
                try:
                    enabled = bool(json.loads(enabled_file.read_text()).get("enabled"))
                except (ValueError, OSError):
                    pass
            say("Game autostart: " + ("on" if enabled else "off"))
            say("Usage: game-autostart on | game-autostart off")
        else:
            RUNTIME.mkdir(parents=True, exist_ok=True)
            temp = enabled_file.with_suffix(".tmp")
            try:
                temp.write_text(json.dumps({"enabled": arg == "on"}), encoding="utf-8")
                temp.chmod(0o600)
                temp.replace(enabled_file)
            finally:
                temp.unlink(missing_ok=True)
            say("Game autostart set to " + arg)
            if arg == "on":
                say("Game starts automatically after next HidenCloud/launcher restart; "
                    "use game-start to launch immediately")
    elif cmd == "game-start":
        launch_job("game-live", ROOT / "scripts" / "run_game.py")
    elif cmd == "game-stop":
        stop_live_game()
    elif cmd == "game-restart":
        if stop_live_game():
            launch_job("game-live", ROOT / "scripts" / "run_game.py")
    elif cmd == "mem":
        private_memory_stats()
    elif cmd == "game-status":
        info = job_info()
        say(f"Job: {json.dumps(info)}")
        session = RUNTIME / "game-session.json"
        if session.is_file():
            say(session.read_text(encoding="utf-8"))
        else:
            say("No running TGLL VNC session recorded")
        private_memory_stats()
    elif cmd == "game-screenshot":
        session = RUNTIME / "game-session.json"
        if not session.is_file():
            say("Game session is not active; run game-start")
        else:
            props = json.loads(session.read_text(encoding="utf-8"))
            env = os.environ.copy()
            env["DISPLAY"] = props["display"]
            png = ROOT / "game-screen-live.png"
            result = subprocess.run(
                [sys.executable, str(ROOT / "scripts" / "capture_game_screen.py"), str(png)],
                cwd=ROOT, env=env, capture_output=True, text=True, timeout=15, check=False,
            )
            say(result.stdout.strip() or result.stderr.strip())
    elif cmd == "job":
        job = job_info()
        say(json.dumps(job, indent=2) if job else "No job recorded")
    elif cmd == "job-stop":
        stop_job()
    elif cmd == "logs":
        try:
            count = min(max(int(arg or 40), 1), 500)
        except ValueError:
            say("Usage: logs [1-500]")
            return
        job = job_info()
        tail(Path(job["log"]) if job else RUNTIME / "box64-setup.log", count)
    elif cmd == "bash":
        if not arg.strip():
            SHELL_MODE = True
            SHELL_CWD = ROOT
            say("Bash mode: each line runs via bash -lc; cd persists, export does not")
            say("Type 'exit' to return to launcher")
        else:
            run_bash(arg)
    elif cmd == "quit":
        say("Stopping launcher. HidenCloud may label exit 0 as offline/crash.")
        STOPPING = True
    else:
        say(f"Unknown command: {cmd}. Type help")


def stdin_reader():
    try:
        for line in sys.stdin:
            COMMANDS.put(line)
    except (OSError, ValueError):
        pass


def main():
    global STOPPING
    RUNTIME.mkdir(parents=True, exist_ok=True)
    say(f"TGLL launcher {VERSION} | {platform.machine()}")
    say("Type 'help' in HidenCloud Console. Process remains online while idle.")
    say(f"Fallback: create {COMMAND_FILE.name} in File Manager with a command")
    threading.Thread(target=stdin_reader, daemon=True).start()
    auto = RUNTIME / "game-autostart.json"
    if auto.is_file():
        try:
            if bool(json.loads(auto.read_text(encoding="utf-8")).get("enabled")):
                say("Autostart enabled: launching TGLL VPS session")
                launch_job("game-live", ROOT / "scripts" / "run_game.py")
        except (OSError, ValueError) as error:
            say(f"Game autostart config error: {error}")
    while not STOPPING:
        try:
            if COMMAND_FILE.is_file():
                text = COMMAND_FILE.read_text(encoding="utf-8")
                COMMAND_FILE.unlink()
                for line in text.splitlines():
                    if line.strip():
                        COMMANDS.put(line)
            try:
                instruction = COMMANDS.get(timeout=2)
            except queue.Empty:
                continue
            try:
                handle(instruction)
            except (OSError, ValueError, urllib.error.URLError, subprocess.SubprocessError) as error:
                say(f"Command error: {error}")
            except Exception as error:
                say(f"Unexpected error ({type(error).__name__}): {error}")
        except KeyboardInterrupt:
            STOPPING = True
        except OSError as error:
            say(f"File command error: {error}")
            time.sleep(2)
    say("Launcher stopped")


if __name__ == "__main__":
    main()
