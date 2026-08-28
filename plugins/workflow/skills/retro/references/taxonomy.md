# Bộ từ vựng tag và context

Đặt tag tùy hứng mỗi lần một kiểu sẽ làm recall theo tag vô dụng. Chọn từ danh sách dưới; chỉ thêm từ
mới khi thật sự không có từ nào phủ được, và khi thêm thì ghi bổ sung vào file này.

## Tag

Mỗi bản ghi nên có **3–6 tag**, lấy từ ít nhất hai nhóm dưới đây để recall bắt được từ nhiều hướng.

### Nhóm hệ thống / dự án

`farmnet` · `farmlink` · `odoo` · `plane` · `grpc` · `postgres` · `docker` · `github`

### Nhóm công cụ

`mcp` · `hindsight` · `rtk` · `cli` · `git`

### Nhóm môi trường

`prod` · `preprod` · `dev` · `ci`

### Nhóm bản chất bài học

`gotcha` — công cụ hoặc API cư xử gây hiểu nhầm
`convention` — quy ước của repo/tổ chức
`workflow` — trình tự thao tác
`debugging` — cách lần ra nguyên nhân
`pattern` — mẫu lỗi hoặc mẫu thiết kế lặp lại
`config` — cấu hình, đường dẫn, biến môi trường
`testing` — quy ước và hạ tầng test
`preference` — sở thích, cách làm việc người dùng muốn

### Nhóm miền nghiệp vụ (FarmNet)

`planning` · `disbursement` · `sale_order` · `payment_request` · `accounting` · `security` · `release`

## Context

Trường `context` là một chuỗi ngắn mô tả *bối cảnh áp dụng*, không phải nhắc lại tag. Dùng lại các giá
trị đã có thay vì đặt mới:

- `farmnet ops` — vận hành, đọc log, tra dữ liệu prod
- `farmnet odoo coding rules` — quy tắc viết code trong repo
- `farmnet odoo testing convention` — quy ước viết test
- `farmnet testing infrastructure` — hạ tầng chạy test, CI
- `farmnet-github repo release workflow` — quy trình release, tag, PR
- `odoo mcp debugging` — dùng MCP odoo để điều tra
- `user working preferences` — cách người dùng muốn được hỗ trợ

## Chọn fact_type

Không tự đặt `fact_type` trong `retain` — để hindsight tự phân loại. Bank hiện có những cặp `world` /
`observation` gần trùng nhau chính vì cùng một nội dung bị ghi hai lần; cách chặn là **recall trước khi
retain** (bước 3 của skill), không phải can thiệp vào fact_type.
