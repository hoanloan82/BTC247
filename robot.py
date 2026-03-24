import time
import os
import json
import logging
import re
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

# Hàm kiểm tra xem 1 chuỗi có phải là Số ký hiệu chuẩn Việt Nam hay không (Chứa dấu / và chữ)
def la_so_ky_hieu(text: str) -> bool:
    if not text: return False
    # Nếu là ngày tháng năm thuần túy (dd/mm/yyyy) -> Loại bỏ ngay không lấy làm số hiệu
    if re.match(r'^\d{1,2}/\d{1,2}/\d{4}$', text): return False
    # Tiêu chuẩn số hiệu VN thường có dấu / và đi kèm chữ cái viết hoa (VD: /UBND, /KH, /STC)
    if "/" in text and len(text) >= 4: return True
    return False

# ============================================================
# 4. ROBOT CHÍNH
# ============================================================
def chay_robot():
    log.info("--- BẮT ĐẦU QUÉT HỆ THỐNG SỞ KH&CN ---")
    driver = None
    ds_da_gui = tai_ds_da_gui()

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

        # Đăng nhập
        driver.get(URL_LOGIN)
        wait.until(EC.presence_of_element_located((By.NAME, "Username")))
        driver.find_element(By.NAME, "Username").send_keys(USER_NAME)
        driver.find_element(By.NAME, "Password").send_keys(PASS_WORD)
        try:
            driver.find_element(By.XPATH, "//input[@type='submit']").click()
        except Exception:
            driver.execute_script("document.forms[0].submit()")
        time.sleep(15)

        # Vào danh sách
        driver.get(URL_DANH_SACH)
        time.sleep(30)

        driver.switch_to.default_content()
        wait.until(EC.frame_to_be_available_and_switch_to_it((By.NAME, "Main")))
        log.info("✅ Đã vào Frame 'Main' thành công!")

        wait.until(EC.presence_of_element_located((By.TAG_NAME, "tr")))
        rows = driver.find_elements(By.TAG_NAME, "tr")

        ds_vb_moi = []

        for row in rows:
            tds = row.find_elements(By.TAG_NAME, "td")
            if len(tds) < 5: continue

            # THUẬT TOÁN TỰ ĐỘNG PHÂN LOẠI CHỮ THÔNG MINH
            so_kh = ""
            trich_yeu = ""
            han_xl = "Không có hạn"

            for td in tds:
                txt = td.text.strip()
                if not txt: continue

                # 1. Nếu là Số ký hiệu chuẩn (Có dấu / và không phải ngày tháng năm thuần túy)
                if la_so_ky_hieu(txt) and not so_kh:
                    so_kh = txt
                    continue

                # 2. Nếu là Trích yếu (Đoạn chữ dài nhất trong các cột)
                if len(txt) > len(trich_yeu) and "số ký hiệu" not in txt.lower() and not la_so_ky_hieu(txt):
                    # Thường trích yếu dài trên 15 ký tự và không phải định dạng ngày đến
                    if len(txt) > 15 and not re.match(r'^\d{1,2}/\d{1,2}/\d{4}$', txt):
                        trich_yeu = txt

                # 3. Nếu là thời hạn xử lý (Có chữ hạn hoặc dạng ngày tháng năm xuất hiện sau trích yếu)
                if re.match(r'^\d{1,2}/\d{1,2}/\d{4}$', txt) and trich_yeu:
                    han_xl = txt

            # Kiểm tra nếu bốc được Số ký hiệu thì mới cho vào danh sách gửi
            if so_kh and so_kh not in ds_da_gui:
                if not trich_yeu: trich_yeu = "(Không bóc tách được trích yếu)"
                
                ds_vb_moi.append(
                    f"📍 Số hiệu: <b>{so_kh}</b>\n"
                    f"📝 Trích yếu: {trich_yeu}\n"
                    f"⏳ Hạn xử lý: <b>{han_xl}</b>"
                )
                ds_da_gui.add(so_kh)

        if ds_vb_moi:
            so_luong = len(ds_vb_moi)
            # Lấy 10 cái để tránh spam
            noi_dung = "\n---\n".join(ds_vb_moi[:10]) 
            msg = (
                f"🚀 <b>SỞ KH&CN: CÓ {so_luong} VĂN BẢN ĐẾN MỚI</b>\n"
                f"⏰ Cập nhật: {datetime.now().strftime('%H:%M %d/%m/%Y')}\n\n"
                f"{noi_dung}"
            )
            gui_telegram(msg)
            luu_ds_da_gui(ds_da_gui)
            log.info(f"🔥 Đã đẩy {so_luong} văn bản chuẩn lên Telegram!")
        else:
            log.info("✅ Không có văn bản mới (Trùng lặp hoặc bảng rỗng).")

    except Exception as e:
        log.error(f"❌ Lỗi: {e}")
    finally:
        if driver:
            driver.quit()

if __name__ == "__main__":
    chay_robot()
