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

## Khôi phục nếu lệnh update báo sai "Already up to date"

Nếu `help` hiển thị bản cũ dù GitHub đã có mã mới, chạy lệnh `bash` dưới đây với URL commit cố định để thay app.py, rồi `restart` và `update`:

```text
bash curl -fsSL --retry 3 https://raw.githubusercontent.com/russel2138/tgll/4f3a47323e5ee6c5568ac4b791f45ff25b602ca0/app.py -o /home/container/app.py.new && /usr/local/bin/python -m py_compile /home/container/app.py.new && mv /home/container/app.py.new /home/container/app.py
restart
update
```

Từ bản v2026.10.24.4, launcher lấy SHA của commit mới nhất qua GitHub API, sau đó tải code theo SHA bất biến, tránh cache cũ của `raw.githubusercontent.com/.../main/...`

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
| `install-wine` | Tải Wine x64 WOW64 đã kiểm tra SHA256 vào `.tgll-runtime/wine` không cần root |
| `wine-version` | Kiểm tra Wine chạy được qua Box64 hay không |
| `wine-diagnose` | Kiểm tra Wine và xuất nguyên nhân lỗi `ntdll.so` qua `BOX64_LOG=2` |
| `job` | Kiểm tra tác vụ cài đặt |
| `logs 50` | Xem 50 dòng cuối log |
| `job-stop` | Gửi SIGTERM cho nhóm tiến trình cài đặt |
| `stop` | Tắt launcher, panel sẽ báo offline |

Lưu ý chế độ `bash` là từng lệnh riêng biệt, không phải interactive PTY. `cd` sẽ nhớ thư mục, nhưng `export` giữa các lần nhập sẽ không được giữ lại. Lệnh Bash thực thi với toàn bộ quyền user container, chỉ chạy lệnh tin cậy

### Nếu Console không nhận lệnh

Dùng File Manager tạo file `/home/container/.tgll-command` có nội dung `update`, `status` hoặc `install-box64`. Launcher đọc file mỗi khoảng 2 giây, xóa file sau khi đọc, hỗ trợ nhiều dòng lệnh

## Box64

Nhập `install-box64` sau khi đã đồng bộ phiên bản code mới. Script tải Box64 từ [upstream](https://github.com/ptitSeb/box64), tự cài CMake và Ninja trong `.tgll-runtime/build-tools` nếu cần, build tối đa hai tác vụ đồng thời và sao chép binary vào `.tgll-runtime/box64/bin/box64` mà không chạy `cmake --install` ghi vào `/usr/lib`. Nếu đã biên dịch thành công từ lần trước, script tái sử dụng binary và không build lại. Theo dõi `job` và `logs 50`

## Wine64 (bước thử nghiệm sau Box64)

Sau khi `install-box64` đã thành công, chạy `update`, rồi `install-wine`. Installer tải bản Wine 11.19 amd64 WOW64 từ [Kron4ek/Wine-Builds](https://github.com/Kron4ek/Wine-Builds/releases/tag/11.19), kiểm tra SHA256 chính thức, giải nén vào `.tgll-runtime/wine` và thử `box64 wine --version`

Chọn 11.19 thay vì 11.20 vì release 11.20 có cảnh báo về lỗi segmentation fault khi khởi động trên một số hệ thống

Theo dõi `job` và `logs 50`. Nếu installer báo không nạp được `ntdll.so`, chạy `wine-diagnose` rồi `logs 100` để tìm `Error loading needed lib`, `Symbol ... not found` hoặc lỗi khác. Log chi tiết được giữ tại `.tgll-runtime/wine-debug.log`. Không xóa hoặc tải lại Wine khi đang chẩn đoán. Wine được lưu trên ổ đĩa người dùng và có thể chiếm dung lượng đáng kể, không yêu cầu root

**Chưa có Xvfb, Mesa renderer hoặc bước chạy game TGLL**. Thành công với Box64 và Wine version không đồng nghĩa game Unity hoạt động trên ARM64

### Sửa lỗi Wine không nạp được ntdll.so

Nếu log Box64 có `Error loading needed lib libgcc_s.so.1`, nguyên nhân là chưa có bản **amd64** của thư viện này trong đường dẫn Box64. Bản v2026.10.24.6 tự tải đúng gói Debian bookworm amd64 `libgcc-s1` (SHA256 cố định từ packages.debian.org), tách riêng `libgcc_s.so.1` vào `.tgll-runtime/x86_64-libs`, và đặt `BOX64_LD_LIBRARY_PATH` khi khởi động Wine

**Để áp dụng:** chạy `update` rồi `install-wine`, tiếp theo `logs 100`. Wine đã giải nén được tận dụng lại, không tải lại 75 MiB. Không cần sudo, apt install hay thay đổi thư viện ARM64 của hệ thống

Nên thấy `Installed amd64 libgcc_s.so.1 without root` và bước `Testing ... wine --version`. Nếu chuyển sang lỗi thư viện khác, xem `wine-diagnose` trước khi cài thêm phụ thuộc. Khi `wine-version` chạy thành công, vẫn cần Xvfb và software rendering trước khi thử game

## Dữ liệu và cập nhật

- `app.py`, `main.py`, `scripts/install_box64.py`, `scripts/install_wine.py`, `scripts/install_x86_libs.py`, `README.md` là các file launcher do lệnh update tự cập nhật
- `.tgll-runtime/` chứa runtime, logs và source build, không bị lệnh update ở chế độ tải trực tiếp xóa
- Game và dữ liệu tài khoản là dữ liệu riêng, không đưa vào Git hoặc xóa lúc Reinstall khi chưa sao lưu
- Git pull có thể bị từ chối nếu bạn chỉnh sửa các file theo dõi trong Git trên server. Không sửa trực tiếp các file launcher trên host nếu muốn update ổn định
