import os
import requests
import logging
import pandas as pd
import mplfinance as mpf
import time
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


# --- 🤖 3. HÀM NHỜ GEMINI AI PHÂN TÍCH (XỬ LÝ LỖI CHẠM TRẦN 429) ---
def danh_gia_thi_truong_bang_ai(data_crypto):
    if not GEMINI_API_KEY: return "⚠️ Chưa cấu hình GEMINI_API_KEY!"

    # Thiết lập cơ chế lặp lại 3 lần nếu Google chặn truy cập miễn phí
    for lan_thu in range(3): 
        try:
            client = genai.Client(api_key=GEMINI_API_KEY)
            
            prompt = f"""
            Bạn là một chuyên gia lướt sóng Crypto chuyên nghiệp (Scalper/Day Trading).
            Hãy đọc số liệu giá thực tế hiện tại:

            📊 BTC: ${data_crypto['btc']['price']:,} (Biến động 24h: {data_crypto['btc']['change']:.2f}%)
            📊 ETH: ${data_crypto['eth']['price']:,} (Biến động 24h: {data_crypto['eth']['change']:.2f}%)

            Nhiệm vụ của bạn là đưa ra nhận định kết hợp ĐA KHUNG THỜI GIAN (15P, 1H và 4H):
            1. Xu hướng Vi mô (Khung 15P): Điểm kích hoạt lệnh lướt nhanh ngắn hạn.
            2. Xu hướng Ngắn hạn (Khung 1H): Đỉnh/Đáy hoặc Xu hướng gãy cấu trúc không?
            3. Xu hướng Tổng quan (Khung 4H): Chạm vùng hỗ trợ/kháng cự lớn không?

            👉 Hãy đưa ra 2 Kịch bản chiến lược (LONG hoặc SHORT) rõ ràng cùng điểm cắt lỗ (Stop loss) cụ thể.
            Trình bày bằng tiếng Việt, súc tích, ngắn gọn, chia gạch đầu dòng rõ ràng để dễ đọc trên điện thoại.
            """

            response = client.models.generate_content(model='gemini-2.0-flash', contents=prompt)
            return response.text

        except Exception as e:
            error_str = str(e)
            if "429" in error_str or "RESOURCE_EXHAUSTED" in error_str:
                log.warning(f"⚠️ Chạm giới hạn miễn phí lần {lan_thu + 1}. Đang nghỉ 40s để thử lại...")
                time.sleep(40) # Chờ 40 giây cho Google reset giới hạn rồi lặp lại
                continue
            else:
                return f"⚠️ Lỗi AI phân tích: {e}"
                
    return "⚠️ Không thể phân tích sau 3 lần thử do hết hạn mức API miễn phí (429)."


# --- 📱 4. HÀM GỬI ẢNH KÈM CHỮ VỀ TELEGRAM ---
def gui_anh_kem_tin_nhan(photo_path, caption_text):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID: return
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto"
        with open(photo_path, 'rb') as photo:
            # Giới hạn caption Telegram tránh bị lỗi vượt tải 1024 ký tự
            truncated_caption = caption_text[:1020] 
            data = {'chat_id': TELEGRAM_CHAT_ID, 'caption': truncated_caption, 'parse_mode': 'HTML'}
            requests.post(url, files={'photo': photo}, data=data, timeout=30)
    except Exception as e:
        log.error(f"Lỗi gửi Telegram: {e}")


# --- 🏁 HÀM CHẠY CHÍNH ---
def chay_robot_crypto():
    log.info("--- BẮT ĐẦU CHẠY ROBOT ĐA KHUNG THỜI GIAN ---")
    
    du_lieu_gia = lay_gia_chuan_thi_truong()
    if not du_lieu_gia:
        log.error("Không lấy được dữ liệu thị trường.")
        return

    # 1. Nhờ AI phân tích đa khung thời gian
    nhan_dinh_ai = danh_gia_thi_truong_bang_ai(du_lieu_gia)
    
    # 2. Vẽ biểu đồ nến 1H cho BTC
    anh_chart = ve_bieu_do_nen_1h("BTCUSDT")

    # Nội dung gửi đi được định dạng HTML để hiển thị đẹp trên Telegram
    message = (
        f"📊 <b>QUÂN SƯ CRYPTO - ĐA KHUNG GIỜ (ANH HOÀN)</b>\n"
        f"📅 <i>{datetime.now().strftime('%H:%M %d/%m/%Y')}</i>\n"
        f"─────────────────\n\n"
        f"📌 <b>BTC:</b> ${du_lieu_gia['btc']['price']:,} ({du_lieu_gia['btc']['change']:.2f}%)\n"
        f"📌 <b>ETH:</b> ${du_lieu_gia['eth']['price']:,} ({du_lieu_gia['eth']['change']:.2f}%)\n\n"
        f"{nhan_dinh_ai}"
    )

    # 3. Gửi lên Telegram
    if anh_chart and os.path.exists(anh_chart):
        gui_anh_kem_tin_nhan(anh_chart, message)
        os.remove(anh_chart) # Xóa file rác sau khi gửi thành công
    else:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        requests.post(url, data={"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "HTML"})

if __name__ == "__main__":
    chay_robot_crypto()
