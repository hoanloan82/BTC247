import time
import os
import json
import logging
import requests
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

# ============================================================
# 1. CẤU HÌNH — Đọc từ GitHub Secrets
# ============================================================
URL_LOGIN     = "https://hscvkhcn.dienbien.gov.vn/names.nsf?Login"

USER_NAME        = os.environ.get("SKHCN_USER", "")
PASS_WORD        = os.environ.get("SKHCN_PASS", "")
TELEGRAM_TOKEN   = os.environ.get("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

FILE_DA_GUI = "da_gui.json"

# ============================================================
# 2. LOGGING
# ============================================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()]
)
log = logging.getLogger(__name__)


# ============================================================
# 3. QUẢN LÝ TRẠNG THÁI
# ============================================================
def tai_ds_da_gui() -> set:
    try:
        with open(FILE_DA_GUI, "r", encoding="utf-8") as f:
            return set(json.load(f))
    except (FileNotFoundError, json.JSONDecodeError):
        return set()


def luu_ds_da_gui(ds: set):
    with open(FILE_DA_GUI, "w", encoding="utf-8") as f:
        json.dump(list(ds), f, ensure_ascii=False, indent=2)


# ============================================================
# 4. GỬI TELEGRAM
# ============================================================
def gui_telegram(msg: str) -> bool:
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        log.warning("⚠️ Chưa cấu hình Telegram.")
        return False
    try:
        url  = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        resp = requests.post(url, data={
            "chat_id": TELEGRAM_CHAT_ID,
            "text": msg,
            "parse_mode": "HTML"
        }, timeout=15)
        if resp.status_code == 200:
            log.info("✅ Gửi Telegram thành công!")
            return True
        else:
            log.error(f"❌ Telegram lỗi {resp.status_code}: {resp.text}")
            return False
    except requests.RequestException as e:
        log.error(f"❌ Lỗi kết nối Telegram: {e}")
        return False


# ============================================================
# 5. ROBOT CHÍNH
# ============================================================
def chay_robot():
    log.info("--- BẮT ĐẦU QUÉT HỆ THỐNG SỞ KH&CN ---")

    ds_da_gui = tai_ds_da_gui()
    driver    = None

    try:
        log.info("1. Khởi động Chrome...")
        options = Options()
        options.add_argument("--headless")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")
        options.add_argument("--window-size=1920,1080")
        # Giả lập User Agent giống người dùng thật để máy chủ không đá
        options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
        
        driver = webdriver.Chrome(
            service=Service(ChromeDriverManager().install()),
            options=options
        )
        wait = WebDriverWait(driver, 30)

        # 2. ĐĂNG NHẬP
        log.info("2. Đăng nhập hệ thống...")
        driver.get(URL_LOGIN)
        wait.until(EC.presence_of_element_located((By.NAME, "Username")))
        
        driver.find_element(By.NAME, "Username").send_keys(USER_NAME)
        driver.find_element(By.NAME, "Password").send_keys(PASS_WORD)
        
        try:
            driver.find_element(By.XPATH, "//input[@type='submit']").click()
        except Exception:
            driver.execute_script("document.forms[0].submit()")
        time.sleep(10) # Đợi điều hướng về trang chủ sau đăng nhập

        # 3. THAY VÌ DÙNG LINK TRỰC TIẾP, ROBOT TỰ CLICK TỪ TRANG CHỦ
        log.info("3. Tìm kiếm danh sách văn bản...")
        
        # Thử tìm tất cả khung Frame trên trang để bám vào
        driver.switch_to.default_content()
        all_frames = driver.find_elements(By.XPATH, "//frame | //iframe")
        log.info(f"Phát hiện tổng số {len(all_frames)} khung lồng nhau.")

        khung_chinh_thanh_cong = False

        # Quét dạo các frame để tìm xem thằng nào chứa bảng dữ liệu văn bản
        for idx, f in enumerate(all_frames):
            try:
                driver.switch_to.default_content()
                driver.switch_to.frame(f)
                
                rows_check = driver.find_elements(By.TAG_NAME, "tr")
                # Bảng văn bản chờ xử lý thường có nhiều dòng (trên 5 dòng)
                if len(rows_check) > 5:
                    log.info(f"✅ Đã tìm thấy khung chứa dữ liệu (Khung số {idx + 1})")
                    khung_chinh_thanh_cong = True
                    break
            except Exception:
                continue

        # Phương án dự phòng: Nếu duyệt dạo thất bại, gọi đích danh Frame "Main"
        if not khung_chinh_thanh_cong:
            log.warning("Duyệt tự động thất bại. Thử cưỡng bức nhảy vào frame 'Main'...")
            driver.switch_to.default_content()
            try:
                wait.until(EC.frame_to_be_available_and_switch_to_it((By.NAME, "Main")))
                log.info("✅ Vào frame 'Main' bằng phương án dự phòng thành công.")
                khung_chinh_thanh_cong = True
            except Exception:
                log.error("❌ Không thể bám trụ vào bất kỳ Khung làm việc nào!")

        if not khung_chinh_thanh_cong:
            # Chụp một bức ảnh của trang lỗi (nếu cần gỡ lỗi sau này)
            driver.save_screenshot("screenshot_loi_frame.png")
            gui_telegram("⚠️ <b>Robot lỗi:</b> Kẹt ở lớp giao diện chính (Lotus Domino session timeout).")
            return

        # 4. PHÂN TÍCH BẢNG DỮ LIỆU
        log.info("4. Đang phân tích dữ liệu bảng...")
        wait.until(EC.presence_of_element_located((By.TAG_NAME, "tr")))
        rows = driver.find_elements(By.TAG_NAME, "tr")
        ds_vb_moi = []

        log.info(f"Tổng số dòng trích xuất: {len(rows)}")

        for row in rows:
            tds = row.find_elements(By.TAG_NAME, "td")
            if len(tds) >= 7:
                txt = row.text.strip()
                # Chỉ lọc những hàng chứa dấu gạch chéo ký hiệu "/" (Ví dụ: 123/UBND)
                if "/" in txt and "Số ký hiệu" not in txt:
                    so_kh     = tds[4].text.strip()   # Cột 5 (Số hiệu)
                    trich_yeu = tds[6].text.strip()   # Cột 7 (Trích yếu)
                    
                    if so_kh and so_kh not in ds_da_gui:
                        ds_vb_moi.append(f"📍 Số: <b>{so_kh}</b>\n📝 {trich_yeu}")
                        ds_da_gui.add(so_kh)

        # 5. GỬI TELEGRAM
        if ds_vb_moi:
            so_luong  = len(ds_vb_moi)
            thoi_gian = datetime.now().strftime("%H:%M %d/%m/%Y")
            noi_dung  = "\n---\n".join(ds_vb_moi[:5])
            msg = (
                f"🚀 <b>SỞ KH&CN: CÓ {so_luong} VĂN BẢN ĐẾN MỚI</b>\n"
                f"⏰ Cập nhật: {thoi_gian}\n\n"
                f"{noi_dung}"
            )
            log.info(f"🔥 Tìm thấy {so_luong} văn bản mới!")
            gui_telegram(msg)
            luu_ds_da_gui(ds_da_gui)
        else:
            log.info("✅ Không có văn bản mới sau khi phân tích bảng.")

    except Exception as e:
        log.error(f"❌ Lỗi nghiêm trọng: {e}", exc_info=True)
        gui_telegram(f"⚠️ <b>Robot gặp lỗi!</b>\n{str(e)}")
    finally:
        if driver:
            driver.quit()
        log.info("--- KẾT THÚC PHIÊN QUÉT ---\n")


if __name__ == "__main__":
    chay_robot()
