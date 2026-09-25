# Sale làm nhóm

Panel: http://103.149.87.89/panel/

Một khách = một mã = một số Telegram. Thêm nhóm thì dùng lại mã đó.

Ba loại nhóm:

- **Thật** — hô theo giờ, kết quả lấy từ bàn đang đánh.
- **Ảo** — hô theo giờ, thắng thua theo tỉ lệ mình đặt.
- **24/24** — hô suốt ngày. Cần 2 nhóm Telegram: một nhóm nhận tin hô, một nhóm nhận ảnh bàn.

Góc trái dưới hiện còn bao nhiêu ngày, được bao nhiêu nhóm, và được tạo loại nào.

---

## Cấp mã

1. Chọn gói. Thử = 2 nhóm, tuần = 3, tháng = 10.
2. Ghi chú = tên khách.
3. Tick loại khách mua. Bỏ tick loại không bán.
4. **Cấp mã** → gửi mã cho khách.

Khách mất mã: **Sao chép**. Thêm ngày: **+7 ngày**. Khách nghỉ: **Thu hồi**. Đổi loại nhóm hoặc số nhóm: **Sửa**.

Lần đầu khách đăng nhập là mã bắt đầu đếm ngày.

---

## Setup cho khách

Khách dán mã → **Tiếp tục**.

**1. Nối Telegram** (một lần)

Menu **Tài khoản Telegram**.

Khách mở https://my.telegram.org → **API development tools** → copy API ID và API Hash.

Điền tên, số `+84...`, API ID, API Hash. Có mật khẩu 2 lớp thì điền, không có thì bỏ trống.

**Lưu phiên** → **Gửi mã** → khách lấy mã 5 số trên Telegram → dán → **Xác nhận**.

**2. Lấy ID nhóm**

Mở https://web.telegram.org → vào nhóm. Số sau dấu `#` trên thanh địa chỉ, thêm `-100` phía trước.

`#1234567890` thành `-1001234567890`.

Số Telegram vừa nối phải đang ở trong nhóm.

**3. Tạo nhóm**

**Quản lý nhóm** → **Thêm nhóm**. Chỉ hiện loại đã tick lúc cấp mã. Thiếu loại thì admin **Sửa** mã, tick thêm, khách tải lại trang.

- Thật hoặc Ảo: điền tên, ID nhóm, bao lâu một lần (2/5/10/15/30/60 phút), giờ bắt đầu và giờ kết thúc → **Tạo nhóm**.
- 24/24: điền thêm ID nhóm ảnh bàn. Hai ID phải khác nhau.

**4. Tùy chỉnh** → **Lưu cấu hình**

- **Mức cược**: số hiện trên tin, ví dụ `1000`.
- **Mỗi lần hô mấy ván** (thật/ảo): 1, 2 hoặc 3. Hết ca: thắng cộng mức, thua trừ mức, hòa = 0. Thắng 2 thua 1, mức 1000 = +1000.
- Nhóm ảo: thắng + thua + hòa = 100. Mặc định 80 / 15 / 5.
- Câu hô để **Có sẵn**. Khách muốn chữ riêng thì chọn **Tin tự soạn** → **Chèn mẫu CON/CÁI có icon**.
- Thật/ảo muốn kéo tin mẫu: **Tải mẫu từ kênh**, kéo tin vào ô Mở đầu / Thắng / Thua / Hòa / Kết thúc.
- 24/24: nghỉ giữa 2 ván để `0.8`. Gửi bằng tài khoản khách thì chọn **Boss Tele**. Gửi bằng bot thì chọn **BotFather**, thêm bot vào cả 2 nhóm, dán token.

**5. Bật**

Nhóm để **ĐANG VẬN HÀNH** → **Bật các nhóm đang mở** → **Kiểm tra nhóm**.

Lỗi kiểm tra = sai ID, hoặc tài khoản/bot chưa vào nhóm.

---

## Việc hay gặp

| Khách nói | Làm |
|---|---|
| Không thấy loại nhóm | Admin **Sửa** mã, tick loại đó |
| Đã đủ nhóm | Admin tăng số nhóm, hoặc **Tắt** nhóm cũ |
| 24/24 không tạo được | Thiếu nhóm ảnh bàn, hoặc 2 ID giống nhau |
| Sửa giờ, mức, câu hô | **Tùy chỉnh** → sửa → **Lưu cấu hình** |
| Nghỉ một nhóm | **Tắt** nhóm đó |
| Nghỉ hẳn | Admin **Thu hồi** mã |
