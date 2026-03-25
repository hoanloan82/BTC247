import time
import os
import json
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
# 1. CẤU HÌNH & THƯ VIỆN LOGGING
# ============================================================
URL_LOGIN     = "https://hscvkhcn.dienbien.gov.vn/names.nsf?Login"
URL_DANH_SACH = "https://hscvkhcn.dienbien.gov.vn/qlvb/vbden.nsf/default?openform&frm=Private_ChoXL?openForm"

USER_NAME        = os.environ.get("SKHCN_USER", "")
PASS_WORD        = os.environ.get("SKHCN_PASS", "")
TELEGRAM_TOKEN   = os.environ.get("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

FILE_DA_GUI = "da_gui.json"

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)


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


def chuyen_chuoi_thanh_ngay(txt_ngay: str):
    """Đổi chuỗi 'dd/mm/yyyy' thành đối tượng datetime"""
    try:
        clean_txt = txt_ngay.replace("(", "").replace(")", "").strip()
        return datetime.strptime(clean_txt, "%d/%m/%Y")
    except ValueError:
        return None


def chay_robot():
    log.info("--- BẮT ĐẦU QUÉT HỆ THỐNG SỞ KH&CN V2.2 (SỬA LỖI TÍNH TOÁN NGÀY) ---")
    driver = None
    ds_da_gui = tai_ds_da_gui()
    
    # Ép máy chủ GitHub tính toán chuẩn theo giờ Việt Nam (GMT+7)
    ngay_hom_nay = datetime.now() + timedelta(hours=7)

    try:
        options = Options()
        options.add_argument("--headless")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--window-size=1920,1080")
        
        driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
        wait = WebDriverWait(driver, 30)

        # 🚀 Bước 1: Đăng nhập
        driver.get(URL_LOGIN)
        wait.until(EC.presence_of_element_located((By.NAME, "Username")))
        driver.find_element(By.NAME, "Username").send_keys(USER_NAME)
        driver.find_element(By.NAME, "Password").send_keys(PASS_WORD)
        try:
            driver.find_element(By.XPATH, "//input[@type='submit']").click()
        except Exception:
            driver.execute_script("document.forms[0].submit()")
        time.sleep(15)

        # 🚀 Bước 2: Vào danh sách bảng chính
        driver.get(URL_DANH_SACH)
        time.sleep(30)

        driver.switch_to.default_content()
        wait.until(EC.frame_to_be_available_and_switch_to_it((By.NAME, "Main")))

        wait.until(EC.presence_of_element_located((By.TAG_NAME, "tr")))
        rows = driver.find_elements(By.TAG_NAME, "tr")
        
        vb_khan = []
        vb_thuong = []

        danh_sach_cho_bam = []
        for row in rows:
            txt_row = row.text.strip()
            if not txt_row or "số ký hiệu" in txt_row.lower() or "/" not in txt_row:
                continue

            parts = txt_row.split()
            if len(parts) < 4: continue

            so_hieu = ""
            ngay_den = ""
            for i, p in enumerate(parts):
                if la_ngay_thang(p) and not ngay_den:
                    ngay_den = p
                if "/" in p and not la_ngay_thang(p) and not so_hieu:
                    so_hieu = p

            tds = row.find_elements(By.TAG_NAME, "td")
            if tds:
                o_bam = tds[min(len(tds)-1, 3)] 
                danh_sach_cho_bam.append({
                    "so_hieu": so_hieu,
                    "ngay_den": ngay_den,
                    "web_element": o_bam
                })

        danh_sach_cho_bam = danh_sach_cho_bam[:3]

        # 🚀 Bước 3: Thâm nhập từng văn bản mới để tìm hạn
        for vb in danh_sach_cho_bam:
            try:
                vb["web_element"].click()
                time.sleep(10)

                page_text = driver.find_element(By.TAG_NAME, "body").text
                
                han_xl_tim_thay = "Không rõ"
                khoang_cach_ngay = 999 

                tat_ca_ngay = re.findall(r'\b\d{1,2}/\d{1,2}/\d{4}\b', page_text)
                for ngay_mau in tat_ca_ngay:
                    doi_tuong_ngay = chuyen_chuoi_thanh_ngay(ngay_mau)
                    if doi_tuong_ngay:
                        date_mau = doi_tuong_ngay.date()
                        date_nay = ngay_hom_nay.date()
                        
                        if date_mau >= date_nay:
                            kc = (date_mau - date_nay).days
                            if kc < khoang_cach_ngay:
                                khoang_cach_ngay = kc
                                han_xl_tim_thay = ngay_mau

                khung_chu_telegram = (
                    f"🏷️ <b>Số hiệu:</b> {vb['so_hieu']}\n"
                    f"📅 <b>Ngày đến:</b> {vb['ngay_den']}\n"
                    f"⏳ <b>Hạn xử lý:</b> {han_xl_tim_thay}"
                )

                if 0 <= khoang_cach_ngay <= 2:
                    vb_khan.append(f"🔴 <b>[GẤP HẠN CÒN {khoang_cach_ngay} NGÀY]</b>\n{khung_chu_telegram}")
                else:
                    vb_thuong.append(f"🔹 <b>[Bình thường]</b>\n{khung_chu_telegram}")

                ds_da_gui.add(vb['so_hieu'])

                driver.back()
                time.sleep(10)
                driver.switch_to.default_content()
                wait.until(EC.frame_to_be_available_and_switch_to_it((By.NAME, "Main")))

            except Exception as e_click:
                log.warning(f"Lỗi bấm xem chi tiết văn bản: {e_click}")
                continue

        # 🚀 Bước 4: Bắn kết quả lên Telegram
        tin_khan = "\n\n➖➖➖➖➖➖➖➖➖➖\n\n".join(vb_khan)
        tin_thuong = "\n\n➖➖➖➖➖➖➖➖➖➖\n\n".join(vb_thuong)

        thong_bao_chot = f"🚀 <b>QUÉT VĂN BẢN ĐẾN SỞ KH&CN V2.2</b>\n⏰ {ngay_hom_nay.strftime('%H:%M %d/%m/%Y')}\n\n"
        
        if vb_khan:
            thong_bao_chot += f"🚨 <b>DANH SÁCH VĂN BẢN KHẨN (HẠN ≤ 2 NGÀY)</b> 🚨\n\n{tin_khan}\n\n"
        
        if vb_thuong:
            thong_bao_chot += f"📋 <b>DANH SÁCH VĂN BẢN THƯỜNG</b>\n\n{tin_thuong}"

        if vb_khan or vb_thuong:
            gui_telegram(thong_bao_chot)
            luu_ds_da_gui(ds_da_gui)
            log.info("🔥 Đã đẩy Radar V2.2 lên Telegram!")
        else:
            log.info("✅ Không có văn bản nào mới.")

    except Exception as e:
        log.error(f"❌ Lỗi: {e}")
    finally:
        if driver:
            driver.quit()

if __name__ == "__main__":
    chay_robot()
