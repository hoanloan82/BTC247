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
URL_DANH_SACH = "https://hscvkhcn.dienbien.gov.vn/qlvb/vbden.nsf/default?openform&frm=Private_ChoXL?openForm"

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
        }, timeout=10)
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
        # 1. Khởi động Chrome Headless
        log.info("1. Khởi động Chrome...")
        options = Options()
        options.add_argument("--headless")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")
        options.add_argument("--window-size=1920,1080")
        
        driver = webdriver.Chrome(
            service=Service(ChromeDriverManager().install()),
            options=options
        )
        wait = WebDriverWait(driver, 20)

        # 2. Đăng nhập
        log.info("2. Đăng nhập hệ thống...")
        driver.get(URL_LOGIN)
        wait.until(EC.presence_of_element_located((By.NAME, "Username")))
        
        driver.find_element(By.NAME, "Username").send_keys(USER_NAME)
        driver.find_element(By.NAME, "Password").send_keys(PASS_WORD)
        
        try:
            driver.find_element(By.XPATH, "//input[@type='submit']").click()
        except Exception:
            driver.execute_script("document.forms[0].submit()")
        time.sleep(5)

        # 3. Truy cập danh sách
        log.info("3. Truy cập danh sách văn bản chờ xử lý...")
        driver.get(URL_DANH_SACH)
        time.sleep(5) # Cho web cơ quan load một chút

        # KỸ THUẬT ÉP BUỘC CHỜ ĐỢI FRAME "MAIN"
        log.info("Đang tìm và nhảy vào Frame 'Main'...")
        khung_chinh_thanh_cong = False

        for thu_lai in range(3):
            try:
                # Chờ tối đa 20 giây cho frame "Main" xuất hiện và nhảy vào đó
                WebDriverWait(driver, 20).until(EC.frame_to_be_available_and_switch_to_it((By.NAME, "Main")))
                log.info(f"✅ Đã vào Frame 'Main' thành công ở lần thử {thu_lai + 1}")
                khung_chinh_thanh_cong = True
                break
            except Exception:
                log.warning(f"Chưa thấy Frame 'Main', thử lại lần {thu_lai + 1}...")
                time.sleep(5)

        if not khung_chinh_thanh_cong:
            log.error("❌ Không thể vào Frame 'Main' sau 3 lần thử. Dừng quét!")
            gui_telegram("⚠️ <b>Robot lỗi:</b> Không load được khung danh sách văn bản (Frame Main).")
            return

        # 4. Phân tích bảng dữ liệu
        log.info("4. Đang phân tích dữ liệu bảng...")
        # Chờ bảng (các hàng TR) hiện ra trong Frame
        wait.until(EC.presence_of_element_located((By.TAG_NAME, "tr")))
        rows = driver.find_elements(By.TAG_NAME, "tr")
        ds_vb_moi = []

        for row in rows:
            tds = row.find_elements(By.TAG_NAME, "td")
            if len(tds) >= 7:
                txt = row.text.strip()
                if "/" in txt and "Số ký hiệu" not in txt:
                    # Lấy dữ liệu cột Số hiệu và Trích yếu
                    so_kh     = tds[4].text.strip()   # Cột 5
                    trich_yeu = tds[6].text.strip()   # Cột 7
                    
                    if so_kh and so_kh not in ds_da_gui:
                        ds_vb_moi.append(f"📍 Số: <b>{so_kh}</b>\n📝 {trich_yeu}")
                        ds_da_gui.add(so_kh)

        # 5. Thông báo Telegram
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
