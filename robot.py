import os
import requests
import logging
from datetime import datetime
from google import genai

# 🔑 Cấu hình các Khóa bảo mật
TELEGRAM_TOKEN   = os.environ.get("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
GEMINI_API_KEY   = os.environ.get("GEMINI_API_KEY", "")

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

# --- 📈 1. HÀM LẤY DỮ LIỆU GIÁ TỪ BINANCE ---
def lay_gia_binance(symbol="BTCUSDT"):
    try:
        # Lấy giá hiện tại
        res_price = requests.get(f"https://api.binance.com/api/v3/ticker/price?symbol={symbol}")
        price_data = res_price.json()
        current_price = float(price_data['price'])

        # Lấy thống kê 24h (Cao nhất, thấp nhất, % thay đổi)
        res_24h = requests.get(f"https://api.binance.com/api/v3/ticker/24hr?symbol={symbol}")
        data_24h = res_24h.json()
        
        return {
            "symbol": symbol,
            "current_price": current_price,
            "high_24h": float(data_24h['highPrice']),
            "low_24h": float(data_24h['lowPrice']),
            "price_change_percent": float(data_24h['priceChangePercent']),
            "volume_24h": float(data_24h['volume'])
        }
    except Exception as e:
        log.error(f"Lỗi lấy dữ liệu Binance cho {symbol}: {e}")
        return None

# --- 🤖 2. HÀM NHỜ GEMINI AI ĐÁNH GIÁ THỊ TRƯỜNG ---
def danh_gia_thi_truong_bang_ai(btc_data, eth_data):
    if not GEMINI_API_KEY:
        return "⚠️ Chưa cấu hình GEMINI_API_KEY để AI đọc số liệu!"

    try:
        client = genai.Client(api_key=GEMINI_API_KEY)
        
        prompt = f"""
        Bạn là một chuyên gia phân tích kỹ thuật thị trường Crypto (Tiền điện tử). 
        Hãy đọc số liệu thống kê hiện tại của BTC và ETH sau đây:

        📊 Dữ liệu BTC/USDT:
        - Giá hiện tại: {btc_data['current_price']}
        - Cao nhất 24h: {btc_data['high_24h']}
        - Thấp nhất 24h: {btc_data['low_24h']}
        - Biến động % 24h: {btc_data['price_change_percent']}%

        📊 Dữ liệu ETH/USDT:
        - Giá hiện tại: {eth_data['current_price']}
        - Cao nhất 24h: {eth_data['high_24h']}
        - Thấp nhất 24h: {eth_data['low_24h']}
        - Biến động % 24h: {eth_data['price_change_percent']}%

        Dựa trên cấu trúc giá hiện tại so với biên độ 24h, hãy đưa ra một đánh giá khách quan cho nhà đầu tư (Anh Hoàn):
        1. Xu hướng ngắn hạn hiện tại đang là gì (Tăng, Giảm hay Đi ngang - Sideway)?
        2. Vùng giá hiện tại đang gần Kháng cự (Đỉnh 24h) hay Hỗ trợ (Đáy 24h) hơn? 
        3. Dựa trên lý thuyết Phân tích kỹ thuật thuần túy, bối cảnh này có lợi thế xác suất nghiêng về phe LONG hay phe SHORT hơn, hoặc nên KIÊN NHẪN ĐỨNG NGOÀI quan sát?
        
        Hãy trình bày ngắn gọn, chia đề mục rõ ràng bằng tiếng Việt. Lưu ý kèm cảnh báo rủi ro về Quản lý vốn (Stop loss).
        """

        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt
        )
        return response.text
    except Exception as e:
        log.error(f"Lỗi phân tích AI: {e}")
        return f"⚠️ Không phân tích được số liệu do lỗi AI: {e}"

# --- 📱 3. HÀM GỬI THÔNG BÁO TELEGRAM ---
def gui_telegram(message):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID: return
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        data = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "HTML"}
        requests.post(url, data=data, timeout=30)
    except Exception as e:
        log.error(f"Lỗi gửi Telegram: {e}")

# --- 🏁 HÀM CHẠY CHÍNH ---
def chay_robot_crypto():
    log.info("--- BẮT ĐẦU CHẠY ROBOT QUÂN SƯ CRYPTO ---")
    
    btc_info = lay_gia_binance("BTCUSDT")
    eth_info = lay_gia_binance("ETHUSDT")

    if btc_info and eth_info:
        nhan_dinh_ai = danh_gia_thi_truong_bang_ai(btc_info, eth_info)
        
        message = (
            f"💰 <b>BẢN TIN QUÂN SƯ CRYPTO CHO ANH HOÀN</b>\n"
            f"📅 <i>Cập nhật: {datetime.now().strftime('%H:%M %d/%m/%Y')}</i>\n"
            f"─────────────────\n\n"
            f"{nhan_dinh_ai}"
        )
        gui_telegram(message)
    else:
        gui_telegram("⚠️ Robot không lấy được dữ liệu giá từ Binance, anh Hoàn kiểm tra lại kết nối mạng nhé!")

if __name__ == "__main__":
    chay_robot_crypto()
