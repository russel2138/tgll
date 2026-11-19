#!/usr/bin/env bash
# Dedicated HERO Emulator V2 launcher for Altare Debian container.
set -u
ROOT=/opt/nroemu
JAR=/opt/nroemu/emulators/HERO-Emulator-V2.jar
PORT=25627
HOST=sg-sgp03.altare.global
PASS=/root/.vnc/passwd
PASS_TXT=/root/vnc-password.txt
LOG=/opt/nroemu/hero.log
VNCLOG=/opt/nroemu/vnc.log
XSTARTUP=/root/.vnc/hero-xstartup

vnc_pid() { pgrep -f '^/usr/bin/Xtigervnc :1 ' | head -n1 || true; }
hero_pid() { pgrep -f '^java .*HERO-Emulator-V2\.jar$' | head -n1 || true; }

# Fill the VNC desktop with the HERO application window (X11).
# xdotool resizes the X11 window directly, even without a window manager.
maximize() {
  if ! command -v xdotool >/dev/null 2>&1; then
    echo "[hero] Installing window resize helper xdotool..."
    DEBIAN_FRONTEND=noninteractive apt-get install -y xdotool >/dev/null 2>&1 || {
      echo "[hero] Cannot install xdotool; HERO can still run."
      return 1
    }
  fi
  local pid win attempt
  pid="$(hero_pid)"
  [ -n "$pid" ] || { echo "[hero] HERO is not running"; return 1; }
  for attempt in $(seq 1 20); do
    win="$(DISPLAY=:1 XAUTHORITY=/root/.Xauthority xdotool search --onlyvisible --pid "$pid" 2>/dev/null | head -n 1)"
    if [ -z "$win" ]; then
      win="$(DISPLAY=:1 XAUTHORITY=/root/.Xauthority xdotool search --onlyvisible --name "HERO" 2>/dev/null | head -n 1)"
    fi
    if [ -n "$win" ]; then
      DISPLAY=:1 XAUTHORITY=/root/.Xauthority xdotool windowmove "$win" 0 0
      DISPLAY=:1 XAUTHORITY=/root/.Xauthority xdotool windowsize "$win" 1280 800
      echo "[hero] HERO window expanded to 1280x800 (window $win)"
      return 0
    fi
    sleep 1
  done
  echo "[hero] Window not detected yet; retry with: hero maximize"
  return 1
}

start() {
  if [ ! -s "$JAR" ]; then echo "HERO JAR missing: $JAR"; return 1; fi
  mkdir -p /root/.vnc "$ROOT"
  chmod 700 /root/.vnc
  if [ ! -s "$PASS" ]; then
    if [ -s "$PASS_TXT" ]; then
      PASSWORD="$(head -n1 "$PASS_TXT")"
    else
      PASSWORD="$(openssl rand -hex 4)"
      printf '%s\n' "$PASSWORD" > "$PASS_TXT"
      chmod 600 "$PASS_TXT"
    fi
    printf '%s\n' "$PASSWORD" | tigervncpasswd -f > "$PASS" || return 1
    chmod 600 "$PASS"
  fi
  # Run a minimal X session instead of Debian's default Xtigervnc-session,
  # which launches the unwanted clipboard settings panel (vncconfig).
  cat > "$XSTARTUP" <<'HERO_XSTARTUP'
#!/bin/sh
exec sleep infinity
HERO_XSTARTUP
  chmod 700 "$XSTARTUP"
  OLD="$(vnc_pid)"
  if [ -n "$OLD" ] && ! tr '\0' ' ' < "/proc/$OLD/cmdline" | grep -Eq -- '-rfbport[[:space:]]+25627([[:space:]]|$)'; then
    tigervncserver -kill :1 >/dev/null 2>&1 || return 1
  fi
  if [ -z "$(vnc_pid)" ]; then
    tigervncserver :1 -geometry 1280x800 -depth 24 -rfbport "$PORT" \
      -xstartup "$XSTARTUP" \
      -localhost no -SecurityTypes VncAuth -PasswordFile "$PASS" >> "$VNCLOG" 2>&1 || {
      echo "VNC failed:"; tail -n 20 "$VNCLOG"; return 1;
    }
    sleep 2
  fi
  if [ -z "$(vnc_pid)" ]; then echo "VNC not running"; return 1; fi
  # Cleanup only; the custom X startup prevents future clipboard popups.
  pkill -x vncconfig 2>/dev/null || true

  if [ -z "$(hero_pid)" ]; then
    ( cd "$ROOT" && DISPLAY=:1 XAUTHORITY=/root/.Xauthority \
      nohup java -Xms64m -Xmx384m -jar "$JAR" >> "$LOG" 2>&1 < /dev/null & )
    sleep 2
  fi
  if [ -z "$(hero_pid)" ]; then
    echo "HERO failed:"; tail -n 30 "$LOG"; return 1
  fi
  maximize || true
  echo "HERO RUNNING: $(hero_pid)"
  echo "TigerVNC: $HOST::$PORT"
  echo "Password: hero pass"
}
stop() {
  PID="$(hero_pid)"
  if [ -n "$PID" ]; then kill "$PID" 2>/dev/null || true; fi
  tigervncserver -kill :1 2>/dev/null || true
  echo "HERO / VNC stopped"
}
run() {
  case "$1" in
    start) start ;;
    stop) stop ;;
    restart) stop; sleep 2; start ;;
    maximize) maximize ;;
    status) echo "VNC PID: $(vnc_pid)"; echo "HERO PID: $(hero_pid)" ;;
    logs) tail -n 60 "$LOG" "$VNCLOG" 2>/dev/null ;;
    pass) cat "$PASS_TXT" 2>/dev/null || echo "Run start first" ;;
    vnc) echo "$HOST::$PORT" ;;
    update)
      if git -C /opt/tgll pull --ff-only; then
        echo "Repo updated; HERO JAR unchanged"
        if [ "${HERO_CONSOLE_MODE:-0}" = 1 ]; then
          echo "Reloading HERO console and applying fullscreen window..."
          exec bash /opt/tgll/altare/hero-console.sh
        fi
      else
        echo "Update failed; existing session continues"
        return 1
      fi
      ;;
    help) echo "Commands: start stop restart status logs pass vnc maximize update exit" ;;
    exit) return 99 ;;
    *) echo "Unknown command: $1"; return 1 ;;
  esac
}
if [ "$#" -gt 0 ]; then run "$1"; exit $?; fi
export HERO_CONSOLE_MODE=1
echo "HERO V2 console ready (commands: help)"
start || true
while IFS= read -r LINE; do
  read -r -a ARGS <<< "$LINE"
  [ "${#ARGS[@]}" -eq 0 ] && continue
  run "${ARGS[0]}"
  [ "$?" -eq 99 ] && break
done
while :; do sleep 3600; done
