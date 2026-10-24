# TGLL launcher for HidenCloud

Launcher cho container Python trên HidenCloud (Linux ARM64), không cần quyền root để chạy `app.py`

## Thiết lập lần đầu

1. Tải [main.py](https://raw.githubusercontent.com/russel2138/tgll/main/main.py) từ GitHub và upload đè `/home/container/main.py` trong File Manager của HidenCloud
2. Giữ nguyên Startup `PY_FILE=main.py` như hiện tại
3. Start server. `main.py` sẽ tự tải `app.py` từ GitHub trong lần chạy đầu tiên, sau đó mở launcher
4. Trong Console gõ `update` để tải các file launcher mới nhất. Sau update, Python tự khởi động lại

Nếu dùng `git clone` toàn bộ repository vào `/home/container`, lệnh `update` sẽ dùng `git pull --ff-only` thay vì tải các file riêng lẻ

## Các lệnh Console

| Lệnh | Mô tả |
| --- | --- |
| `help` | Xem lệnh |
| `status` | CPU quota, RAM, CPU architecture, công cụ |
| `update` | Đồng bộ launcher từ GitHub rồi khởi động lại nếu cần |
| `restart` | Khởi động lại Python launcher, không khởi động lại container |
| `bash ls -la` | Thực thi một lệnh Bash trong thư mục /home/container |
| `bash` | Chế độ Bash theo từng lệnh, gõ `exit` để quay lại launcher |
| `install-box64` | Cài Box64 không cần root trong background |
| `job` | Xem PID của tác vụ đang chạy |
| `logs 50` | Xem 50 dòng log cuối |
| `job-stop` | Gửi yêu cầu dừng tác vụ nền |
| `stop` | Dừng launcher, panel có thể báo offline hoặc crash (exit 0) |

Lệnh `bash` có hai chế độ. `bash <command>` chạy toàn bộ command trong một lần gọi Bash. Chế độ `bash` không tham số hỗ trợ `cd` duy trì thư mục hiện tại, nhưng không duy trì các biến `export` giữa hai dòng

### Khi Console không truyền được lệnh cho Python

Trong File Manager, tạo file `/home/container/.tgll-command` với nội dung như `update`, `status` hoặc `install-box64`

Launcher sẽ đọc file (tối đa khoảng 2 giây) rồi tự xóa file đó. Hỗ trợ nhiều lệnh, mỗi dòng một lệnh

## Cài Box64

Trong Console gõ `update` trước để lấy mã installer, sau đó chạy `install-box64`. Xem `logs 50` và `job`. Log nằm trong `/home/container/.tgll-runtime/box64-setup.log`

Installer tải source chính thức của [Box64](https://github.com/ptitSeb/box64), tự cài CMake + Ninja bằng pip (không cần GNU Make hay sudo), build tối đa 2 job rồi cài vào `.tgll-runtime/box64`

**Giới hạn:** Đây mới là bước thử Box64, chưa cài Wine64/Xvfb/Mesa và chưa chạy game. Game TGLL là Unity Windows x86-64, máy HidenCloud là Linux ARM64. Cài thành công Box64 không bảo đảm game chạy được

## Quản lý dữ liệu

File do launcher quản lý: `main.py`, `app.py`, `scripts/install_box64.py`, `README.md`

Runtime, source build, logs nằm trong `.tgll-runtime/`, **không bị lệnh update xóa**

Game riêng, dữ liệu tài khoản và các thư mục khác của người dùng không bị lệnh update thay đổi

Launcher không cần dịch vụ web, không mở port, không cần GitHub token cho repo public
