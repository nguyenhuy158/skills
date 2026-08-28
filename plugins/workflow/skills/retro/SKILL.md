---
name: retro
description: Chắt lọc bài học từ phiên làm việc vừa rồi và ghi vào hindsight, có dedupe để không tạo bản ghi trùng. Dùng skill này bất cứ khi nào người dùng nói "rút kinh nghiệm", "nãy giờ có gì hay", "học được gì không", "lưu vào hindsight đi", "retro", hoặc khi vừa khép lại một phiên debug dài, một PR được merge, một sự cố production được xử lý xong — kể cả khi họ không gọi tên skill. Không dùng khi người dùng chỉ muốn ghi một ghi chú đơn lẻ, muốn đọc lại memory cũ, hay muốn tóm tắt cuộc trò chuyện.
---

# Retro

Chắt bài học từ phiên hiện tại rồi ghi vào hindsight.

Claude vốn đã gọi được `retain`. Cái khó không nằm ở đó — nó nằm ở chỗ **ghi cái gì**, **có trùng
với cái đã ghi không**, và **viết thế nào để lần recall sau hành động được ngay**. Ba việc đó là
toàn bộ nội dung của skill này. Nếu bỏ qua bước dedupe, bank sẽ phình lên bằng các bản ghi gần
giống nhau và recall trả về nhiễu — đó chính là thứ skill này sinh ra để chặn.

Mặc định: **ghi thẳng, rồi báo cáo**. Người dùng vẫn xóa được sau, nên đừng chặn họ lại để xin phép.
Ngoại lệ duy nhất: bài học nào chạm vào thông tin nhạy cảm (credential, dữ liệu cá nhân của người
thứ ba) thì hỏi trước.

## Bước 1 — Quét phiên theo 5 tín hiệu

Đừng đọc lại toàn bộ transcript để "tóm tắt". Tóm tắt và chắt bài học là hai việc khác nhau: tóm tắt
tái hiện những gì đã xảy ra, còn ở đây ta chỉ săn những khoảnh khắc sinh ra thông tin mà lần sau
**không tự suy ra được**. Chúng gần như luôn rơi vào năm loại:

1. **Người dùng sửa lưng** — họ nói bạn làm sai, hiểu nhầm, hoặc đưa ra bằng chứng bác kết luận của bạn.
2. **Người dùng nhắc lại** — một yêu cầu họ đã nói rồi mà bạn vẫn làm khác.
3. **Lỗi tốn hơn một lần thử** — nếu phải thử nhiều cách mới qua, lần sau cũng sẽ tốn ngần ấy nếu không ghi.
4. **Convention · lệnh · đường dẫn không hiển nhiên** — thứ chỉ biết được bằng cách mò trong repo/hạ tầng này.
5. **Công cụ trả kết quả gây hiểu nhầm** — rỗng thay vì lỗi, im lặng thay vì cảnh báo, thành công giả.

Loại 5 đáng giá nhất và hay bị bỏ sót nhất, vì lúc gặp nó bạn không biết mình đang bị lừa. Cứ thấy
mình từng kết luận sai rồi phải quay lại sửa, hãy hỏi: có phải một công cụ đã nói dối mình không?

Liệt kê ứng viên ra trước, chưa lọc.

## Bước 2 — Lọc bằng ba câu hỏi

Mỗi ứng viên phải trả lời **có** cho cả ba, thiếu một là bỏ:

- **Dùng lại được ở phiên khác không?** — nếu chỉ đúng cho đúng bản ghi/đúng ngày hôm nay thì không.
- **Lần sau có tự suy ra được không?** — nếu Claude vốn đã biết (kiến thức phổ quát về ngôn ngữ,
  framework, công cụ chuẩn) thì ghi vào chỉ làm loãng bank.
- **Có phải dữ liệu tức thời không?** — id bản ghi, số tiền, timestamp, hash container, tên chi nhánh
  tạm. Những thứ này mai đã sai, mà recall ra thì gây hiểu nhầm nghiêm trọng hơn là không có.

Ranh giới hay gây phân vân là giữa "sự việc" và "quy luật". Sự việc *"hôm nay sync fail vì khách X
thiếu AM"* thì bỏ; quy luật rút ra từ nó — *"batch create + api.constrains: một record hỏng abort cả
lô"* — thì giữ. Khi thấy mình đang định ghi một câu chuyện, hãy hỏi câu chuyện đó dạy điều gì, rồi
ghi điều đó.

Chi tiết tiêu chí và ví dụ good/bad có thật: đọc `references/filters.md` khi phân vân một ứng viên
cụ thể.

## Bước 3 — Recall trước khi retain

Với **từng** ứng viên còn lại, gọi `mcp__hindsight__recall` bằng chính từ khóa của nó trước.

- Không có gì liên quan → ghi mới.
- Đã có bản ghi cùng chủ đề nhưng bài học của bạn bổ sung thêm → dùng `update_mode` để gộp vào bản
  ghi cũ, đừng tạo bản mới. Nêu rõ `document_id` khi có.
- Đã có và không thêm được gì → **bỏ**, và báo trong bảng cuối là "đã có sẵn".

Bước này tốn thêm vài lượt gọi nhưng là lý do skill tồn tại. Bank hiện tại đã có những cặp bản ghi
gần như y hệt nhau vì bước này bị bỏ qua.

## Bước 4 — Viết theo một khuôn duy nhất

```
<quy tắc mệnh lệnh, một câu> | <triệu chứng khi vi phạm> | <cách kiểm chứng>
```

Ba phần, mỗi phần có lý do tồn tại:

- **Quy tắc mệnh lệnh** để đọc xong là làm được, không phải diễn giải lại.
- **Triệu chứng** để lần sau gặp đúng hiện tượng đó là recall khớp — người ta tìm memory bằng triệu
  chứng chứ hiếm khi bằng tên giải pháp.
- **Cách kiểm chứng** để bài học hành động được, không dừng ở mức "biết vậy".

Ví dụ thật:

```
Xác nhận tên field bằng fields_get trước khi kết luận truy vấn MCP odoo là rỗng
  | search_records trả count 0 không kèm lỗi khi domain tham chiếu field sai tên
  | đối chiếu execute_method + search_count trên cùng model
```

Gộp nhiều bài học liên quan chặt vào **một** bản ghi đánh số thay vì rải ra nhiều bản ghi vụn — recall
trả về nguyên cụm thì dễ dùng hơn là bảy mảnh rời.

Tag và `context` lấy từ bộ từ vựng cố định trong `references/taxonomy.md`. Đặt tag tùy hứng mỗi lần
một kiểu sẽ làm recall theo tag vô dụng.

Viết bằng ngôn ngữ người dùng đang dùng trong phiên.

## Bước 5 — Báo cáo bảng giữ / gộp / bỏ

Sau khi ghi xong, in một bảng ngắn:

| Bài học | Xử lý | Lý do |
|---|---|---|
| … | ghi mới | — |
| … | gộp vào bản ghi cũ | trùng chủ đề với memory về X |
| … | bỏ | dữ liệu tức thời |

Có phần "bỏ" thì người dùng mới thấy bạn đã cân nhắc chứ không phải sót, và họ có cơ hội nói "cái đó
nhớ giùm đi" hoặc "cái kia đừng nhớ".

Nếu không có ứng viên nào qua bộ lọc, nói thẳng: phiên này không có gì đáng ghi. Đó là kết quả hợp lệ
và tốt hơn nhiều so với việc nặn ra vài bản ghi vô thưởng vô phạt cho có.
