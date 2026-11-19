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

vnc_pid() { pgrep -f '^/usr/bin/Xtigervnc :1 ' | head -n1 || true; }
hero_pid() { pgrep -f '^java .*HERO-Emulator-V2\.jar$' | head -n1 || true; }

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
  OLD="$(vnc_pid)"
  if [ -n "$OLD" ] && ! tr '\0' ' ' < "/proc/$OLD/cmdline" | grep -Eq -- '-rfbport[[:space:]]+25627([[:space:]]|$)'; then
    tigervncserver -kill :1 >/dev/null 2>&1 || return 1
  fi
  if [ -z "$(vnc_pid)" ]; then
    tigervncserver :1 -geometry 1280x800 -depth 24 -rfbport "$PORT" \
      -localhost no -SecurityTypes VncAuth -PasswordFile "$PASS" >> "$VNCLOG" 2>&1 || {
      echo "VNC failed:"; tail -n 20 "$VNCLOG"; return 1;
    }
    sleep 2
  fi
  if [ -z "$(vnc_pid)" ]; then echo "VNC not running"; return 1; fi
  if [ -z "$(hero_pid)" ]; then
    ( cd "$ROOT" && DISPLAY=:1 XAUTHORITY=/root/.Xauthority \
      nohup java -Xms64m -Xmx384m -jar "$JAR" >> "$LOG" 2>&1 < /dev/null & )
    sleep 2
  fi
  if [ -z "$(hero_pid)" ]; then
    echo "HERO failed:"; tail -n 30 "$LOG"; return 1
  fi
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
    status) echo "VNC PID: $(vnc_pid)"; echo "HERO PID: $(hero_pid)" ;;
    logs) tail -n 60 "$LOG" "$VNCLOG" 2>/dev/null ;;
    pass) cat "$PASS_TXT" 2>/dev/null || echo "Run start first" ;;
    vnc) echo "$HOST::$PORT" ;;
    update) git -C /opt/tgll pull --ff-only && echo "Repo updated; HERO JAR unchanged" ;;
    help) echo "Commands: start stop restart status logs pass vnc update exit" ;;
    exit) return 99 ;;
    *) echo "Unknown command: $1"; return 1 ;;
  esac
}
if [ "$#" -gt 0 ]; then run "$1"; exit $?; fi
echo "HERO V2 console ready (commands: help)"
start || true
while IFS= read -r LINE; do
  read -r -a ARGS <<< "$LINE"
  [ "${#ARGS[@]}" -eq 0 ] && continue
  run "${ARGS[0]}"
  [ "$?" -eq 99 ] && break
done
while :; do sleep 3600; done
