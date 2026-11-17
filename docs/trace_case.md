# Trace case: từ trace tới quyết định sai đầu tiên

Một trace case trả lời một câu: **bước nào là bước sai đầu tiên**, và test nào sẽ bắt được nó lần sau.

```bash
cd src
python -m lab9.trace_case --shape seeded_regression --claim C-002 --seed 11
python -m lab9.trace_case --shape fixed --claim C-002 --seed 11   # đối chứng
```

## Case của nhóm

| Trường | Nội dung |
|---|---|
| Trial | `seeded_regression C-002@11`, run ID `E-seeded_regression-20261117-9f2e` (`reports/eval_seeded_regression.json`) |
| Triệu chứng | `pass_rate`, `refund_amount_correct`, `reply_matches_ledger` fail. Label: denied, ledger 0đ. Thực tế: reply "LogiX đã hoàn 20.000đ", ledger ghi 20.000đ, status `resolved` |
| Bước sai đầu tiên | Event 3 `model_override {"delay_days": 5}`: agent ghi đè số ngày trễ của DB (2 ngày) bằng số trong ticket (5 ngày) |
| Vì sao là bước *đầu tiên* | Event 1 (handoff) đúng, event 2 (investigator) trả `delay_days` từ DB là 2 và `visible: true`. Từ event 3 trở đi mọi số đều dựa trên 5 ngày: event 4 `quote 20000` (SHIP-LATE-03), event 6 reply 20.000đ |
| Failure mode | FM-03 `ticket_trust` (kéo theo FM-02 vì claim bị denied vẫn có refund) |
| Đối chứng | Shape `fixed` cùng claim@seed: không có event `model_override`; event 3 `quote 0, no_entitlement`; reply "chưa đủ điều kiện"; ledger 0đ |
| Regression test | `tests/test_lab9_trace_case.py`: `test_ticket_trust_refunds_a_denied_claim` (xác nhận lỗi trên variant lỗi) và `test_fixed_denies_c002_and_ledger_stays_empty` (pass trên `fixed`). Ngoài ra grader `DbFactKept` (đếm `model_override`) và `RefundAmountCorrect` fail trên variant lỗi, pass trên `fixed` |
| Chưa chắc chắn | Trace không cho biết vì sao agent chọn tin ticket (chỉ thấy hành vi). Mới kiểm tra 1 claim@seed; `quiet_override` (tin ticket nhưng không ghi event) sẽ không bị `DbFactKept` bắt, chỉ bị grader đọc ledger bắt |

## Quy tắc

- Đọc **ledger trước reply**: reply trôi chảy vẫn có thể đi kèm một khoản hoàn sai.
- "Bước sai đầu tiên" phải dẫn số event cụ thể, không phải "agent bị nhầm".
- Case chỉ hoàn thành khi có regression test chạy được.
