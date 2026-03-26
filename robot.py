import os
import requests
import logging
import pandas as pd
import mplfinance as mpf
from datetime import datetime
from google import genai

# 🔑 Cấu hình Khóa bảo mật lấy từ GitHub Secrets
TELEGRAM_TOKEN   = os.environ.get("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
GEMINI_API_KEY   = os.environ.get("GEMINI_API_KEY", "")

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)


# --- 📈 1. HÀM LẤY GIÁ THUẦN TÚY (DÙNG ĐỂ TEXT BÁO CÁO) ---
def lay_gia_chuan_thi_truong():
    try:
        url = "https://api.coingecko.com/api/v3/simple/price?ids=bitcoin,ethereum&vs_currencies=usd&include_24hr_change=true"
        response = requests.get(url, timeout=15)
        data = response.json()
        return {
            "btc": {"price": float(data['bitcoin']['usd']), "change": float(data['bitcoin']['usd_24h_change'])},
            "eth": {"price": float(data['ethereum']['usd']), "change": float(data['ethereum']['usd_24h_change'])}
        }
    except Exception as e:
        log.error(f"Lỗi CoinGecko: {e}")
        return None


# --- 📊 2. HÀM VẼ BIỂU ĐỒ NẾN 1H (LẤY 24 CÂY NẾN GẦN NHẤT) ---
def ve_bieu_do_nen_1h(symbol="BTCUSDT"):
    try:
        # Lấy dữ liệu nến 1 tiếng (interval=1h) từ Binance công khai
        base_url = "https://api1.binance.com/api/v3"
        url = f"{base_url}/klines?symbol={symbol}&interval=1h&limit=24"
        response = requests.get(url, timeout=20)
        data = response.json()
        
        # Tạo bảng dữ liệu chuẩn (Time, Open, High, Low, Close, Volume)
        df = pd.DataFrame(data, columns=['Time', 'Open', 'High', 'Low', 'Close', 'Volume', '_', '_', '_', '_', '_', '_'])
        df['Time'] = pd.to_datetime(df['Time'], unit='ms')
        df.set_index('Time', inplace=True)
        df = df.astype(float)
        
        file_name = f"chart_{symbol}_1h.png"
        
        # Chỉnh màu nến: Xanh (tăng), Đỏ (giảm)
        mc = mpf.make_marketcolors(up='green', down='red', edge='inherit', wick='inherit', volume='in', inherit=True)
        s  = mpf.make_mpf_style(base_mpf_style='charles', marketcolors=mc, gridstyle='--', y_on_right=False)
        
        # Xuất ảnh nến 1H
        mpf.plot(df, type='candle', style=s, title=f"\n📊 BIEU DO NEN {symbol} (Khung 1H)", savefig=file_name, volume=True)
        
        return file_name
    except Exception as e:
        log.error(f"Lỗi vẽ biểu đồ 1H cho {symbol}: {e}")
        return None


# --- 🤖 3. HÀM NHỜ GEMINI AI PHÂN TÍCH (THÊM YÊU CẦU ĐỌC NẾN 1H) ---
def danh_gia_thi_truong_bang_ai(data_crypto):
    if not GEMINI_API_KEY: return "⚠️ Chưa cấu hình GEMINI_API_KEY!"

    try:
        client = genai.Client(api_key=GEMINI_API_KEY)
        
        prompt = f"""
        Bạn là một trader chuyên nghiệp lướt sóng ngắn hạn (Scalping/Day trading).
        Hãy đọc số liệu giá thực tế hiện tại của BTC và ETH:

        📊 Dữ liệu BTC: ${data_crypto['btc']['price']:,} (Biến động 24h: {data_crypto['btc']['change']:.2f}%)
        📊 Dữ liệu ETH: ${data_crypto['eth']['price']:,} (Biến động 24h: {data_crypto['eth']['change']:.2f}%)

        Dựa trên khung đồ thị 1 giờ (1H), hãy phân tích thật ngắn gọn và thực dụng:
        1. Xu hướng ngắn hạn trong vài tiếng tới (Tăng nhẹ, giảm nhẹ hay đi ngang)?
        2. Dấu hiệu nến hiện tại có ủng hộ cho lệnh LONG hay lệnh SHORT không? (Nêu rõ điều kiện cắt lỗ Stop loss để bảo vệ vốn).
        
        Trình bày bằng tiếng Việt, súc tích, chia gạch đầu dòng rõ ràng.
        """

        response = client.models.generate_content(model='gemini-2.5-flash', contents=prompt)
        return response.text
    except Exception as e:
        return f"⚠️ Lỗi AI phân tích: {e}"


# --- 📱 4. HÀM GỬI ẢNH KÈM CHỮ VỀ TELEGRAM ---
def gui_anh_kem_tin_nhan(photo_path, caption_text):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID: return
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto"
        with open(photo_path, 'rb') as photo:
            # Cắt bớt chữ nếu Gemini viết quá dài (Telegram giới hạn caption < 1024 kí tự)
            truncated_caption = caption_text[:1020] 
            data = {'chat_id': TELEGRAM_CHAT_ID, 'caption': truncated_caption, 'parse_mode': 'HTML'}
            requests.post(url, files={'photo': photo}, data=data, timeout=30)
    except Exception as e:
        log.error(f"Lỗi gửi Telegram: {e}")


# --- 🏁 HÀM CHẠY CHÍNH ---
def chay_robot_crypto():
    log.info("--- BẮT ĐẦU CHẠY ROBOT NẾN 1H ---")
    
    du_lieu_gia = lay_gia_chuan_thi_truong()
    if not du_lieu_gia:
        log.error("Không lấy được dữ liệu thị trường.")
        return

    # 1. Nhờ AI phân tích
    nhan_dinh_ai = danh_gia_thi_truong_bang_ai(du_lieu_gia)
    
    # 2. Vẽ biểu đồ nến 1H cho BTC
    anh_chart = ve_bieu_do_nen_1h("BTCUSDT")

    # Nội dung gửi đi
    message = (
        f"📊 <b>QUÂN SƯ CRYPTO - NẾN 1H (ANH HOÀN)</b>\n"
        f"📅 <i>{datetime.now().strftime('%H:%M %d/%m/%Y')}</i>\n"
        f"─────────────────\n\n"
        f"📌 <b>BTC:</b> ${du_lieu_gia['btc']['price']:,} ({du_lieu_gia['btc']['change']:.2f}%)\n"
        f"📌 <b>ETH:</b> ${du_lieu_gia['eth']['price']:,} ({du_lieu_gia['eth']['change']:.2f}%)\n\n"
        f"{nhan_dinh_ai}"
    )

    # 3. Gửi lên Telegram
    if anh_chart and os.path.exists(anh_chart):
        gui_anh_kem_tin_nhan(anh_chart, message)
        os.remove(anh_chart) # Xóa ảnh tạm
    else:
        # Nếu lỗi vẽ ảnh thì gửi tin nhắn Text tạm thời
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        requests.post(url, data={"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "HTML"})

if __name__ == "__main__":
    chay_robot_crypto()
