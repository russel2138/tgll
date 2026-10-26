# Altare Python Hosting: Java ME / game.jar

**Separate mode** added to the existing \`russel2138/tgll\` launcher. TGLL and ModDP250 Windows/Wine code, installations, Wine prefixes, and existing configuration remain intact. Source runtime follows \`russel2138/test\`: Temurin Java 17, MicroEmulator 2.0.4, Xvfb, VNC and file-backed RMS.

## Quick start

Use existing Python Hosting with Startup \`PY_FILE=altare.py\`. No need for a Java hosting egg.

Console:

\`\`\`text
stop
update
game-select jar
setup jar
job
logs 80
\`\`\`

\`setup jar\` installs rootless Java 17, MicroEmulator 2.0.4 and a private x86_64 Xvfb/x11vnc display, **without installing Wine**. If missing, it seeds \`/home/container/game.jar\` from the public \`russel2138/test\` repository. Upload your own \`game.jar\` before setup to use a custom J2ME MIDlet. An existing local \`game.jar\` is never overwritten.

When \`logs 80\` shows \`SUCCESS: Java ME runtime installed\`:

\`\`\`text
vnc-password
vnc-public on <your-altare-Network-TCP-port>
start
logs 80
vnc-info
mem
\`\`\`

Connect TigerVNC to \`<your-Altare-Network-host>::<port>\`. VNC password auth is not transport encryption; use trusted networks and avoid secrets on publicly exposed VNC. Altare must assign an externally reachable TCP allocation.

Use \`stop\` and \`game-select tgll\` to switch back to Windows TGLL; \`game-select moddp250\` is also retained. Do not run both game modes simultaneously through this launcher. Each runtime's files persist independently.

## Resources and state

- Java heap defaults \`-Xms8m -Xmx160m -XX:+UseSerialGC\`; can optionally set \`JAR_HEAP_MB=128\` or another value 32..512 in Startup env, then restart. Total RAM includes JVM native overhead, Xvfb, VNC and file cache, not only Java heap
- Display: \`400x340x16\`; Java ME resizable game area \`400x300\`
- Saves/RMS: \`/home/container/.tgll-runtime/jar-runtime/state/microemu-home/.microemulator/\` (default \`--rms file\`)
- Optional \`JAR_RMS_MODE=memory\` in Startup env for nonpersistent RMS only if game supports it; normally keep file
- Game: \`/home/container/game.jar\`
- JRE: \`/home/container/.tgll-runtime/jar-runtime/java17\`
- MicroEmulator: \`/home/container/.tgll-runtime/jar-runtime/microemu\`
- Java log: \`/home/container/.tgll-runtime/jar-game.log\`
- Old Wine/TGLL game files: **untouched**

## Troubleshooting

\`\`\`text
status
logs 100
bash tail -n 70 .tgll-runtime/jar-game.log
mem
\`\`\`

If the Java setup fails, supply the last 80 log lines. Older \`game.jar\` not containing \`META-INF/MANIFEST.MF\` with \`MIDlet-1\` is not a J2ME MIDlet and cannot be run with this emulator.

**Compatibility**: prepared for Altare Python x86_64 and not yet live-tested in the user's container. Provider terms and CPU limits still apply.
