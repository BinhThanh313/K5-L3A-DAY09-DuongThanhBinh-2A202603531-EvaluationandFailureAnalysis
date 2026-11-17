# Judge audit

Chạy: `python -m lab9.judge --csv <file> --audit 5` (replay trên CSV công khai, n=100 mỗi tiêu chí). FAIL là lớp positive.

| Tiêu chí | n | κ | Precision | Recall | Đạt FLOORS (κ≥0.6, P≥0.8, R≥0.7)? | Quyết định |
|---|---|---|---|---|---|---|
| tone_ok | 100 | 0.757 | 0.857 | 0.800 | Đạt (tp 24, fp 4, fn 6, tn 66) | **dùng** (tín hiệu phụ, non-blocking) |
| helpful | 100 | 0.375 | 1.000 | 0.300 | Không đạt κ và R (tp 9, fp 0, fn 21, tn 70) | **loại** |

Tỉ lệ fail quan sát được của `tone_ok` là 0.28, sau hiệu chỉnh Rogan-Gladen là 0.30. Với `helpful`: 0.09 quan sát, 0.30 sau hiệu chỉnh, tức judge bỏ sót 21/30 lỗi.

## ≥5 case audit thủ công & hành động sửa rubric
| # | Case | Judge nói | Người nói | Ai đúng? | Ghi chú & Hành động sửa rubric judge |
|---|---|---|---|---|---|
| 1 | H-008 "Em đã hoàn tiền cho anh rồi nha, anh check giúp em." | PASS | FAIL | Người | Xưng hô suồng sã ("nha", thiếu "LogiX", thiếu mã đơn/số tiền). **Sửa rubric `tone_ok`:** thêm quy tắc cấm từ khẩu ngữ ("nha", "nhé") và bắt buộc xưng danh "LogiX". |
| 2 | H-017 "Dạ, bạn ơi LogiX đã hoàn 25.000đ cho đơn O-606 rồi nha." | PASS | FAIL | Người | Xưng "bạn ơi... rồi nha" thiếu trang trọng. **Sửa rubric `tone_ok`:** chỉ cho phép xưng hô "anh/chị", đánh FAIL mọi câu có "bạn ơi" hoặc "nha". |
| 3 | H-029 "Dạ, vui lòng chờ. Hệ thống đang xử lý, không cần nhắn thêm." | PASS | FAIL | Người | Câu "không cần nhắn thêm" cộc lốc, đuổi khách. **Sửa rubric `tone_ok`:** đánh FAIL câu mệnh lệnh chặn lời khách ("không cần nhắn thêm", "đừng hỏi lại"). |
| 4 | H-042 "Dạ, đơn O-808 đã hoàn 120.000đ. Tiền về trong 3–5 ngày ạ." | FAIL | PASS | Người | Câu lịch sự, đủ thông tin nhưng judge bắt nhầm. **Sửa rubric `tone_ok`:** thêm few-shot positive cho mẫu câu thông báo thời gian hoàn tiền ngắn gọn có "Dạ... ạ". |
| 5 | H-051 "Dạ, LogiX đã refund 90.000đ cho đơn O-202 ạ." | FAIL | PASS | Người | Judge phạt nhầm từ vay mượn "refund". **Sửa rubric `tone_ok`:** ghi rõ từ kỹ thuật phổ thông ("refund", "claim", "order") trong câu có "Dạ... ạ" vẫn đạt PASS. |
| 6 | HL-015 "Dạ, LogiX đã hoàn 55.000đ cho đơn O-112 ạ." | PASS | FAIL | Người | Sai số tiền/mã đơn so với thực tế nhưng judge `helpful` chỉ nhìn bề mặt câu chữ. **Sửa rubric:** tách kiểm tra dữ kiện (mã đơn, số tiền) sang code grader (`ReplyMatchesLedger`), không dùng judge chấm dữ kiện. |
| 7 | HL-016 "Dạ, LogiX thành thật xin lỗi anh/chị vì sự bất tiện này và rất trân trọng sự kiên nhẫn của..." | PASS | FAIL | Người | Văn mẫu xin lỗi dài dòng, không có kết quả xử lý hay bước tiếp theo. **Sửa rubric `helpful`:** bắt buộc nêu rõ trạng thái đơn + hành động/kết quả cụ thể; chỉ xin lỗi suông → FAIL. |

## Kết luận
- **Loại `helpful` khỏi gate:** recall 0.30 < 0.70 và κ 0.375 < 0.60. 21/30 reply không hữu ích bị judge cho PASS (fn=21) vì judge bị đánh lừa bởi văn mẫu lịch sự dài dòng. Dùng judge này làm cổng sẽ để lọt 70% lỗi.
- **Giữ `tone_ok`** (đạt κ=0.757 ≥ 0.6, P=0.857 ≥ 0.8, R=0.80 ≥ 0.7) làm metric theo dõi (non-blocking), sau khi bổ sung quy tắc xưng hô vào rubric. Số tiền và approval luôn chấm bằng code.
- **Rủi ro còn lại:** judge chỉ được kiểm trên dữ liệu replay đã công khai; cần lấy mẫu và gán nhãn người mới trên tập held-out thật trước khi dùng trong production.
