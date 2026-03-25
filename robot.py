import time
import os
import logging
import requests
import re
from datetime import datetime, timedelta
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

# ============================================================
# CẤU HÌNH GIAO DIỆN CHUẨN (KHÔNG CLICK SÂU ĐỂ TRÁNH LỖI IFRAME)
# ============================================================
URL_LOGIN     = "https://hscvkhcn.dienbien.gov.vn/names.nsf?Login"
URL_DANH_SACH = "https://hscvkhcn.dienbien.gov.vn/qlvb/vbden.nsf/default?openform&frm=Private_ChoXL?openForm"

USER_NAME        = os.environ.get("SKHCN_USER", "")
PASS_WORD        = os.environ.get("SKHCN_PASS", "")
TELEGRAM_TOKEN   = os.environ.get("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

def gui_telegram(msg: str) -> bool:
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID: return False
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        resp = requests.post(url, data={"chat_id": TELEGRAM_CHAT_ID, "text": msg, "parse_mode": "HTML"}, timeout=15)
        return resp.status_code == 200
    except Exception:
        return False

def la_ngay_thang(txt: str) -> bool:
    t = txt.replace("(", "").replace(")", "").strip()
    return bool(re.match(r'^\d{1,2}/\d{1,2}/\d{4}$', t))

def chay_robot():
    log.info("--- BẮT ĐẦU QUÉT HỆ THỐNG SỞ KH&CN (BẢN CẮT CHUỖI AN TOÀN) ---")
    driver = None
    gio_vn = datetime.now() + timedelta(hours=7)

    try:
        options = Options()
        options.add_argument("--headless")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--window-size=1920,1080")
        
        # Bỏ qua xác thực SSL nếu trang web của sở bị lỗi chứng chỉ bảo mật
        options.add_argument('--ignore-certificate-errors')
        options.add_argument('--ignore-ssl-errors')

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

        # 2. Vào danh sách
        driver.get(URL_DANH_SACH)
        time.sleep(30)

        driver.switch_to.default_content()
        wait.until(EC.frame_to_be_available_and_switch_to_it((By.NAME, "Main")))

        wait.until(EC.presence_of_element_located((By.TAG_NAME, "tr")))
        rows = driver.find_elements(By.TAG_NAME, "tr")
        ds_vb_moi = []

        for row in rows:
            txt_row = row.text.strip()
            if not txt_row or "số ký hiệu" in txt_row.lower() or "/" not in txt_row:
                continue

            parts = txt_row.split()
            if len(parts) < 6: continue

            so_hieu = ""
            ngay_den = ""
            trich_yeu = ""

            # Tách ngày đến
            if len(parts) > 1 and la_ngay_thang(parts[1]):
                ngay_den = parts[1]

            # Tách Số hiệu và Trích yếu
            for i in range(len(parts)):
                p = parts[i]
                if "/" in p and not la_ngay_thang(p) and not so_hieu:
                    so_hieu = p
                    start_trich_yeu = i + 2
                    if start_trich_yeu < len(parts):
                        trich_yeu = " ".join(parts[start_trich_yeu:])
                    break

            if so_hieu and trich_yeu:
                ds_vb_moi.append(
                    f"🏷️ <b>Số hiệu:</b> {so_hieu}\n"
                    f"📅 <b>Ngày đến:</b> {ngay_den}\n"
                    f"📝 <b>Trích yếu:</b> {trich_yeu}"
                )

        if ds_vb_moi:
            noi_dung = "\n\n➖➖➖➖➖➖➖➖➖➖\n\n".join(ds_vb_moi[:3])
            msg = (
                f"🚀 <b>QUÉT VĂN BẢN ĐẾN SỞ KH&CN V2.4 (AN TOÀN)</b>\n"
                f"⏰ Giờ VN: {gio_vn.strftime('%H:%M %d/%m/%Y')}\n\n"
                f"{noi_dung}"
            )
            gui_telegram(msg)
            log.info("🔥 Đã lấy văn bản bảng ngoài thành công!")
        else:
            log.info("✅ Không tìm thấy văn bản mới.")

    except Exception as e:
        log.error(f"❌ Lỗi: {e}")
    finally:
        if driver:
            driver.quit()

if __name__ == "__main__":
    chay_robot()
