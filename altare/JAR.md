# Altare Python Hosting — Java ME / game.jar

Chế độ JAR được thêm riêng vào repo `russel2138/tgll` theo cách chạy MicroEmulator từ `russel2138/test`. Mọi file TGLL, ModDP250, Wine, Wine prefix và VNC cũ được giữ nguyên.

## Cài đặt lần đầu

Trên Altare Python Hosting (startup `PY_FILE=altare.py`), nhập trong Console:

```text
stop
update
game-select jar
setup jar
logs 80
```

`setup jar` cài Java 17, MicroEmulator 2.0.4 và **TigerVNC (Xtigervnc)** rootless như Zampto/Ezonic, không cần Wine. Chế độ JAR chỉ chạy TigerVNC, **không fallback sang Xvfb+x11vnc**. Nếu thiếu dependency hoặc TigerVNC không khởi động được, launcher báo lỗi và dừng. Nếu thiếu `/home/container/game.jar`, script tải bản mặc định từ repo `russel2138/test`. File game do bạn upload không bị ghi đè.

Khi đã có `SUCCESS: Java ME runtime installed`, và VNC/port đã cài từ lần chạy TGLL trước, **không cần đổi mật khẩu hay cấu hình lại port**:

```text
start
logs 80
vnc-info
mem
```

Nếu server mới chưa có VNC, chạy `vnc-password` và `vnc-public on <TCP port từ Altare Network>` một lần. Classic VNC không mã hóa đường truyền.

## Nâng cấp server JAR đang chạy

Từ cấu hình x11vnc cũ, nhập:

```text
stop
update
setup jar
logs 80
start
logs 80
```

Chờ `logs` báo `SUCCESS: Java ME + TigerVNC runtime installed` rồi mới chạy `start`. Mật khẩu VNC, hostname và TCP port Altare trước đó được giữ nguyên. Nếu TigerVNC lỗi, đọc `logs 80` và `bash tail -n 80 .tgll-runtime/jar-tigervnc.log` để xử lý, không tự chạy server VNC khác.

## Đổi game và emulator

Các thư mục upload:

```text
/home/container/
├── game.jar                 # Game mặc định từ repo test
├── games/
│   ├── AUTO50_X1.jar
│   └── V9_X1.jar
└── emulators/
    ├── MICRO_NST.jar
    └── MICRO_ABC.jar
```

Emulator phải tương thích MicroEmulator và chứa class `org.microemu.app.Main`. Không dùng một JAR bất kỳ làm emulator.

Để liệt kê lựa chọn và xem cặp đang chọn:

```text
list
```

Đổi emulator và game **đồng thời, có restart** như repo `test`:

```text
restart MICRO_NST AUTO50_X1.jar
```

Hoặc chỉ đổi game, dùng emulator mặc định:

```text
restart stock V9_X1.jar
```

Chỉ đổi emulator, dùng game `game.jar`:

```text
restart MICRO_NST game.jar
```

Muốn chọn trước mà chưa mở game:

```text
stop
jar-select MICRO_NST AUTO50_X1.jar
start
```

`restart` không đối số dùng lại cặp đã lưu. Có thể nhập tên không có `.jar` nếu không trùng tên. Launcher kiểm tra file JAR và `MIDlet-1` của game trước khi lưu lựa chọn.

**Không cần gọi lại `setup jar`, `vnc-password` hay `vnc-public` khi chỉ đổi cặp emulator/game.**

## Dữ liệu và mức RAM

- Java heap mặc định `-Xms8m -Xmx160m -XX:+UseSerialGC`, có thể đặt `JAR_HEAP_MB=128` ở Startup và restart nếu cần
- Màn hình VNC 400×340×16, thiết bị MicroEmulator 400×300
- Cặp mặc định `stock + game.jar` vẫn dùng RMS tại `.tgll-runtime/jar-runtime/state/microemu-home/` để không mất dữ liệu cũ
- Cặp khác lưu riêng RMS tại `.tgll-runtime/jar-runtime/state/profiles/<game>/<emulator>/microemu-home/`
- Mặc định `--rms file` để lưu tiến trình, không xóa khi chuyển game
- Java log: `.tgll-runtime/jar-game.log`
- Lệnh kiểm tra: `status`, `logs 100`, `mem`

Chuyển về TGLL Windows vẫn dùng `stop`, `game-select tgll`, `start`. Không được chạy hai phiên game cùng một port VNC.

Runtime này đã được commit nhưng tính tương thích của từng emulator JAR do người dùng upload cần kiểm chứng bằng log và VNC trên Altare.