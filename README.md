# 🤖 Crypto Signal Bot — BTC & ETH Đa Khung

Bot tự động phân tích BTC/ETH theo khung 15P/1H/4H, chỉ gửi tín hiệu khi có điều kiện đẹp.

---

## 📁 Cấu trúc file

```
├── main.py                          # Script chính
├── requirements.txt                 # Thư viện Python
├── signal_log.json                  # Log anti-spam (tự tạo khi chạy)
└── .github/
    └── workflows/
        └── crypto_bot.yml           # GitHub Actions chạy mỗi 15 phút
```

---

## ⚙️ Cài đặt GitHub Secrets

Vào **Settings → Secrets and variables → Actions → New repository secret**:

| Tên Secret        | Giá trị                              |
|-------------------|--------------------------------------|
| `TELEGRAM_TOKEN`  | Token bot Telegram của bạn           |
| `TELEGRAM_CHAT_ID`| Chat ID nhận thông báo               |
| `GEMINI_API_KEY`  | API key từ Google AI Studio          |

### Lấy Telegram Token & Chat ID:
1. Nhắn `/newbot` cho [@BotFather](https://t.me/BotFather) → lấy Token
2. Nhắn `/start` cho bot của bạn, rồi truy cập:
   `https://api.telegram.org/bot<TOKEN>/getUpdates` → lấy `chat.id`

### Lấy Gemini API Key:
- Vào [Google AI Studio](https://aistudio.google.com/) → Get API Key (miễn phí)

---

## 🔍 Điều kiện kích hoạt phân tích

Bot **CHỈ phân tích và gửi** khi có ít nhất **2 trong các điều kiện** sau:

| Điều kiện | Ngưỡng |
|-----------|--------|
| ⚡ Biến động giá mạnh | > 1.5% trong 1 nến 15P |
| 📦 Volume spike | > 1.8x trung bình 20 nến |
| 🔵/🔴 RSI cực trị | < 30 hoặc > 70 |
| 🕯️ Nến đẹp | Engulfing, Pin Bar, Hammer, Shooting Star, Marubozu |
| 📈 MACD cắt | Histogram đổi chiều |

> Điều chỉnh ngưỡng ở đầu file `main.py` theo ý muốn.

---

## 📊 Nội dung tin nhắn Telegram

Mỗi tín hiệu bao gồm:
- **3 ảnh chart** (15P / 1H / 4H) với nến Nhật + EMA9 + SMA20 + BB + RSI + MACD + Volume
- **Score tín hiệu** 0–100
- **Lý do kích hoạt** cụ thể
- **Phân tích AI Gemini Vision** (nhìn vào ảnh chart thật):
  - Nhận định đa khung
  - Kịch bản LONG / SHORT với Entry, SL, TP1, TP2, R:R
  - Khuyến nghị cuối

---

## 🛡️ Tính năng chống spam

- Bot lưu thời điểm gửi tín hiệu cuối vào `signal_log.json`
- **Không gửi lại trong 30 phút** kể từ lần trước cho cùng một coin

---

## ⚠️ Lưu ý quan trọng

> Bot này chỉ là **công cụ hỗ trợ phân tích**, không phải lời khuyên tài chính.
> Luôn tự kiểm tra và quản lý rủi ro trước khi vào lệnh.
