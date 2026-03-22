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
        log.info("1. Khởi động Chrome Headless...")
        options = Options()
        options.add_argument("--headless")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")
        options.add_argument("--window-size=1920,1080")
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
        
        log.info("Đang chờ 15 giây để đăng nhập hoàn tất...")
        time.sleep(15)

        # 3. TRUY CẬP DANH SÁCH
        log.info("3. Truy cập danh sách văn bản...")
        driver.get(URL_DANH_SACH)
        
        log.info("Đang ngủ đông 30 giây để trang web tải hết các Khung (Frame)...")
        time.sleep(30) # <<< Ép buộc dừng 30 giây để máy chủ Sở kịp tải

        driver.switch_to.default_content()

        # Thử nhảy vào Frame 'Main'
        khung_chinh_thanh_cong = False
        try:
            wait.until(EC.frame_to_be_available_and_switch_to_it((By.NAME, "Main")))
            log.info("✅ Đã nhảy vào Frame 'Main' thành công!")
            khung_chinh_thanh_cong = True
        except Exception:
            log.warning("Chưa bám được vào Frame 'Main', thử quét dạo tìm Iframe...")

        # Dự phòng: Tự động lùng sục tất cả các Iframe nếu bám trực tiếp thất bại
        if not khung_chinh_thanh_cong:
            frames = driver.find_elements(By.XPATH, "//frame | //iframe")
            log.info(f"Dò tìm thấy {len(frames)} khung lồng ghép trên trang.")
            
            for i, f in enumerate(frames):
                try:
                    driver.switch_to.default_content()
                    driver.switch_to.frame(f)
                    
                    rows_check = driver.find_elements(By.TAG_NAME, "tr")
                    if len(rows_check) > 5:
                        log.info(f"✅ Phát hiện khung thứ {i+1} có chứa dữ liệu văn bản!")
                        khung_chinh_thanh_cong = True
                        break
                except Exception:
                    continue

        if not khung_chinh_thanh_cong:
            log.error("❌ Không thể bám trụ vào bất kỳ Khung làm việc nào. Hủy phiên quét!")
            gui_telegram("⚠️ <b>Robot lỗi:</b> Kẹt ở lớp giao diện chính (Không tìm thấy Frame bảng).")
            return

        # 4. PHÂN TÍCH BẢNG DỮ LIỆU
        log.info("4. Đang phân tích dữ liệu bảng...")
        wait.until(EC.presence_of_element_located((By.TAG_NAME, "tr")))
        rows = driver.find_elements(By.TAG_NAME, "tr")
        ds_vb_moi = []

        log.info(f"Trích xuất thành công {len(rows)} hàng thô.")

        for row in rows:
            tds = row.find_elements(By.TAG_NAME, "td")
            if len(tds) >= 7:
                txt = row.text.strip()
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
                f"🚀 <b>SỞ KH&CN: CÓ {so_luong} VĂN BẢN ĐẾM MỚI</b>\n"
                f"⏰ Cập nhật: {thoi_gian}\n\n"
                f"{noi_dung}"
            )
            log.info(f"🔥 Tìm thấy {so_luong} văn bản mới!")
            gui_telegram(msg)
            luu_ds_da_gui(ds_da_gui)
        else:
            log.info("✅ Không có văn bản mới sau khi bóc tách.")

    except Exception as e:
        log.error(f"❌ Lỗi nghiêm trọng: {e}", exc_info=True)
        gui_telegram(f"⚠️ <b>Robot gặp lỗi!</b>\n{str(e)}")
    finally:
        if driver:
            driver.quit()
        log.info("--- KẾT THÚC PHIÊN QUÉT ---\n")


if __name__ == "__main__":
    chay_robot()
