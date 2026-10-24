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

VERSION = "2026.10.24.12"
ROOT = Path(__file__).resolve().parent
RUNTIME = ROOT / ".tgll-runtime"
COMMAND_FILE = ROOT / ".tgll-command"
JOB_FILE = RUNTIME / "job.json"
MANAGED_FILES = ("app.py", "main.py", "scripts/install_box64.py", "scripts/install_wine.py", "scripts/install_x86_libs.py", "scripts/install_display.py", "scripts/test_graphics.py", "scripts/install_game.py", "scripts/install_graphics_libs.py", "scripts/test_game.py", "README.md")
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
    if cmd in ("help", "?"):
        say("Commands: help | status | update | restart | install-box64 | install-wine | wine-diagnose | wine-version")
        say("          install-display | test-graphics | install-graphics-libs | game-install | test-game")
        say("          job | logs [N]")
        say("          bash [command] | bash (enter shell mode) | job-stop | stop")
        say("Use bash <command> for one command. In bash mode use 'exit' to return.")
        say("Tip: .tgll-command file also works if panel console input is unavailable.")
    elif cmd == "status":
        status()
    elif cmd == "update":
        update()
    elif cmd == "restart":
        restart()
    elif cmd == "install-box64":
        launch_job("box64-setup", ROOT / "scripts" / "install_box64.py")
    elif cmd == "install-wine":
        launch_job("wine-setup", ROOT / "scripts" / "install_wine.py")
    elif cmd == "wine-diagnose":
        launch_job("wine-diagnose", ROOT / "scripts" / "install_wine.py", ("--diagnose",))
    elif cmd == "install-display":
        launch_job("display-setup", ROOT / "scripts" / "install_display.py")
    elif cmd == "test-graphics":
        launch_job("graphics-test", ROOT / "scripts" / "test_graphics.py")
    elif cmd == "game-install":
        launch_job("game-install", ROOT / "scripts" / "install_game.py")
    elif cmd == "install-graphics-libs":
        launch_job("graphics-libs-setup", ROOT / "scripts" / "install_graphics_libs.py")
    elif cmd == "test-game":
        launch_job("game-test", ROOT / "scripts" / "test_game.py")
    elif cmd == "wine-version":
        box64 = RUNTIME / "box64" / "bin" / "box64"
        wine = RUNTIME / "wine" / "bin" / "wine"
        if not box64.is_file() or not wine.is_file():
            say("Box64 or Wine not installed. Run install-box64 and install-wine first")
        else:
            env = os.environ.copy()
            libs = RUNTIME / "x86_64-libs"
            if libs.is_dir():
                env["BOX64_LD_LIBRARY_PATH"] = str(libs) + (
                    os.pathsep + env["BOX64_LD_LIBRARY_PATH"]
                    if env.get("BOX64_LD_LIBRARY_PATH") else ""
                )
            result = subprocess.run([str(box64), str(wine), "--version"],
                                    env=env, check=False, timeout=60)
            say(f"[wine-version] exit code: {result.returncode}")
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
    elif cmd in ("stop", "quit"):
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
