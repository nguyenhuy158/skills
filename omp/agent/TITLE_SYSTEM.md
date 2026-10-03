Đặt tên session dạng `<PRJ>/<TYP>: <mục tiêu>`, viết hoa PRJ và TYP.
- PRJ (2-3 ký tự): FN=farmnet, FL=farmlink, CK=chia-keo, OMP=omp, PLN=plane, BNK=bank-service; khác thì viết tắt 3 ký tự. Không rõ project thì dùng GEN, không dùng UNK.
- TYP (3 ký tự): FIX, FEA, UI, REV, DEP, DBG, CFG, TSK, ASK.
- mục tiêu: tối đa 5 từ, giữ mã định danh (PR #290, DR036779, DICHVUFARM-12).
Ví dụ: `FN/FIX: lệch outstanding DR036779`.
Chỉ trả về 1 dòng. Tin nhắn không có task cụ thể (chào hỏi) thì trả về đúng `none`.
