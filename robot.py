import os
import io
import base64
import requests
import logging
import pandas as pd
import pandas_ta as ta
import mplfinance as mpf
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import time
import json
from datetime import datetime
from pathlib import Path
from google import genai
from google.genai import types

# ─────────────────────────────────────────
# 🔑 CẤU HÌNH TỪ GITHUB SECRETS
# ─────────────────────────────────────────
TELEGRAM_TOKEN   = os.environ.get("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
GEMINI_API_KEY   = os.environ.get("GEMINI_API_KEY", "")

# ─────────────────────────────────────────
# ⚙️ THAM SỐ BỘ LỌC (chỉnh tùy ý)
# ─────────────────────────────────────────
BIEN_DONG_MANH_NGUONG   = 1.5    # % thay đổi giá trong 15P để coi là "mạnh"
VOLUME_SPIKE_NGUONG     = 1.8    # volume nến hiện tại / TB 20 nến
RSI_QUA_BAN_NGUONG      = 30     # RSI < 30 → vùng quá bán
RSI_QUA_MUA_NGUONG      = 70     # RSI > 70 → vùng quá mua
DIEU_KIEN_TOI_THIEU     = 2      # cần ít nhất N điều kiện đúng thì mới phân tích
ANTI_SPAM_PHUT          = 30     # không gửi lại nếu < 30 phút kể từ lần trước
LOG_FILE                = "signal_log.json"

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════
# 1. LẤY DỮ LIỆU OHLCV TỪ BINANCE
# ═══════════════════════════════════════════════════════
def lay_ohlcv(symbol: str, interval: str, limit: int = 100) -> pd.DataFrame | None:
    """Kéo dữ liệu nến từ Binance."""
    urls = [
        f"https://api1.binance.com/api/v3/klines",
        f"https://api2.binance.com/api/v3/klines",
        f"https://api3.binance.com/api/v3/klines",
    ]
    params = {"symbol": symbol, "interval": interval, "limit": limit}
    for url in urls:
        try:
            r = requests.get(url, params=params, timeout=15)
            data = r.json()
            if not isinstance(data, list):
                continue
            cols = ['Time','Open','High','Low','Close','Volume','_','_','_','_','_','_']
            df = pd.DataFrame(data, columns=cols)
            df['Time'] = pd.to_datetime(df['Time'], unit='ms')
            df.set_index('Time', inplace=True)
            df = df[['Open','High','Low','Close','Volume']].astype(float)
            return df
        except Exception as e:
            log.warning(f"Binance endpoint lỗi ({url}): {e}")
    log.error(f"Không lấy được OHLCV {symbol} {interval}")
    return None


def lay_gia_spot(symbol: str) -> dict | None:
    """Lấy giá spot hiện tại + thay đổi 24h."""
    try:
        r = requests.get(
            "https://api.binance.com/api/v3/ticker/24hr",
            params={"symbol": symbol}, timeout=10
        )
        d = r.json()
        return {
            "price": float(d["lastPrice"]),
            "change_24h": float(d["priceChangePercent"]),
            "high_24h": float(d["highPrice"]),
            "low_24h": float(d["lowPrice"]),
            "volume_24h": float(d["quoteVolume"]),
        }
    except Exception as e:
        log.error(f"Lỗi lấy giá spot {symbol}: {e}")
        return None


# ═══════════════════════════════════════════════════════
# 2. TÍNH CHỈ BÁO KỸ THUẬT
# ═══════════════════════════════════════════════════════
def tinh_chi_bao(df: pd.DataFrame) -> pd.DataFrame:
    """Tính RSI, MACD, Bollinger Bands, ATR vào dataframe."""
    df = df.copy()
    df.ta.rsi(length=14, append=True)
    df.ta.macd(fast=12, slow=26, signal=9, append=True)
    df.ta.bbands(length=20, std=2, append=True)
    df.ta.atr(length=14, append=True)
    df.ta.sma(length=20, append=True)
    df.ta.ema(length=9, append=True)
    return df


def lay_ket_qua_chi_bao(df: pd.DataFrame) -> dict:
    """Trích xuất giá trị chỉ báo của nến cuối cùng."""
    last = df.iloc[-1]
    prev = df.iloc[-2]

    # Tên cột động từ pandas_ta
    rsi_col   = [c for c in df.columns if c.startswith("RSI_")]
    macd_col  = [c for c in df.columns if c.startswith("MACD_") and "h" not in c.lower() and "s" not in c.lower()]
    macdh_col = [c for c in df.columns if "MACDh_" in c]
    macds_col = [c for c in df.columns if "MACDs_" in c]
    bbu_col   = [c for c in df.columns if c.startswith("BBU_")]
    bbl_col   = [c for c in df.columns if c.startswith("BBL_")]
    bbm_col   = [c for c in df.columns if c.startswith("BBM_")]
    atr_col   = [c for c in df.columns if c.startswith("ATRr_")]
    sma_col   = [c for c in df.columns if c.startswith("SMA_")]
    ema_col   = [c for c in df.columns if c.startswith("EMA_")]

    return {
        "close":       last["Close"],
        "open":        last["Open"],
        "high":        last["High"],
        "low":         last["Low"],
        "volume":      last["Volume"],
        "vol_tb20":    df["Volume"].iloc[-20:].mean(),
        "rsi":         last[rsi_col[0]]   if rsi_col   else None,
        "macd":        last[macd_col[0]]  if macd_col  else None,
        "macd_hist":   last[macdh_col[0]] if macdh_col else None,
        "macd_signal": last[macds_col[0]] if macds_col else None,
        "macd_prev_hist": prev[macdh_col[0]] if macdh_col else None,
        "bb_upper":    last[bbu_col[0]]   if bbu_col   else None,
        "bb_lower":    last[bbl_col[0]]   if bbl_col   else None,
        "bb_mid":      last[bbm_col[0]]   if bbm_col   else None,
        "atr":         last[atr_col[0]]   if atr_col   else None,
        "sma20":       last[sma_col[0]]   if sma_col   else None,
        "ema9":        last[ema_col[0]]   if ema_col   else None,
    }


# ═══════════════════════════════════════════════════════
# 3. NHẬN DIỆN MÔ HÌNH NẾN NHẬT
# ═══════════════════════════════════════════════════════
def phat_hien_mo_hinh_nen(df: pd.DataFrame) -> list[str]:
    """Phát hiện các mô hình nến đẹp tại nến cuối."""
    patterns = []
    c0 = df.iloc[-1]   # nến hiện tại
    c1 = df.iloc[-2]   # nến trước

    body0     = abs(c0["Close"] - c0["Open"])
    range0    = c0["High"] - c0["Low"]
    upper_wick0 = c0["High"] - max(c0["Close"], c0["Open"])
    lower_wick0 = min(c0["Close"], c0["Open"]) - c0["Low"]
    is_bull0  = c0["Close"] > c0["Open"]
    is_bear0  = c0["Close"] < c0["Open"]

    body1     = abs(c1["Close"] - c1["Open"])
    is_bull1  = c1["Close"] > c1["Open"]
    is_bear1  = c1["Close"] < c1["Open"]

    # Hammer / Hanging Man
    if body0 > 0 and lower_wick0 >= 2 * body0 and upper_wick0 <= 0.3 * body0:
        patterns.append("🔨 Hammer (tín hiệu đảo chiều tăng)")

    # Shooting Star / Inverted Hammer
    if body0 > 0 and upper_wick0 >= 2 * body0 and lower_wick0 <= 0.3 * body0:
        patterns.append("⭐ Shooting Star (tín hiệu đảo chiều giảm)")

    # Bullish Engulfing
    if is_bear1 and is_bull0 and c0["Open"] < c1["Close"] and c0["Close"] > c1["Open"]:
        patterns.append("🟢 Bullish Engulfing (nhấn chìm tăng mạnh)")

    # Bearish Engulfing
    if is_bull1 and is_bear0 and c0["Open"] > c1["Close"] and c0["Close"] < c1["Open"]:
        patterns.append("🔴 Bearish Engulfing (nhấn chìm giảm mạnh)")

    # Doji
    if range0 > 0 and body0 / range0 < 0.1:
        patterns.append("✚ Doji (do dự, chờ xác nhận)")

    # Pin Bar
    if range0 > 0 and body0 / range0 < 0.3:
        if lower_wick0 > 2 * body0:
            patterns.append("📌 Pin Bar tăng (đuôi dài bên dưới)")
        elif upper_wick0 > 2 * body0:
            patterns.append("📌 Pin Bar giảm (đuôi dài bên trên)")

    # Marubozu (nến mạnh không có bóng)
    if range0 > 0 and body0 / range0 > 0.9:
        if is_bull0:
            patterns.append("💪 Bullish Marubozu (tăng mạnh không bóng)")
        else:
            patterns.append("💪 Bearish Marubozu (giảm mạnh không bóng)")

    return patterns


# ═══════════════════════════════════════════════════════
# 4. BỘ LỌC THÔNG MINH
# ═══════════════════════════════════════════════════════
def kiem_tra_dieu_kien_kich_hoat(df_15p: pd.DataFrame, cb_15p: dict) -> tuple[bool, list[str], int]:
    """
    Kiểm tra các điều kiện kích hoạt.
    Trả về: (có_kích_hoạt, danh_sách_lý_do, điểm_score)
    """
    ly_do = []
    score = 0

    # 1. Biến động giá mạnh trong 15P
    if len(df_15p) >= 2:
        prev_close = df_15p.iloc[-2]["Close"]
        curr_close = df_15p.iloc[-1]["Close"]
        bien_dong = abs((curr_close - prev_close) / prev_close * 100)
        if bien_dong >= BIEN_DONG_MANH_NGUONG:
            ly_do.append(f"⚡ Biến động mạnh: {bien_dong:.2f}% trong 15P")
            score += 25

    # 2. Volume spike
    vol_ratio = cb_15p["volume"] / cb_15p["vol_tb20"] if cb_15p["vol_tb20"] > 0 else 0
    if vol_ratio >= VOLUME_SPIKE_NGUONG:
        ly_do.append(f"📦 Volume spike: {vol_ratio:.1f}x trung bình 20 nến")
        score += 25

    # 3. RSI vùng cực trị
    rsi = cb_15p.get("rsi")
    if rsi is not None:
        if rsi <= RSI_QUA_BAN_NGUONG:
            ly_do.append(f"🔵 RSI quá bán: {rsi:.1f} (≤ {RSI_QUA_BAN_NGUONG})")
            score += 25
        elif rsi >= RSI_QUA_MUA_NGUONG:
            ly_do.append(f"🔴 RSI quá mua: {rsi:.1f} (≥ {RSI_QUA_MUA_NGUONG})")
            score += 25

    # 4. Mô hình nến đẹp
    patterns = phat_hien_mo_hinh_nen(df_15p)
    if patterns:
        for p in patterns:
            ly_do.append(p)
        score += 25

    # 5. MACD cắt (bonus)
    mh = cb_15p.get("macd_hist")
    mh_prev = cb_15p.get("macd_prev_hist")
    if mh is not None and mh_prev is not None:
        if mh_prev < 0 and mh >= 0:
            ly_do.append("📈 MACD cắt lên (tín hiệu mua)")
            score += 10
        elif mh_prev > 0 and mh <= 0:
            ly_do.append("📉 MACD cắt xuống (tín hiệu bán)")
            score += 10

    # Kiểm tra đủ điều kiện tối thiểu
    kich_hoat = len([l for l in ly_do if any(x in l for x in ["⚡","📦","🔵","🔴","🔨","⭐","🟢","🔴 Bear","📌","💪","✚"])]) >= DIEU_KIEN_TOI_THIEU

    return kich_hoat, ly_do, min(score, 100)


# ═══════════════════════════════════════════════════════
# 5. VẼ BIỂU ĐỒ NẾN (3 KHUNG + CHỈ BÁO)
# ═══════════════════════════════════════════════════════
def ve_chart_day_du(df: pd.DataFrame, symbol: str, interval: str, cb: dict) -> str | None:
    """Vẽ biểu đồ nến có RSI, MACD, Volume. Trả về đường dẫn file."""
    try:
        df_plot = df.copy()

        # Thêm EMA9 và SMA20 lên chart
        add_plots = []
        if "EMA_9" in df_plot.columns:
            add_plots.append(mpf.make_addplot(df_plot["EMA_9"], color='orange', width=1.2, label='EMA9'))
        sma_col = [c for c in df_plot.columns if c.startswith("SMA_")]
        if sma_col:
            add_plots.append(mpf.make_addplot(df_plot[sma_col[0]], color='blue', width=1, linestyle='--', label='SMA20'))

        # RSI panel
        rsi_col = [c for c in df_plot.columns if c.startswith("RSI_")]
        if rsi_col:
            add_plots.append(mpf.make_addplot(df_plot[rsi_col[0]], panel=2, color='purple',
                                               ylabel='RSI', ylim=(0, 100)))
            # Đường 30/70
            add_plots.append(mpf.make_addplot([70]*len(df_plot), panel=2, color='red', linestyle='--', width=0.7))
            add_plots.append(mpf.make_addplot([30]*len(df_plot), panel=2, color='green', linestyle='--', width=0.7))

        # MACD histogram panel
        macdh_col = [c for c in df_plot.columns if "MACDh_" in c]
        macds_col = [c for c in df_plot.columns if "MACDs_" in c]
        macd_col  = [c for c in df_plot.columns if c.startswith("MACD_") and "h" not in c and "s" not in c]
        if macdh_col and macd_col and macds_col:
            colors_hist = ['green' if v >= 0 else 'red' for v in df_plot[macdh_col[0]]]
            add_plots.append(mpf.make_addplot(df_plot[macdh_col[0]], panel=3, type='bar',
                                               color=colors_hist, ylabel='MACD'))
            add_plots.append(mpf.make_addplot(df_plot[macd_col[0]], panel=3, color='blue', width=0.8))
            add_plots.append(mpf.make_addplot(df_plot[macds_col[0]], panel=3, color='orange', width=0.8))

        mc = mpf.make_marketcolors(up='#26a69a', down='#ef5350',
                                    edge='inherit', wick='inherit',
                                    volume={'up':'#26a69a','down':'#ef5350'})
        style = mpf.make_mpf_style(base_mpf_style='nightclouds', marketcolors=mc,
                                    gridstyle=':', gridcolor='#333333')

        interval_label = {"15m": "15 Phút", "1h": "1 Giờ", "4h": "4 Giờ"}.get(interval, interval)
        file_path = f"/tmp/chart_{symbol}_{interval}.png"

        fig, axes = mpf.plot(
            df_plot, type='candle', style=style,
            title=f"\n{symbol} | Khung {interval_label}",
            addplot=add_plots if add_plots else None,
            volume=True,
            panel_ratios=(4, 1, 1.5, 1.5),
            figsize=(14, 10),
            returnfig=True,
        )

        # Thêm BB bands lên price panel
        bbu = [c for c in df_plot.columns if c.startswith("BBU_")]
        bbl = [c for c in df_plot.columns if c.startswith("BBL_")]
        if bbu and bbl and axes:
            ax = axes[0]
            ax.fill_between(range(len(df_plot)),
                            df_plot[bbu[0]].values,
                            df_plot[bbl[0]].values,
                            alpha=0.08, color='cyan')

        fig.savefig(file_path, dpi=130, bbox_inches='tight',
                    facecolor='#131722', edgecolor='none')
        plt.close(fig)
        return file_path

    except Exception as e:
        log.error(f"Lỗi vẽ chart {symbol} {interval}: {e}")
        return None


def anh_sang_base64(file_path: str) -> str:
    """Đọc ảnh → base64 string."""
    with open(file_path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


# ═══════════════════════════════════════════════════════
# 6. PHÂN TÍCH AI VỚI GEMINI VISION
# ═══════════════════════════════════════════════════════
def phan_tich_ai_gemini_vision(
    symbol: str,
    spot: dict,
    cb_15p: dict, cb_1h: dict, cb_4h: dict,
    ly_do_kich_hoat: list[str],
    score: int,
    anh_paths: list[str],
    phong_cach: str = "cả hai"
) -> str:
    """Gửi 3 chart + số liệu vào Gemini Vision để phân tích đa khung."""
    if not GEMINI_API_KEY:
        return "⚠️ Chưa cấu hình GEMINI_API_KEY!"

    def _format_cb(cb: dict) -> str:
        rsi  = f"{cb['rsi']:.1f}"    if cb.get('rsi')    is not None else "N/A"
        macd = f"{cb['macd']:.4f}"   if cb.get('macd')   is not None else "N/A"
        mh   = f"{cb['macd_hist']:.4f}" if cb.get('macd_hist') is not None else "N/A"
        bbu  = f"{cb['bb_upper']:.2f}" if cb.get('bb_upper') is not None else "N/A"
        bbl  = f"{cb['bb_lower']:.2f}" if cb.get('bb_lower') is not None else "N/A"
        vol_r = f"{cb['volume']/cb['vol_tb20']:.1f}x" if cb.get('vol_tb20') and cb['vol_tb20'] > 0 else "N/A"
        return (f"Close: ${cb['close']:,.2f} | RSI: {rsi} | MACD hist: {mh} | "
                f"BB: [{bbl} – {bbu}] | Volume: {vol_r} TB")

    kich_hoat_str = "\n".join(f"  • {l}" for l in ly_do_kich_hoat)

    prompt = f"""
Bạn là một trader chuyên nghiệp, chuyên phân tích kỹ thuật crypto đa khung thời gian.
Tôi đính kèm 3 biểu đồ nến (15P / 1H / 4H) của {symbol}.

━━━ SỐ LIỆU KỸ THUẬT HIỆN TẠI ━━━
💰 Giá hiện tại:  ${spot['price']:,}
📈 Thay đổi 24H:  {spot['change_24h']:.2f}%
📊 High/Low 24H:  ${spot['high_24h']:,} / ${spot['low_24h']:,}

🕐 Khung 15P:  {_format_cb(cb_15p)}
🕐 Khung  1H:  {_format_cb(cb_1h)}
🕐 Khung  4H:  {_format_cb(cb_4h)}

━━━ LÝ DO KÍCH HOẠT PHÂN TÍCH (Score: {score}/100) ━━━
{kich_hoat_str}

━━━ YÊU CẦU PHÂN TÍCH ━━━
Phong cách giao dịch ưu tiên: {phong_cach}

Hãy trả lời theo đúng cấu trúc sau:

**1. NHẬN ĐỊNH ĐA KHUNG**
- 4H (xu hướng tổng thể): ...
- 1H (xu hướng ngắn hạn): ...
- 15P (momentum hiện tại): ...
- ⚠️ Các khung có đồng thuận không? (quan trọng!)

**2. MÔ HÌNH NẾN & TÍN HIỆU**
- Mô hình nến đáng chú ý: ...
- Vùng hỗ trợ / kháng cự gần nhất: ...

**3. KỊCH BẢN GIAO DỊCH**

🟢 KỊCH BẢN LONG (nếu có cơ sở):
- Entry: ...
- Stop Loss: ...
- TP1: ... | TP2: ...
- R:R = ... | Độ tin cậy: .../10

🔴 KỊCH BẢN SHORT (nếu có cơ sở):
- Entry: ...
- Stop Loss: ...
- TP1: ... | TP2: ...
- R:R = ... | Độ tin cậy: .../10

**4. KHUYẾN NGHỊ CUỐI**
▶ NÊN: LONG / SHORT / CHỜ THÊM TÍN HIỆU
▶ Lý do 1 câu: ...

Trả lời ngắn gọn, súc tích, đúng số liệu. Không giải thích dài dòng.
"""

    for attempt in range(3):
        try:
            client = genai.Client(api_key=GEMINI_API_KEY)

            # Chuẩn bị parts: text + ảnh
            parts = [types.Part.from_text(text=prompt)]
            labels = ["📊 Chart 15P", "📊 Chart 1H", "📊 Chart 4H"]
            for i, path in enumerate(anh_paths):
                if path and os.path.exists(path):
                    img_data = anh_sang_base64(path)
                    parts.append(types.Part.from_text(text=f"\n{labels[i]}:"))
                    parts.append(types.Part.from_bytes(
                        data=base64.b64decode(img_data),
                        mime_type="image/png"
                    ))

            response = client.models.generate_content(
                model='gemini-2.0-flash',
                contents=parts
            )
            return response.text

        except Exception as e:
            err_str = str(e)
            if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str:
                wait = 45 * (attempt + 1)
                log.warning(f"⚠️ Rate limit Gemini. Chờ {wait}s... (lần {attempt+1}/3)")
                time.sleep(wait)
            else:
                log.error(f"Lỗi Gemini: {e}")
                return f"⚠️ Lỗi AI: {e}"

    return "⚠️ Hết giới hạn API Gemini sau 3 lần thử."


# ═══════════════════════════════════════════════════════
# 7. GỬI TELEGRAM
# ═══════════════════════════════════════════════════════
def gui_media_group(anh_paths: list[str], caption: str):
    """Gửi nhiều ảnh cùng lúc (media group) kèm caption."""
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        log.warning("Thiếu Telegram config!")
        return

    try:
        # Gửi 3 ảnh dưới dạng album
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMediaGroup"
        files = {}
        media = []
        for i, path in enumerate(anh_paths):
            if path and os.path.exists(path):
                key = f"photo{i}"
                files[key] = open(path, 'rb')
                item = {"type": "photo", "media": f"attach://{key}"}
                if i == 0:
                    item["caption"] = caption[:1024]
                    item["parse_mode"] = "HTML"
                media.append(item)

        data = {"chat_id": TELEGRAM_CHAT_ID, "media": json.dumps(media)}
        r = requests.post(url, data=data, files=files, timeout=60)
        for f in files.values():
            f.close()

        if not r.ok:
            log.warning(f"Gửi media group thất bại: {r.text}")
            # Fallback: gửi text
            gui_tin_nhan_van_ban(caption)

    except Exception as e:
        log.error(f"Lỗi gửi Telegram: {e}")


def gui_tin_nhan_van_ban(text: str):
    """Gửi tin nhắn text thuần."""
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        return
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        # Telegram giới hạn 4096 ký tự
        chunks = [text[i:i+4000] for i in range(0, len(text), 4000)]
        for chunk in chunks:
            requests.post(url, data={"chat_id": TELEGRAM_CHAT_ID, "text": chunk, "parse_mode": "HTML"}, timeout=20)
            time.sleep(0.5)
    except Exception as e:
        log.error(f"Lỗi gửi text Telegram: {e}")


# ═══════════════════════════════════════════════════════
# 8. ANTI-SPAM: LOG TÍN HIỆU
# ═══════════════════════════════════════════════════════
def doc_log_tin_hieu() -> dict:
    try:
        if os.path.exists(LOG_FILE):
            with open(LOG_FILE, 'r') as f:
                return json.load(f)
    except:
        pass
    return {}


def ghi_log_tin_hieu(symbol: str):
    log_data = doc_log_tin_hieu()
    log_data[symbol] = datetime.now().isoformat()
    with open(LOG_FILE, 'w') as f:
        json.dump(log_data, f)


def kiem_tra_anti_spam(symbol: str) -> bool:
    """Trả về True nếu ĐÃ gửi gần đây (nên bỏ qua)."""
    log_data = doc_log_tin_hieu()
    if symbol not in log_data:
        return False
    last_time = datetime.fromisoformat(log_data[symbol])
    elapsed = (datetime.now() - last_time).total_seconds() / 60
    if elapsed < ANTI_SPAM_PHUT:
        log.info(f"Anti-spam: {symbol} đã gửi {elapsed:.0f} phút trước, bỏ qua.")
        return True
    return False


# ═══════════════════════════════════════════════════════
# 9. XỬ LÝ MỘT COIN
# ═══════════════════════════════════════════════════════
def xu_ly_mot_coin(symbol: str):
    """Toàn bộ pipeline cho một symbol (BTCUSDT / ETHUSDT)."""
    log.info(f"▶ Đang xử lý {symbol}...")

    # Anti-spam
    if kiem_tra_anti_spam(symbol):
        return

    # Lấy dữ liệu
    spot = lay_gia_spot(symbol)
    df_15p = lay_ohlcv(symbol, "15m", 80)
    df_1h  = lay_ohlcv(symbol, "1h",  80)
    df_4h  = lay_ohlcv(symbol, "4h",  80)

    if not spot or df_15p is None or df_1h is None or df_4h is None:
        log.error(f"Thiếu dữ liệu cho {symbol}, bỏ qua.")
        return

    # Tính chỉ báo
    df_15p = tinh_chi_bao(df_15p)
    df_1h  = tinh_chi_bao(df_1h)
    df_4h  = tinh_chi_bao(df_4h)

    cb_15p = lay_ket_qua_chi_bao(df_15p)
    cb_1h  = lay_ket_qua_chi_bao(df_1h)
    cb_4h  = lay_ket_qua_chi_bao(df_4h)

    # Bộ lọc
    kich_hoat, ly_do, score = kiem_tra_dieu_kien_kich_hoat(df_15p, cb_15p)
    if not kich_hoat:
        log.info(f"  ↳ {symbol}: chưa đủ điều kiện (score={score}). Bỏ qua.")
        return

    log.info(f"  ↳ {symbol}: KÍCH HOẠT! Score={score}, lý do: {ly_do}")

    # Vẽ 3 chart
    chart_15p = ve_chart_day_du(df_15p, symbol, "15m", cb_15p)
    chart_1h  = ve_chart_day_du(df_1h,  symbol, "1h",  cb_1h)
    chart_4h  = ve_chart_day_du(df_4h,  symbol, "4h",  cb_4h)
    anh_paths = [p for p in [chart_15p, chart_1h, chart_4h] if p]

    # Phân tích AI với ảnh
    nhan_dinh = phan_tich_ai_gemini_vision(
        symbol, spot,
        cb_15p, cb_1h, cb_4h,
        ly_do, score,
        anh_paths,
        phong_cach="cả Scalp (15P) và Swing (1H-4H)"
    )

    # Tạo tin nhắn
    ly_do_str = "\n".join(f"  • {l}" for l in ly_do)
    tin_nhan = (
        f"🚨 <b>TÍN HIỆU {symbol}</b> — Score: <b>{score}/100</b>\n"
        f"📅 <i>{datetime.now().strftime('%H:%M %d/%m/%Y')}</i>\n"
        f"─────────────────\n"
        f"💰 Giá: <b>${spot['price']:,}</b>  ({spot['change_24h']:+.2f}% 24H)\n"
        f"📊 High/Low 24H: ${spot['high_24h']:,} / ${spot['low_24h']:,}\n\n"
        f"<b>Lý do kích hoạt:</b>\n{ly_do_str}\n\n"
        f"─────────────────\n"
        f"{nhan_dinh}"
    )

    # Gửi Telegram
    gui_media_group(anh_paths, tin_nhan)

    # Dọn file ảnh
    for p in anh_paths:
        try:
            os.remove(p)
        except:
            pass

    # Ghi log anti-spam
    ghi_log_tin_hieu(symbol)
    log.info(f"  ✅ Đã gửi tín hiệu {symbol}")


# ═══════════════════════════════════════════════════════
# 10. MAIN
# ═══════════════════════════════════════════════════════
def chay_robot():
    log.info("═══ BẮT ĐẦU CHẠY ROBOT CRYPTO ═══")
    log.info(f"Thời gian: {datetime.now().strftime('%H:%M:%S %d/%m/%Y')}")

    for symbol in ["BTCUSDT", "ETHUSDT"]:
        xu_ly_mot_coin(symbol)
        time.sleep(3)  # nghỉ giữa 2 coin tránh rate limit

    log.info("═══ HOÀN THÀNH ═══")


if __name__ == "__main__":
    chay_robot()
