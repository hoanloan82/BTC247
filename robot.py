import os
import requests
import logging
from datetime import datetime
from google import genai

# 🔑 Cấu hình Khóa bảo mật lấy từ GitHub Secrets
TELEGRAM_TOKEN   = os.environ.get("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
GEMINI_API_KEY   = os.environ.get("GEMINI_API_KEY", "")

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)


# --- 📈 1. HÀM LẤY GIÁ THẬT 100% TỪ COINGECKO (KHÔNG BỊ CHẶN) ---
def lay_gia_chuan_thi_truong():
    try:
        url = "https://api.coingecko.com/api/v3/simple/price?ids=bitcoin,ethereum&vs_currencies=usd&include_24hr_change=true"
        response = requests.get(url, timeout=15)
        data = response.json()
        
        btc_price = float(data['bitcoin']['usd'])
        btc_change = float(data['bitcoin']['usd_24h_change'])
        
        eth_price = float(data['ethereum']['usd'])
        eth_change = float(data['ethereum']['usd_24h_change'])

        return {
            "btc": {"price": btc_price, "change": btc_change},
            "eth": {"price": eth_price, "change": eth_change}
        }
    except Exception as e:
        log.error(f"Lỗi lấy giá từ CoinGecko: {e}")
        return None


# --- 🖼️ 2. HÀM TẢI ẢNH BIỂU ĐỒ NẾN (CHART) TỰ ĐỘNG ---
def tai_anh_bieu_do(symbol="BTCUSDT"):
    try:
        # Sử dụng API của công cụ TradingView vẽ biểu đồ nến miễn phí
        clean_symbol = symbol.replace("USDT", "")
        url_chart = f"https://charts2-node.finviz.com/chart.ashx?cs=h&t={clean_symbol}&tf=d&s=l"
        
        file_name = f"bieu_do_{symbol}.png"
        response = requests.get(url_chart, stream=True, timeout=20)
        
        if response.status_code == 200:
            with open(file_name, 'wb') as f:
                for chunk in response.iter_content(1024):
                    f.write(chunk)
            log.info(f"✅ Đã tải ảnh biểu đồ cho {symbol}")
            return file_name
    except Exception as e:
        log.error(f"Lỗi tải biểu đồ cho {symbol}: {e}")
    return None


# --- 🤖 3. HÀM NHỜ GEMINI AI PHÂN TÍCH ---
def danh_gia_thi_truong_bang_ai(data_crypto):
    if not GEMINI_API_KEY:
        return "⚠️ Chưa cấu hình GEMINI_API_KEY trên GitHub Secrets!"

    try:
        client = genai.Client(api_key=GEMINI_API_KEY)
        
        prompt = f"""
        Bạn là chuyên gia phân tích kỹ thuật Crypto. Hãy đọc số liệu giá thật hiện tại (Tháng 3/2026):

        📊 Dữ liệu BTC/USDT:
        - Giá hiện tại: ${data_crypto['btc']['price']:,}
        - Biến động 24h qua: {data_crypto['btc']['change']:.2f}%

        📊 Dữ liệu ETH/USDT:
        - Giá hiện tại: ${data_crypto['eth']['price']:,}
        - Biến động 24h qua: {data_crypto['eth']['change']:.2f}%

        Hãy đánh giá ngắn gọn cho nhà đầu tư (Anh Hoàn):
        1. Xu hướng ngắn hạn?
        2. Tình hình này có ưu thế cho phe LONG, phe SHORT hay nên ĐỨNG NGOÀI?
        
        Trình bày súc tích, chia đề mục rõ ràng bằng tiếng Việt.
        """

        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt
        )
        return response.text
    except Exception as e:
        log.error(f"Lỗi phân tích AI: {e}")
        return f"⚠️ Không phân tích được số liệu do lỗi AI: {e}"


# --- 📱 4. HÀM GỬI ẢNH KÈM TIN NHẮN LÊN TELEGRAM ---
def gui_tin_kem_anh_telegram(photo_path, caption_text):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID or not photo_path: return False
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto"
        with open(photo_path, 'rb') as photo:
            files = {'photo': photo}
            truncated_caption = caption_text[:1020]
            data = {'chat_id': TELEGRAM_CHAT_ID, 'caption': truncated_caption, 'parse_mode': 'HTML'}
            requests.post(url, files=files, data=data, timeout=30)
        return True
    except Exception as e:
        log.error(f"Lỗi gửi Telegram: {e}")
        return False


# --- 🏁 HÀM CHẠY CHÍNH ---
def chay_robot_crypto():
    log.info("--- BẮT ĐẦU CHẠY ROBOT QUÂN SƯ + ẢNH BIỂU ĐỒ ---")
    
    du_lieu_gia = lay_gia_chuan_thi_truong()

    if du_lieu_gia:
        # Phân tích của AI
        nhan_dinh_ai = danh_gia_thi_truong_bang_ai(du_lieu_gia)
        
        # Tải ảnh biểu đồ nến BTC
        anh_btc = tai_anh_bieu_do("BTCUSDT")

        message = (
            f"💰 <b>BẢN TIN QUÂN SƯ CRYPTO CHUẨN (ANH HOÀN)</b>\n"
            f"📅 <i>Cập nhật: {datetime.now().strftime('%H:%M %d/%m/%Y')}</i>\n"
            f"─────────────────\n\n"
            f"📌 <b>Giá BTC:</b> ${du_lieu_gia['btc']['price']:,} ({du_lieu_gia['btc']['change']:.2f}%)\n"
            f"📌 <b>Giá ETH:</b> ${du_lieu_gia['eth']['price']:,} ({du_lieu_gia['eth']['change']:.2f}%)\n\n"
            f"{nhan_dinh_ai}"
        )
        
        if anh_btc and os.path.exists(anh_btc):
            gui_tin_kem_anh_telegram(anh_btc, message)
            os.remove(anh_btc) # Xóa ảnh tạm sau khi gửi
        else:
            # Nếu lỗi tải ảnh thì gửi tin nhắn văn bản bình thường
            url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
            requests.post(url, data={"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "HTML"})
    else:
        log.error("Không lấy được dữ liệu thị trường.")

if __name__ == "__main__":
    chay_robot_crypto()
