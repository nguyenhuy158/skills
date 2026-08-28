# Bộ lọc — chi tiết và ví dụ

Đọc file này khi phân vân một ứng viên cụ thể có đáng ghi không.

## Ba câu hỏi, diễn giải kỹ

### 1. Dùng lại được ở phiên khác không?

Hỏi ngược: *nếu ba tháng nữa gặp lại tình huống tương tự, câu này có tiết kiệm được thời gian không?*

- Có → giữ.
- Chỉ đúng cho đúng bản ghi này, đúng ngày này → bỏ.

Cái bẫy: một sự việc rất đáng nhớ (sự cố lớn, tốn cả ngày) không đồng nghĩa nó đáng **ghi**. Cái đáng
ghi là **quy luật** rút ra từ nó, không phải bản thân sự việc.

### 2. Lần sau có tự suy ra được không?

Nếu đó là kiến thức phổ quát về ngôn ngữ, framework, hay công cụ chuẩn thì Claude vốn đã biết. Ghi vào
làm loãng bank và đẩy các bài học thật sự hiếm xuống dưới trong kết quả recall.

Ranh giới: kiến thức phổ quát thì bỏ, nhưng **cách hệ thống cụ thể này lệch khỏi mặc định phổ quát**
thì giữ — đó chính là loại thông tin không suy ra được.

### 3. Có phải dữ liệu tức thời không?

Bỏ: id bản ghi, số tiền, timestamp, hash container, tên nhánh tạm, số PR (trừ khi PR đó là mốc tra cứu
cho một quy tắc), trạng thái hiện tại của một record.

Những thứ này mai đã sai. Một memory sai nguy hiểm hơn một memory thiếu, vì nó được recall ra với vẻ
chắc chắn và không ai kiểm tra lại.

Ngoại lệ: hằng số hạ tầng ổn định (tên host, tên instance, đường dẫn trong container) thì giữ — nhưng
kèm cách tự tra lại, vì chúng vẫn đổi theo thời gian.

## Ví dụ có thật

Rút từ phiên debug planning sync FarmNet, 28/08/2026.

### Giữ — hành vi công cụ gây hiểu nhầm

```
Xác nhận tên field bằng fields_get trước khi kết luận truy vấn MCP odoo là rỗng
  | search_records trả count 0 không kèm lỗi khi domain tham chiếu field sai tên
  | đối chiếu execute_method + search_count trên cùng model
```

Đáng giá vì: tốn nhiều lượt mới phát hiện, sẽ lặp lại, và lúc gặp thì không có dấu hiệu nào báo bạn
đang sai.

### Giữ — bản đồ hệ thống không hiển nhiên

```
Khách hàng FarmLink nằm ở model farmlink_customer.customer với field tax_id_number và uuid,
không phải res.partner (res.partner bên flproduction chỉ có duy nhất company Techcoop)
```

Đáng giá vì: chỉ biết được bằng cách mò, và mò sai thì rơi đúng vào bẫy "count 0 im lặng" ở trên.

### Giữ — pattern lỗi có thể tái diễn ở chỗ khác

```
Batch create(list_of_vals) + api.constrains: một record hỏng làm ValidationError abort toàn bộ
recordset | vòng lặp dựng vals từ dữ liệu ngoài phải continue + gom vào list rồi log warning
tổng hợp | kiểm tra bằng test có một record thiếu field bắt buộc
```

Đáng giá vì: là **quy luật**, không phải sự việc. Áp dụng được cho mọi model khác trong cùng codebase.

### Bỏ — dữ liệu tức thời

```
DR041460 (id 41528) có planning_customer_id = 4144, tạo lúc 2026-08-28 08:11:51
```

Mai đã có thể khác. Recall ra thì gây hiểu nhầm.

### Bỏ — kiến thức phổ quát

```
ValidationError trong Odoo sẽ rollback transaction
```

Claude đã biết. Ghi vào không thêm gì.

### Bỏ — sự việc chưa rút thành quy luật

```
Hôm nay sync fail vì công ty Gia Bảo không có account manager
```

Đúng nhưng vô dụng ở phiên sau. Quy luật đằng sau nó (batch create + constrains) mới là thứ đáng ghi
— xem ví dụ "giữ" thứ ba.

## Khi thật sự không chắc

Nghiêng về **bỏ**. Bank sạch mà thiếu vài bài học thì lần sau vẫn mò ra được; bank đầy nhiễu thì recall
mất tác dụng và không ai dọn.
