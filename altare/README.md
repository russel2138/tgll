# TGLL trên Altare Python Hosting (x86_64)

Khác HidenCloud ARM64: Altare đã được xác nhận chạy Linux **x86_64**, glibc 2.36, **1.5 vCPU**, **6.3 GiB RAM**, Python 3.14.8 và biến `SERVER_PORT=25519` trên server được test ngày 24/10/2026.

Bộ cài TGLL native nằm riêng trong `altare/native_setup.py` và `altare/native_run.py`; không sửa hay xóa file game/runtime HidenCloud. Không cần Box64.

## Python Startup

- Tạo server **Python** trên [Altare](https://console.altare.gg/)
- Upload file [altare.py](../altare.py) vào Files tại thư mục gốc
- Startup `PY_FILE=altare.py` (hoặc chạy `python3 -u altare.py` nếu dùng custom command)
- Bật server. Script `altare.py` báo thông tin CPU/RAM và tạo lựa chọn game TGLL trên server mới
- Trên Console nhập:
  ```text
  update
  status
  game-select tgll
  ```

## Cài runtime Wine + VNC native x86_64

Sau khi `update` đã lấy bộ cài mới, nhập:
```text
setup native
```

Theo dõi bằng:
```text
logs 60
job
```

Chỉ làm bước kế tiếp sau khi log hiển thị `SUCCESS: Altare native runtime installed`.
Bộ cài download các gói Debian Bookworm amd64 từ index SHA256 của Debian, giải nén vào `.tgll-runtime/altare-amd64` không có root, cài Wine amd64 WOW64 đã kiểm tra SHA256 vào `.tgll-runtime/wine`, sau đó thử Xvfb và Wine. Nếu báo `FAILED`, gửi `logs 100`, **không lặp cài liên tục**.

## Upload TGLL và cài game

Repo không chứa ZIP TGLL.
Trong Altare Files upload bản game hợp pháp của bạn dưới tên `TGLL_minCPU_v2.zip` hoặc `game.zip`, ở thư mục gốc bên cạnh `altare.py`.
Trong Console:
```text
setup game
logs 50
```
Phải thấy `SUCCESS: TGLL game extracted`. Installer sẽ không ghi đè game cũ.

## Truy cập màn hình VNC

Đầu tiên chạy:
```text
vnc-password
vnc-public on 25519
start
logs 60
vnc-info
```

`25519` là port từ log server mẫu, **phải dùng cổng TCP được cấp thực tế trong Altare > Network** nếu server khác. TigerVNC dùng `<Altare Network address>::25519`, không phải tên host HidenCloud. Nếu Altare chỉ cung cấp HTTP ingress, raw VNC/TigerVNC sẽ không truy cập được; cần xem lại Network hoặc dùng giải pháp noVNC/WebSocket riêng được phép.

**Cảnh báo:** VNC classic không mã hóa đường truyền; ưu tiên private network/tunnel nếu nhà cung cấp hỗ trợ và không chia sẻ mật khẩu.

Các lệnh hỗ trợ sau cài:
- `start`, `stop`, `restart` — chạy/dừng native TGLL
- `status`, `logs 100`, `mem`, `vnc-info` — chẩn đoán
- `vnc-scale off`, `resolution 640x480` — cấu hình màn hình
- `setup native` — tái kiểm tra/tải gói thiếu, không xóa dữ liệu

**Giới hạn:** Chưa thực thi kiểm thử TGLL trên server Altare thực tế. `update` và `setup native` chỉ cài launcher/runtime; cần xem log và kết nối VNC để xác nhận Windows Unity có chạy đúng với Mesa software rendering. Không chạy `setup box64`, `setup wine`, `setup display` hay `setup vnc` (các lệnh ARM64).

## Chính sách

Altare có quy định về ứng dụng, tài nguyên và nội dung. Đây là game client trên Python Hosting, không phải backend thông thường; cần đảm bảo mục đích sử dụng phù hợp điều khoản. Không sử dụng tên giả của tiến trình, đường hầm không được phép hay cách né giới hạn CPU.

## NRO TiênnVo EXE + SOCKS5 (không QLTK)

Chỉ áp dụng cho Altare x86_64 với Wine đã cài qua `setup native`. Không cần Box64, QLTK, .NET Framework hay cài ProxyChains bằng tay.

1. Upload ZIP gốc `[Pc]  Mod-Nro-Tiennvo(Pass giải nén 123).zip` vào thư mục chứa `altare.py`. Có thể đổi tên thành `tiennvo.zip`.
2. Trong console nhập:

```text
stop
update
game-select tiennvo
setup native
setup game
logs 80
```

`setup game` chỉ giải nén các file Unity không mã hóa, bỏ QLTK và các DLL QLTK mã hóa AES; không chạy game khi cài. Nếu `setup native` đã thành công trước đó thì chỉ cần `setup game`. Giữ nguyên phiên game và prefix JAR/TGLL cũ.

Chạy trực tiếp (không proxy):

```text
start
```

Chạy qua SOCKS5 (không cần file cấu hình thủ công):

```text
start 1.2.3.4:1080
start 1.2.3.4:1080:username:password
```

Nếu muốn đổi proxy đang chạy:

```text
restart 5.6.7.8:1080:username:password
```

`restart` không đối số sẽ dùng lại proxy của phiên gần nhất trong **bộ nhớ launcher**. `stop` rồi `start` không đối số sẽ chạy direct. Sau khi launcher/container khởi động lại, proxy không được tự khôi phục: `game-autostart` sử dụng direct. Không lưu proxy mật khẩu vào `job.json` hoặc Git.

Khi chạy với SOCKS5 lần đầu, runtime sẽ tự tải hai gói Debian `proxychains4` và `libproxychains4` (rootless, xác thực checksum) vào prefix Altare đã có, kiểm tra SOCKS5 handshake và tạo một cấu hình tạm quyền `0600`. Khi phiên game dừng bình thường, cấu hình tạm được xóa. Nếu SOCKS5 sai mật khẩu hoặc không kết nối được, launcher báo lỗi thay vì âm thầm chuyển sang direct.

**Giới hạn quan trọng:** ProxyChains-NG dùng hook libc và chỉ áp dụng cho TCP; không bảo đảm mọi kết nối của Wine/Unity đều đi qua SOCKS5. Xác minh lưu lượng bằng log hoặc Activity của nhà cung cấp proxy trước khi tin tưởng. Kết nối loopback `127.0.0.1` được giữ local cho giao tiếp nội bộ. Mật khẩu nhập vào console có thể vẫn được panel lưu trong lịch sử lệnh hoặc ghi lại trong giao diện, dù launcher không ghi lại.

Chạy thử trên Altare và theo dõi `logs 100`, `status`, `mem`. Không bảo đảm FPS hay độ ổn định của Unity trên phần mềm render CPU trước khi kiểm thử.

## Cài NRO TiênnVo + QLTK.exe trên Altare (một phiên Wine/VNC)

QLTK là chương trình .NET Framework 4.8 32-bit, tách biệt với Unity IL2CPP 64-bit. Dùng Wine WOW64 bản native AMD64, không dùng Box64 và không cài toàn bộ Windows.

Upload **ZIP TiênnVo gốc** vào `/home/container/`, nên đổi tên thành `tiennvo.zip`. ZIP của TiênnVo đặt password `123` cho bảy file QLTK AES, còn phần Unity game không mã hóa.

Console:

```text
stop
update
game-select tiennvo
setup native
setup game
setup qltk
logs 100
```

- Nếu đã chạy `setup native` thành công trước đó thì không cần chạy lại
- Chờ `setup game` hoàn thành rồi mới nhập `setup qltk`, không chạy hai job song song
- `setup qltk` cài 7-Zip từ Debian vào private prefix không cần root, giải mã riêng đúng bảy file QLTK bằng password ZIP công khai `123` và giữ các file Unity/RMS/TGLL hiện tại
- `setup qltk` tải **Wine Mono 11.3.0** từ GitHub release và xác thực SHA256, sau đó cài MSI vào prefix TiênnVo riêng (có Xvfb tạm khi cài). Mục đích là hỗ trợ .NET Framework 4.8/WinForms mà chưa cần cài .NET 4.8 chính thức
- Hoàn tất mới đánh dấu `qltk on`. Không tự chạy `QLTK.exe` trong bước setup

Sau setup, chạy bình thường:

```text
start
```

Hoặc sử dụng SOCKS5:

```text
start 1.2.3.4:1080
start 1.2.3.4:1080:user:pass
```

`start` sẽ mở **game Unity + QLTK** trên cùng Wine prefix/display/VNC. Game vẫn dùng 400×340 (trừ khi bạn đổi `resolution`), nhưng desktop VNC mở rộng mặc định lên 1280×800 để nhìn trọn cửa sổ QLTK. SOCKS5 TCP qua ProxyChains được áp dụng cho cả game và QLTK nếu bạn truyền proxy; localhost `127.0.0.1` được giữ local cho giao tiếp giữa hai chương trình.

Có thể tạm không mở QLTK:

```text
stop
qltk off
start
```

Bật lại:

```text
stop
qltk on
start
```

QLTK **không được bảo đảm hoạt động** trên Wine Mono: UI Guna/WinForms, login/license hoặc tương tác socket phụ thuộc vào mã nguồn mod và khả năng tương thích thực tế. Nếu QLTK đóng hoặc không hiện trong VNC, hãy xem `status` rồi `bash tail -n 100 .tgll-runtime/game-live-qltk.log`; game không bị dừng chỉ vì QLTK tự thoát. Nếu thiếu API .NET, đánh giá log trước khi cân nhắc .NET 4.8 thật; không cài bổ sung tự động.

**Lưu ý bảo mật:** ZIP/EXE là phần mềm bên thứ ba chưa được xác minh hoàn toàn; tránh tài khoản chính khi thử. VNC không mã hóa, không đăng mật khẩu proxy/game lên GitHub; mật khẩu proxy gõ vào panel có thể còn trong lịch sử của nhà cung cấp. Kiểm tra CPU/RAM và điều khoản Altare trước khi treo 24/7.

## QLTK bị cắt cạnh phải hoặc lỗi dấu tiếng Việt trong Wine

Các phiên bản trước chỉ dùng desktop 800×600 cho QLTK. WinForms/Guna UI TiênnVo có thể lớn hơn màn hình này, làm cắt nút phía phải và phía dưới. Từ bản cập nhật này:

- Khi bật QLTK, **desktop VNC mặc định 1280×800**; game Unity vẫn dùng độ phân giải đã chọn (mặc định 400×340), không tăng kích thước render game
- Khi tắt QLTK, màn hình nhỏ của game vẫn được sử dụng như trước
- Có thể chỉnh riêng desktop QLTK (ví dụ `qltk-display 1440x900`), không sử dụng lệnh `resolution` để sửa lỗi bị cắt vì lệnh đó điều chỉnh cả game
- Font DejaVu Sans được cài **rootless** từ gói Debian đã xác minh SHA256 vào Wine prefix TiênnVo; không động đến các Wine prefix khác. Wine fontconfig được ưu tiên font Unicode cho Tahoma, Arial, Segoe UI, Microsoft Sans Serif
- Do Guna UI có thể dùng font tùy biến hoặc bản thân nội dung thiếu glyph, việc cài font **có thể không xử lý hết** các ô vuông; cần ảnh/log sau khi chạy để xác minh

Nếu QLTK đã được cài và đang mở nhưng giao diện bị cắt, chạy từng lệnh sau:

```text
stop
update
setup qltk-fonts
logs 60
vnc-scale off
start
```

Chờ `setup qltk-fonts` kết thúc trước khi dùng `start`. Kết nối VNC lại sau khi restart để VNC Viewer nhận màn hình mới. Nếu muốn kiểm tra hoặc đổi kích thước:

```text
qltk-display
stop
qltk-display 1440x900
start
```

Trong VNC viewer có thể bật fit-to-screen hoặc cuộn để quan sát toàn bộ màn hình. `vnc-scale on` trên Altare có thể thu nhỏ 1280×800 xuống 640×480, phù hợp xem toàn cảnh nhưng chữ sẽ nhỏ. Không cần đổi cổng, mật khẩu VNC, dữ liệu tài khoản hoặc cài lại `setup qltk`.
