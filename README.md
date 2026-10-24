# TGLL launcher for HidenCloud

Launcher TGLL dành cho HidenCloud Python 3.13 trên Linux ARM64, chạy tại `/home/container/app.py`

## Startup Settings được khuyến nghị (dùng Git có sẵn của host)

| Startup Settings | Giá trị |
| --- | --- |
| Server Image | Python 3.13 |
| Git Repo Address | `https://github.com/russel2138/tgll.git` |
| Git Branch | `main` |
| User Uploaded Files | `0` |
| Auto Update | `1` |
| App py file | `app.py` |
| Additional Python packages | để trống |
| Git Username | để trống |
| Git Access Token | để trống |
| Requirements file | `requirements.txt` |

Không cần thay đổi Startup Command mặc định. Repo public nên không cần GitHub username/token

**Quan trọng:** Git Repo Address và User Uploaded Files là tùy chọn của **bước cài đặt/reinstall** trong Python Egg, không phải lệnh clone chạy mỗi khi Start/Restart

- Server mới, thư mục file trống: cấu hình thông số trên, chạy bước Install/Reinstall được hỗ trợ trên panel, sau đó Start
- Server đã upload `main.py` và có các file nhưng **không có `.git`**: chỉ bật Auto Update rồi Restart **không đủ** để biến thư mục thành Git repo. Script cài đặt mẫu thậm chí có thể bỏ qua clone nếu thư mục chưa trống. Không xóa `.tgll-runtime`, file game hay dữ liệu tài khoản mà chưa sao lưu
- Nếu không muốn reinstall/xóa file: sử dụng cách bootstrap bên dưới. `update` của launcher vẫn tự tải file mới từ GitHub qua HTTPS kể cả khi không có `.git`
- Khi `.git` tồn tại: `Auto Update=1` sẽ thực hiện `git pull` ở đầu lần khởi động container. Có thể tự cập nhật trong app bằng lệnh `update` mà không cần restart cả container

## Bootstrap không cần reinstall (cho server đã dùng)

1. Tải [main.py](https://raw.githubusercontent.com/russel2138/tgll/main/main.py) và upload đè file `/home/container/main.py`
2. Đặt `App py file=main.py` (nếu vẫn giữ như cũ thì không phải thay)
3. Nhấn Start. `main.py` sẽ tải `app.py` từ GitHub nếu file chưa tồn tại
4. Trong Console nhập `update` để đồng bộ toàn bộ launcher, hoặc dùng file `.tgll-command` nếu Console không chuyển được stdin
5. Sau này có thể cập nhật qua `update`, không phải upload lại code

## Các lệnh Console

| Lệnh | Mô tả |
| --- | --- |
| `help` | Xem danh sách lệnh |
| `status` | CPU quota, RAM, kiến trúc CPU, trạng thái Box64 |
| `update` | Nếu có .git thì `git pull --ff-only`, nếu không có thì tải file launcher từ GitHub |
| `restart` | Khởi động lại tiến trình Python |
| `bash ls -la` | Chạy một lệnh Bash |
| `bash` | Vào chế độ Bash theo từng lệnh, gõ `exit` để quay lại |
| `install-box64` | Biên dịch Box64 không cần root |
| `job` | Kiểm tra tác vụ cài đặt |
| `logs 50` | Xem 50 dòng cuối log |
| `job-stop` | Gửi SIGTERM cho nhóm tiến trình cài đặt |
| `stop` | Tắt launcher, panel sẽ báo offline |

Lưu ý chế độ `bash` là từng lệnh riêng biệt, không phải interactive PTY. `cd` sẽ nhớ thư mục, nhưng `export` giữa các lần nhập sẽ không được giữ lại. Lệnh Bash thực thi với toàn bộ quyền user container, chỉ chạy lệnh tin cậy

### Nếu Console không nhận lệnh

Dùng File Manager tạo file `/home/container/.tgll-command` có nội dung `update`, `status` hoặc `install-box64`. Launcher đọc file mỗi khoảng 2 giây, xóa file sau khi đọc, hỗ trợ nhiều dòng lệnh

## Box64

Nhập `install-box64` sau khi đã đồng bộ phiên bản code mới. Script tải Box64 từ [upstream](https://github.com/ptitSeb/box64), tự cài CMake và Ninja trong `.tgll-runtime/build-tools` nếu cần, build tối đa hai tác vụ đồng thời và sao chép binary vào `.tgll-runtime/box64/bin/box64` mà không chạy `cmake --install` ghi vào `/usr/lib`. Nếu đã biên dịch thành công từ lần trước, script tái sử dụng binary và không build lại. Theo dõi `job` và `logs 50`

**Chưa có Wine64, Xvfb, Mesa renderer hoặc bước chạy game TGLL**. Thành công với Box64 chưa có nghĩa chạy được game Windows x86-64 trên Linux ARM64

## Dữ liệu và cập nhật

- `app.py`, `main.py`, `scripts/install_box64.py`, `README.md` là các file launcher do lệnh update tự cập nhật
- `.tgll-runtime/` chứa runtime, logs và source build, không bị lệnh update ở chế độ tải trực tiếp xóa
- Game và dữ liệu tài khoản là dữ liệu riêng, không đưa vào Git hoặc xóa lúc Reinstall khi chưa sao lưu
- Git pull có thể bị từ chối nếu bạn chỉnh sửa các file theo dõi trong Git trên server. Không sửa trực tiếp các file launcher trên host nếu muốn update ổn định
