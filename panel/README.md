# Panel v2 — hướng khách hàng

## Ai dùng gì

| Vai trò | Đăng nhập bằng | Làm được |
|---------|----------------|----------|
| **Khách thuê** | Mã license (trial/week/month) | Kết nối Tele, thêm nhiều nhóm, xếp kịch bản tin, đặt lịch |
| **Admin (bạn)** | `PANEL_ADMIN_KEY` trong `.env` | Tạo mã (ngày **cố định**), Start/Stop bot |

Khách **không** chỉnh được số ngày / hạn license.

## Nhiều nhóm / 1 panel

Một license → nhiều nhóm (ảo hoặc thật), giới hạn `max_groups` theo gói:
- trial: 3 ngày, 2 nhóm
- week: 7 ngày, 3 nhóm  
- month: 30 ngày, 10 nhóm

## Kịch bản tin

Không còn gõ `opening_order: 0,1`. Khách:
1. Tải tin mẫu từ kênh nguồn  
2. Bấm ô “Tin mở đầu / Khi thắng / …”  
3. Bấm tin để gắn  

## URL

http://localhost:3201/panel/
