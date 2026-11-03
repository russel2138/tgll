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

`start` khi QLTK đang bật sẽ **chỉ mở QLTK** trên Wine/VNC. QLTK tự mở Unity khi bạn nhấn **Login**, tránh mở game trùng. Khi `qltk off`, `start` mới mở EXE game trực tiếp. Game vẫn dùng 400×340 (trừ khi bạn đổi `resolution`), nhưng desktop VNC mở rộng mặc định lên 1280×800 để nhìn trọn cửa sổ QLTK. SOCKS5 TCP qua ProxyChains được áp dụng cho cả game và QLTK nếu bạn truyền proxy; localhost `127.0.0.1` được giữ local cho giao tiếp giữa hai chương trình.

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

## TiênnVo QLTK: bộ font đã cài nhưng dấu tiếng Việt vẫn thành ô vuông

Đã xác nhận trong `QLTK.exe` từ ZIP của TiênnVo có tham chiếu trực tiếp đến font **Segoe UI** và **Microsoft Sans Serif**. Chỉ cài font DejaVu + Fontconfig alias có thể chưa đủ vì GDI/WinForms/Wine có cơ chế chọn font riêng. WineHQ xác nhận Wine hỗ trợ mapping theo user tại `HKCU\\Software\\Wine\\Fonts\\Replacements`.

Bản mới của `setup qltk-fonts` sẽ đăng ký hai font này thành alias **DejaVu Sans** trong *Wine prefix riêng TiênnVo* (không can thiệp game JAR, TGLL hoặc prefix khác). Các font DejaVu đã tải trước đó được tái sử dụng; chỉ thêm registry alias, không cần tải/cài lại game. Cấu hình tự lưu trong prefix và sẽ tự áp dụng khi khởi chạy QLTK mới.

Console:

```text
stop
update
setup qltk-fonts
logs 50
start
```

Chờ `logs` báo `Wine font substitutions registered for QLTK UI` và `Unicode fonts ready` trước khi `start`. Không cần thay `qltk-display` hoặc `resolution` vì giao diện đã đủ. Chụp lại màn hình VNC nếu lỗi dấu vẫn còn; khi đó nguyên nhân có thể là font đã embed trong Guna UI hoặc cách ứng dụng xử lý glyph riêng, không nên cài thêm các font ngẫu nhiên hay sửa binary EXE vội.

## Sửa cơ chế QLTK mở game khi Login (Altare, bản 2026.11.03.3)

QLTK sở hữu chức năng login, và **tự sinh tiến trình `MOD_Tiennvo_249.exe`** khi người dùng nhấn **Login**. Các bản launcher trước đây chạy game một lần trước QLTK, khiến màn hình có hai phiên game và nhiễu khi chẩn đoán màn hình đen.

Cơ chế sau khi sửa:

- `qltk on` (mặc định sau setup): `start` chỉ mở QLTK + VNC, không khởi động EXE Unity. Sau đó chọn tài khoản và bấm **Login** trong QLTK để game mở lên
- `qltk off`: `start` mở EXE Unity bình thường, vẫn truyền kích thước game 400×340 (hoặc đã thiết lập)
- Wine prefix, môi trường X11 và thư mục làm việc được giữ nguyên. QLTK thoát sớm sẽ ghi log, nhưng không tự đóng VNC vì nó có thể đã mở game con. Lệnh `stop` sẽ đóng toàn bộ tiến trình Wine trong prefix TiênnVo

Cập nhật:

```text
stop
update
qltk on
start
```

**Bấm Login trong QLTK, không cần tự mở game thứ hai.** Khi cần chẩn đoán màn đen của *game được mở bởi QLTK*, xem log `game-live-qltk.log` và Player.log mà Unity tự ghi trong Wine prefix. Lưu ý tham số `-screen-width`/ `-logFile` chỉ có ở chế độ `qltk off` vì QLTK kiểm soát tham số khi khởi chạy game.

## Chẩn đoán WineD3D black screen/page fault khi QLTK mở Unity

Nếu crash stack có `wined3d` → `d3d11` → `UnityPlayer` hoặc game hiển thị đen sau Login, không mặc định coi là lỗi CPU/RAM hay tài khoản. Giữ nguyên game, QLTK, Wine prefix và font. Không tự thêm hoặc xóa `csmt` Registry (người dùng có thể đã hoàn tác thử nghiệm trước đó).

Sau `stop` và `update`, phiên mặc định:

```text
graphics default
qltk on
start
```

Sau đó bấm **Login** trong QLTK. Nếu màn hình vẫn đen, dừng phiên rồi thử một chế độ WineD3D khác có thể **truyền xuống tiến trình Unity do QLTK tạo**:

```text
stop
graphics glsl-vkd3d
qltk on
start
```

`glsl-vkd3d` dùng `WINE_D3D_CONFIG=shader_backend=glsl-vkd3d`, được các nhánh Wine 11 gần đây hỗ trợ. Nó là phương án thử nghiệm thay đổi shader compiler, **không bảo đảm sửa lỗi và có thể làm game chậm/crash**. Cả QLTK lẫn game con kế thừa biến môi trường này. Nếu không hiệu quả, trả về `stop` → `graphics default`.

Các chế độ Unity trực tiếp, không thể truyền qua QLTK (vì QLTK tự tạo command-line cho game):

```text
stop
qltk off
graphics bitblt
start
```

Đổi `graphics bitblt` thành `graphics glcore` hoặc `graphics singlethread` để thử lần lượt. Đó là cờ Unity chính thức `-force-d3d11-bitblt-model`, `-force-glcore` và `-force-d3d11-singlethreaded`. Chế độ này có thể kiểm chứng renderer, nhưng không thay thế quy trình Login qua QLTK. Đổi về `graphics default` trước khi bật lại QLTK.

Lệnh `graphics` không có đối số hiển thị mode hiện tại. Mode được lưu cục bộ ở `.tgll-runtime/tiennvo-graphics.json` (không lưu tài khoản/password), chỉ có hiệu lực khi `start` phiên mới. `status` có `graphics_mode`. Không có bước nào đụng tới `HKCU\\Software\\Wine\\Direct3D\\csmt`.

Nếu game vẫn đen/crash, giữ log QLTK và Player.log mới; đặc biệt tìm lỗi `Unhandled exception`, `wined3d`, `d3d11`, `dxgi`. Lưu ý lỗi `BaseLib` assembly .NET của QLTK khác với `baselib.dll` native Unity. Không tải DLL từ nguồn không đáng tin.

## Tool Up Đệ Cơ Bản TiênnVo (file ZIP đã commit lên GitHub)

Nguồn: `[TiennVo.Net]Tool Up De Basic.zip` ở commit `f45aebcf` (61 MB). SHA256: `b7bb0302e4a0d7dce961a17538eb2b752319c4eb0ce4ef23bff1c8c822cb5901`.

Đã kiểm tra tĩnh 110 file, 300 MiB sau giải nén, không mã hóa. ZIP chứa:

- `QLTK.exe`: .NET Framework 4.7.2 32-bit
- `DragonBoy166.exe` và `Run/Dragonboy_vn_v229.exe`: hai client Unity Mono 32-bit
- Các DLL và tài nguyên đi kèm nằm đúng trong cây thư mục ZIP

Đây là **bộ mới khác `MOD_Tiennvo_249.exe` x64/IL2CPP**, không chạy chồng với profile cũ. Wine 11.19 với WoW64 có thể chạy ứng dụng Windows 32-bit trên Altare x86_64, nhưng GUI và đồ họa chưa được kiểm chứng thực tế.

### Cách dùng

```text
stop
game-autostart off
update
game-select upde
setup game
logs 80
```

- Cần `setup native` thành công ít nhất một lần trước đó, không cần cài lại nếu Wine/Xvfb/VNC hiện có hoạt động
- `setup game` tự download ZIP từ **commit GitHub cố định**, kiểm tra SHA256 và giải nén an toàn vào `game-upde/` (không chạy file EXE lúc cài)
- Cùng job tự cài Wine Mono vào prefix riêng `.tgll-runtime/altare-wineprefix-upde`, cài font DejaVu và bật QLTK
- Chờ log `SUCCESS: Up Đệ Basic installed, QLTK enabled` trước khi chạy `start`
- Lúc `start` chỉ mở QLTK và VNC. QLTK chọn tài khoản và **Login** để mở game, không pre-launch Unity
- Không cần proxy: `start` (không có đối số) là direct

```text
start
status
logs 80
```

Nếu muốn chỉ mở game để kiểm tra giao diện (không tự đăng nhập bằng QLTK):

```text
stop
qltk off
start
```

Khôi phục cơ chế QLTK:

```text
stop
qltk on
start
```

Game cũ, JAR và dữ liệu khác không bị xóa. Có thể quay lại `stop` → `game-select tiennvo` → `start`. Cấu hình `graphics` cho TiênnVo IL2CPP cũ không được áp vào profile Up Đệ.

Trong hướng dẫn gốc, tác giả khuyên bật **Giảm CPU** khi treo VPS. Theo tài liệu đi kèm, giảm CPU mức cao có thể giảm FPS hiển thị mà không ảnh hưởng tốc độ up. Đây là mô tả của tác giả, không phải benchmark xác nhận trên Altare.

**Chú ý:** ZIP gồm phần mềm thứ ba không có mã nguồn để kiểm toán đầy đủ. Không dùng tài khoản chính khi mới thử; tuân thủ quy định dịch vụ và theo dõi CPU/fair-use. Nếu chạy đen/crash, lấy `logs 80`, `bash tail -n 80 .tgll-runtime/game-live-qltk.log` và Player.log trong prefix Up Đệ trước khi chỉnh renderer.

## Up Đệ Basic: QLTK thoát code 1, Wine Mono báo #VMData / mscorlib

Log có thể hiển thị:

```text
Unknown heap type: #VMData
Failed to run module constructor ... mscorlib.dll type:TypeInitializationException
QLTK wrapper exited code 1
```

Đây là lỗi khởi động ứng dụng .NET trên **Wine Mono**, chưa liên quan tới Unity/Direct3D. Tham chiếu `#VMData` có thể liên quan metadata đặc biệt của chương trình được bảo vệ/obfuscate. Không sửa EXE hay gỡ bảo vệ. WineHQ có trường hợp lỗi tương tự được khắc phục bằng Microsoft .NET Framework 4.8.

### Thử Microsoft .NET Framework 4.8 an toàn (tùy chọn)

Launcher dùng **Wine prefix thứ hai**: `.tgll-runtime/altare-wineprefix-upde-netfx`. Prefix Wine Mono cũ `.tgll-runtime/altare-wineprefix-upde` và dữ liệu game `game-upde/` **không bị sửa**. Không sửa Registry CSMT, không dùng proxy.

```text
stop
update
game-select upde
setup upde-dotnet
logs 80
```

`setup upde-dotnet` yêu cầu ít nhất 2 GiB dung lượng đĩa trống và tải Microsoft .NET Framework 4.8 thông qua Winetricks phiên bản ghim commit, cùng các dependency rootless từ Debian. Chỉ thao tác trong prefix mới; quá trình cài có thể không tương thích Wine 11 WoW64. Log chi tiết ở `.tgll-runtime/upde-dotnet48-install.log`, có thể xem:

```text
bash tail -n 80 .tgll-runtime/upde-dotnet48-install.log
```

Khi log báo **SUCCESS: Microsoft .NET Framework 4.8 installed**, chọn runtime rồi chạy:

```text
upde-runtime netfx
start
```

Sau đó vào TigerVNC xem **QLTK** có hiện giao diện không. Nếu QLTK vẫn không hoạt động hoặc muốn về trạng thái trước:

```text
stop
upde-runtime mono
start
```

`upde-runtime` (không tham số) sẽ hiển thị mode hiện tại. Không cho chọn `netfx` nếu setup chưa xác minh được Microsoft .NET release Registry (>= 528040).

**Lưu ý:** Thành công khi cài runtime **không có nghĩa QLTK hoặc Unity chắc chắn hoạt động**. Không tự đăng nhập trong bước cài. Winetricks sẽ tải installer chính hãng và kiểm chứng checksum riêng, nhưng một số phiên bản Wine mới WoW64 gặp lỗi cài .NET 4.x. Nếu cài thất bại, giữ nguyên Mono prefix, xem log trước khi thử tiếp. Mọi thay đổi chỉ là thử nghiệm tương thích, cần cân nhắc dung lượng và điều khoản lưu trú/compute của Altare.

## Up Đệ Basic: tiếng Việt hiển thị ô vuông trên Wine Mono hoặc .NET 4.8

Bộ `setup game` trước đây chỉ copy DejaVu fonts vào prefix Mono của Up Đệ. Prefix .NET 4.8 là thư mục riêng, vì vậy có thể thiếu font dù bản Mono đã có. Ngoài Fontconfig, ứng dụng WinForms có thể gọi Windows family theo tên, cần đăng ký mapping trong Wine.

Sau khi **hoàn tất** công việc cài `setup upde-dotnet` (kiểm tra `job` đã xong) và dừng mọi phiên game:

```text
stop
update
game-select upde
setup upde-fonts
logs 60
```

Lệnh sửa font chỉ sửa các prefix Up Đệ đã được tạo `.tgll-runtime/altare-wineprefix-upde` và `.tgll-runtime/altare-wineprefix-upde-netfx`, không tạo prefix mới. Nó copy bốn file DejaVu từ gói Debian đã xác minh vào `drive_c/windows/Fonts`, áp dụng alias Wine Registry cho `Segoe UI` và `Microsoft Sans Serif` → `DejaVu Sans` rồi cập nhật Fontconfig của Up Đệ. Có thể chạy lại nhiều lần, không xóa game, tài khoản, QLTK hay cài lại runtime.

Khi thấy `[upde-fonts] SUCCESS: repaired fonts in ...` và đã cài .NET thành công:

```text
upde-runtime netfx
start
```

Việc sửa font **không giải quyết lỗi Wine Mono `Unknown heap type: #VMData`**, và không bảo đảm sửa glyph tùy biến của Guna UI. Nếu QLTK .NET 4.8 vẫn chưa mở được hoặc font vẫn sai, xem `game-live-qltk.log` hoặc gửi ảnh VNC mới.
