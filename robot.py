import time
import os
import logging
import requests
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

# ============================================================
# CẤU HÌNH — Đọc từ GitHub Secrets
# ============================================================
URL_LOGIN     = "https://hscvkhcn.dienbien.gov.vn/names.nsf?Login"
URL_DANH_SACH = "https://hscvkhcn.dienbien.gov.vn/qlvb/vbden.nsf/default?openform&frm=Private_ChoXL?openForm"

USER_NAME        = os.environ.get("SKHCN_USER", "")
PASS_WORD        = os.environ.get("SKHCN_PASS", "")
TELEGRAM_TOKEN   = os.environ.get("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)


def gui_anh_telegram(photo_path: str, caption: str):
    """Hàm gửi ảnh chụp màn hình qua Telegram"""
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID: return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto"
    try:
        with open(photo_path, 'rb') as photo:
            resp = requests.post(url, data={"chat_id": TELEGRAM_CHAT_ID, "caption": caption}, files={"photo": photo}, timeout=30)
        if resp.status_code == 200: log.info("✅ Đã gửi ảnh chụp trang web thành công!")
    except Exception as e:
        log.error(f"❌ Lỗi gửi ảnh Telegram: {e}")


def chay_robot():
    log.info("--- BẮT ĐẦU CHỤP ẢNH MÀN HÌNH GIẢI MÃ LỖI ---")
    driver = None

    try:
        options = Options()
        options.add_argument("--headless")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--window-size=1920,1080") # Đưa về màn hình máy tính chuẩn
        options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
        
        driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
        wait = WebDriverWait(driver, 30)

        # 1. Đăng nhập
        driver.get(URL_LOGIN)
        wait.until(EC.presence_of_element_located((By.NAME, "Username")))
        driver.find_element(By.NAME, "Username").send_keys(USER_NAME)
        driver.find_element(By.NAME, "Password").send_keys(PASS_WORD)
        try:
            driver.find_element(By.XPATH, "//input[@type='submit']").click()
        except Exception:
            driver.execute_script("document.forms[0].submit()")
        time.sleep(15)

        # 2. Vào danh sách văn bản
        driver.get(URL_DANH_SACH)
        time.sleep(35) # Chờ load hẳn bảng ra

        driver.switch_to.default_content()
        wait.until(EC.frame_to_be_available_and_switch_to_it((By.NAME, "Main")))
        
        # 📸 CHỤP ẢNH MÀN HÌNH HIỆN TẠI
        file_anh = "man_hinh_so.png"
        driver.save_screenshot(file_anh)
        log.info("📸 Đã chụp ảnh màn hình lưu thành công!")

        # ✈️ Gửi ảnh này qua Telegram cho anh Hoàn
        gui_anh_telegram(file_anh, "🔍 Đây là giao diện trang web mà GitHub nhìn thấy!")

    except Exception as e:
        log.error(f"❌ Lỗi chụp ảnh: {e}")
    finally:
        if driver:
            driver.quit()

if __name__ == "__main__":
    chay_robot()
