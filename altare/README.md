# TGLL on Altare Python Hosting (experimental)

This deployment is **separate from HidenCloud**. Do not copy over the
HidenCloud ARM64 runtime folder or overwrite a working HidenCloud instance.

## Start the launcher

1. Create an Altare **Python** server.
2. Download the single [altare.py](../altare.py) file from this repo, and
   upload it in Altare Files to the server's working directory (usually
   `/home/container`).
3. In Altare **Startup**, select Python's main file `altare.py`. If the
   template instead allows a custom command, use `python3 -u altare.py`.
4. Start the server. The script reports architecture, libc, CPU/RAM limits,
   installed utilities, and allocated port variables, then runs the original
   interactive `app.py` launcher. It selects **TGLL** on new installations.
5. In the Altare console, run:

   ```text
   update
   status
   game-select tgll
   ```

   Note the CPU architecture shown on the very first startup lines.
   `update` fetches the current launcher scripts from this repository.
   It does not replace any existing game files or Wine prefix.

## Upload the TGLL game

The repository **does not contain** the user's Windows game archive.

1. Upload `TGLL_minCPU_v2.zip` (or `game.zip`) in Altare Files beside
   `altare.py`.
2. In Altare Console, run `setup game` and `logs 50`.
3. Extraction is complete only when the log says **SUCCESS: TGLL game extracted**.

The ZIP installer preserves the original archive, checks for
`TheGioiLangLa.exe`, `UnityPlayer.dll`, `GameAssembly.dll`, and the
Unity data directory, and refuses to overwrite existing game installations.

## Architecture-specific prerequisites

### If `aarch64` / ARM64

The pre-existing HidenCloud installers target **Debian Bookworm ARM64**.
They may work only if Altare has compatible libc / native dependencies and
the needed network access. Set up one step at a time, checking `logs 100`:

```text
setup box64
setup wine
setup display
setup graphics
setup vnc
vnc-password
```

Do not run these simultaneously: each setup operation is a separate launcher
job; wait for it to finish before the next.

To expose VNC, find your **allocated TCP port** in Altare > Network and use:

```text
vnc-public on <allocated-tcp-port>
start
```

Then use TigerVNC with the Altare hostname/IP and exactly that port.
Classic VNC is **not transport-encrypted**; use a protected private connection
where possible, and do not share the password.

### If `x86_64` / amd64

**Do not run `setup box64`, `setup display` or `setup vnc`**. These
scripts download ARM64-specific binaries. Native x86-64 Wine and matching
Xvfb/VNC/Mesa packages need an Altare-specific runtime. The existing
`run_game.py` explicitly refuses non-ARM64 CPUs.

The `altare.py` startup and `setup game` extraction work, but this is a
**preflight deployment, not a working x86-64 game renderer**. Use the console
preflight results to build the correct native runtime without guessing
architecture or installing incompatible Debian packages.

## Networking & provider policy

Altare assigns a port under its Network tab; do not assume it is 5900
or that a web/HTTP-only proxy will accept raw VNC TCP. A raw VNC client needs
a reachable TCP port; an HTTP-only allocation would need a WebSocket/noVNC
gateway instead.

Altare's fair-use and acceptable-use terms apply to Windows games and
native emulators alike. Provisioning a Python server does not exempt game
clients from resource and software policies.

This README describes **setup and diagnostics only**. No live Altare container
has been accessed or tested by this repository change.
