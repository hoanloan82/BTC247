import time
import os
import logging
import requests
import re
from datetime import datetime
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


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()]
)
log = logging.getLogger(__name__)


def gui_telegram(msg: str) -> bool:
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        return False
    try:
        url  = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        resp = requests.post(url, data={
            "chat_id": TELEGRAM_CHAT_ID,
            "text": msg,
            "parse_mode": "HTML"
        }, timeout=15)
        return resp.status_code == 200
    except Exception:
        return False

def la_so_hieu_chuan(text: str) -> bool:
    if not text: return False
    if re.match(r'^\d{1,2}/\d{1,2}/\d{4}$', text): return False
    if "/" in text and len(text) >= 4: return True
    return False


def chay_robot():
    log.info("--- BẮT ĐẦU QUÉT HỆ THỐNG SỞ KH&CN (CHẾ ĐỘ TEST) ---")
    driver = None

    try:
        options = Options()
        options.add_argument("--headless")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")
        options.add_argument("--window-size=1920,1080")
        options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
        
        driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
        wait = WebDriverWait(driver, 30)

        driver.get(URL_LOGIN)
        wait.until(EC.presence_of_element_located((By.NAME, "Username")))
        
        driver.find_element(By.NAME, "Username").send_keys(USER_NAME)
        driver.find_element(By.NAME, "Password").send_keys(PASS_WORD)
        
        try:
            driver.find_element(By.XPATH, "//input[@type='submit']").click()
        except Exception:
            driver.execute_script("document.forms[0].submit()")
        time.sleep(15)

        driver.get(URL_DANH_SACH)
        time.sleep(30)

        driver.switch_to.default_content()
        wait.until(EC.frame_to_be_available_and_switch_to_it((By.NAME, "Main")))

        wait.until(EC.presence_of_element_located((By.TAG_NAME, "tr")))
        rows = driver.find_elements(By.TAG_NAME, "tr")
        ds_vb_moi = []

        for row in rows:
            tds = row.find_elements(By.TAG_NAME, "td")
            if len(tds) < 5: continue

            so_kh     = ""
            ngay_den   = ""
            trich_yeu = ""

            for td in tds:
                txt = td.text.strip()
                if not txt: continue

                if la_so_hieu_chuan(txt) and not so_kh:
                    so_kh = txt
                    continue

                if re.match(r'^\d{1,2}/\d{1,2}/\d{4}$', txt) and not ngay_den:
                    ngay_den = txt
                    continue

                if len(txt) > len(trich_yeu) and "số ký hiệu" not in txt.lower():
                    if len(txt) > 12 and not la_so_hieu_chuan(txt) and not re.match(r'^\d{1,2}/\d{1,2}/\d{4}$', txt):
                        trich_yeu = txt

            if so_kh: # Bỏ qua biến kiểm tra trùng lặp để ép gửi test!
                if not trich_yeu: trich_yeu = "(Không bóc tách được trích yếu)"
                ds_vb_moi.append(
                    f"📍 Số hiệu: <b>{so_kh}</b>\n"
                    f"📅 Ngày đến: <b>{ngay_den}</b>\n"
                    f"📝 Trích yếu: {trich_yeu}"
                )

        if ds_vb_moi:
            # Lấy tầm 5 cái để test xem mặt mũi tin nhắn thế nào
            noi_dung = "\n---\n".join(ds_vb_moi[:5]) 
            msg = (
                f"🚀 <b>TEST ROBOT THÔNG MINH (ÉP GỬI ĐỂ XEM TRÍCH YẾU)</b>\n"
                f"⏰ Cập nhật: {datetime.now().strftime('%H:%M %d/%m/%Y')}\n\n"
                f"{noi_dung}"
            )
            gui_telegram(msg)
            log.info("🔥 Đã ép bắn tin nhắn test lên Telegram!")

    except Exception as e:
        log.error(f"❌ Lỗi: {e}")
    finally:
        if driver:
            driver.quit()

if __name__ == "__main__":
    chay_robot()
