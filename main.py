"""
ربات‌های سیگنال با تمرکز روی کیفیت بالا (Win Rate)

  1) crypto-signal-bot      : کراس EMA 9/21 در ۴ساعته + تایید قوی ۱ساعته
  2) crypto-signal-bot-v10  : شکست رنج تمیز در ۱ساعته با حجم قوی
  3) crypto-signal-bot-v20  : پرایس‌اکشن با کیفیت بالا در پولبک به EMA21
  4) crypto-signal-bot-v40  : رژیم بازار (ADX): پولبک روند یا بازگشت از باند در رنج
  5) crypto-signal-bot-v50  : SMC/ICT ترکیبی
  6) crypto-signal-bot-v60  : فیلتر BTC (1D+4H) + پولبک هم‌جهت روی نمادها

هر ربات: تگ جدا، heartbeat جدا و فایل وضعیت جدا دارد.
خلاصه روزانه ساعت ۸ صبح به وقت ایران برای همه ربات‌های زنده ارسال می‌شود.
"""
import os
import json
import time
import requests
import numpy as np
import pandas as pd
import ccxt
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
import jdatetime

# =====================================================================
# تنظیمات عمومی
# =====================================================================
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
CHAT_ID = os.environ.get("CHAT_ID")
TOOBIT_API_KEY = os.environ.get("TOOBIT_API_KEY")
TOOBIT_SECRET = os.environ.get("TOOBIT_SECRET")

SYMBOLS = [
    # --- Core Majors ---
    "BTC-SWAP-USDT", "ETH-SWAP-USDT", "SOL-SWAP-USDT", "XRP-SWAP-USDT",
    "BNB-SWAP-USDT", "DOGE-SWAP-USDT", "ADA-SWAP-USDT", "TRX-SWAP-USDT",
    "AVAX-SWAP-USDT", "LINK-SWAP-USDT", "DOT-SWAP-USDT", "LTC-SWAP-USDT",
    "BCH-SWAP-USDT", "TON-SWAP-USDT", "SUI-SWAP-USDT", "NEAR-SWAP-USDT",
    "APT-SWAP-USDT", "ARB-SWAP-USDT", "OP-SWAP-USDT", "ATOM-SWAP-USDT",

    # --- High Volume / Popular ---
    "UNI-SWAP-USDT", "AAVE-SWAP-USDT", "FIL-SWAP-USDT", "INJ-SWAP-USDT",
    "TIA-SWAP-USDT", "JUP-SWAP-USDT", "ENA-SWAP-USDT", "WIF-SWAP-USDT",
    "1000PEPE-SWAP-USDT", "1000SHIB-SWAP-USDT", "WLD-SWAP-USDT", "SEI-SWAP-USDT",
    "RUNE-SWAP-USDT", "LDO-SWAP-USDT", "STX-SWAP-USDT", "IMX-SWAP-USDT",
    "HBAR-SWAP-USDT", "ICP-SWAP-USDT", "ETC-SWAP-USDT", "XLM-SWAP-USDT",

    # --- DeFi & Layer 2 ---
    "CRV-SWAP-USDT", "SNX-SWAP-USDT",
    "COMP-SWAP-USDT", "SUSHI-SWAP-USDT", "1INCH-SWAP-USDT", "GRT-SWAP-USDT",
    "DYDX-SWAP-USDT", "GMX-SWAP-USDT", "PENDLE-SWAP-USDT", "ONDO-SWAP-USDT",
    "JTO-SWAP-USDT", "PYTH-SWAP-USDT", "STRK-SWAP-USDT", "MANTA-SWAP-USDT",

    # --- Meme & Community ---
    "1000BONK-SWAP-USDT", "1000FLOKI-SWAP-USDT", "MEME-SWAP-USDT", "ORDI-SWAP-USDT",
    "1000SATS-SWAP-USDT", "1000RATS-SWAP-USDT", "POPCAT-SWAP-USDT",
    "BRETT-SWAP-USDT", "TURBO-SWAP-USDT", "1000000MOG-SWAP-USDT", "DOGS-SWAP-USDT",

    # --- AI, Gaming & Metaverse ---
    "FET-SWAP-USDT", "TAO-SWAP-USDT",
    "AKT-SWAP-USDT", "ILV-SWAP-USDT",
    "AXS-SWAP-USDT", "SAND-SWAP-USDT", "MANA-SWAP-USDT", "GALA-SWAP-USDT",

    # --- Infrastructure & Others ---
    "ALGO-SWAP-USDT", "VET-SWAP-USDT", "EGLD-SWAP-USDT", "FLOW-SWAP-USDT",
    "KAVA-SWAP-USDT", "ROSE-SWAP-USDT", "KAS-SWAP-USDT",
    "THETA-SWAP-USDT", "CHZ-SWAP-USDT", "ENJ-SWAP-USDT", "ZIL-SWAP-USDT",
    "ONE-SWAP-USDT", "QTUM-SWAP-USDT", "IOTA-SWAP-USDT", "NEO-SWAP-USDT"
]

BTC_SYMBOL = "BTC-SWAP-USDT"
MAX_HEARTBEATS = 2
MAX_SIGNALS_PER_RUN = 5
SUMMARY_FILE = "daily_summary.json"
SUMMARY_HOUR = 8

MIN_SL_PCT = 0.0035
MAX_ENTRY_DRIFT_ATR = 0.45

TF_MS = {
    "5m": 5 * 60 * 1000,
    "15m": 15 * 60 * 1000,
    "1h": 60 * 60 * 1000,
    "4h": 4 * 60 * 60 * 1000,
    "1d": 24 * 60 * 60 * 1000,
}

# --- ربات ۱ ---
B1_CROSS_LOOKBACK = 2
B1_RSI_LONG = (48, 68)
B1_RSI_SHORT = (32, 52)
B1_VOLUME_MULT = 1.4
B1_SL_ATR, B1_TP_ATR = 1.7, 3.4
B1_MIN_SCORE = 0.62

# --- ربات ۲ ---
B2_LOOKBACK = 20
B2_VOLUME_MULT = 1.7
B2_CLOSE_POS = 0.70
B2_MAX_EXTENSION_ATR = 1.1
B2_RSI_LONG = (55, 75)
B2_RSI_SHORT = (25, 45)
B2_SL_ATR, B2_TP_ATR = 1.5, 3.2
B2_MAX_RANGE_ATR = 6.0
B2_MIN_BODY_ATR = 0.45
B2_MIN_SCORE = 0.60

# --- ربات ۳ ---
B3_MIN_BODY_ATR = 0.70
B3_TOUCH_ATR = 0.22
B3_MIN_DISTANCE_ATR = 0.12
B3_VOLUME_MULT = 1.4
B3_RSI_LONG = (42, 65)
B3_RSI_SHORT = (35, 58)
B3_SL_BUFFER_ATR = 0.10
B3_MIN_RISK_ATR, B3_MAX_RISK_ATR = 0.6, 2.1
B3_RR = 2.2
B3_COOLDOWN_HOURS = 3
B3_MIN_SCORE = 0.60

# --- ربات ۴ ---
B4_ADX_TREND = 25
B4_ADX_RANGE = 20
B4_TREND_GAP_4H_ATR = 0.30
B4_TREND_TOUCH_ATR = 0.20
B4_TREND_MAX_EXT_ATR = 1.0
B4_TREND_RSI_LONG = (40, 62)
B4_TREND_RSI_SHORT = (38, 60)
B4_TREND_SL_ATR, B4_TREND_TP_ATR = 1.2, 3.0
B4_RANGE_RSI_LONG_MAX = 35
B4_RANGE_RSI_SHORT_MIN = 65
B4_RANGE_SL_BUFFER_ATR = 0.5
B4_RANGE_MIN_RR = 1.5
B4_MIN_SCORE = 0.50
B4_COOLDOWN_HOURS = 3

# --- ربات ۵ ---
B5_LOOKBACK_1H = 20
B5_SWEEP_RECENT = 3
B5_RANGE_BARS = 48
B5_FVG_RECENT = 12
B5_TREND_GAP_4H_ATR = 0.30
B5_SL_BUFFER_ATR = 0.10
B5_MIN_RR = 2.0
B5_MAX_RISK_ATR = 3.0
B5_MIN_SCORE = 0.50
B5_COOLDOWN_HOURS = 3

# --- ربات ۶ (فیلتر BTC + ورود هم‌جهت) ---
B6_MIN_GAP_ATR = 0.30
B6_MIN_ADX = 22
B6_MAX_EXT_ATR = 1.5
B6_1H_ALIGN_BONUS = 0.12
B6_ALT_GAP_ATR = 0.25
B6_TOUCH_ATR = 0.25
B6_MAX_EXT_ALT_ATR = 1.2
B6_RSI_LONG = (42, 65)
B6_RSI_SHORT = (35, 58)
B6_VOLUME_MULT = 1.2
B6_SL_ATR, B6_TP_ATR = 1.5, 3.0
B6_MIN_SCORE = 0.58
B6_COOLDOWN_HOURS = 3


# =====================================================================
# ابزارهای عمومی
# =====================================================================
def get_iran_time():
    now = datetime.now(ZoneInfo("Asia/Tehran"))
    date_gregorian = now.strftime("%Y-%m-%d")
    now_jalali = jdatetime.datetime.fromgregorian(datetime=now)
    date_jalali = now_jalali.strftime("%Y/%m/%d")
    time_str = now.strftime("%H:%M:%S")
    return date_gregorian, date_jalali, time_str


def send_telegram(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try:
        r = requests.post(url, json={"chat_id": CHAT_ID, "text": message}, timeout=10)
        if r.status_code == 200:
            return r.json().get("result", {}).get("message_id")
    except Exception as e:
        print(f"⚠️ خطا در ارسال تلگرام: {e}")
    return None


def delete_telegram(message_id):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/deleteMessage"
    try:
        requests.post(url, json={"chat_id": CHAT_ID, "message_id": message_id}, timeout=10)
    except Exception as e:
        print(f"⚠️ خطا در حذف پیام: {e}")


def format_number(value):
    if value >= 1000:
        return f"{value:.2f}"
    elif value >= 1:
        return f"{value:.4f}"
    else:
        return f"{value:.6f}"


def load_json(path, default):
    try:
        with open(path, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def save_json(path, data):
    with open(path, "w") as f:
        json.dump(data, f)


def now_ms():
    return int(time.time() * 1000)


# =====================================================================
# داده و اندیکاتورها
# =====================================================================
class Ctx:
    def __init__(self, exchange):
        self.exchange = exchange
        self.cache = {}
        self.tickers = {}
        self.btc_filter = None


def create_exchange():
    params = {"enableRateLimit": True}
    if TOOBIT_API_KEY and TOOBIT_SECRET:
        params.update({"apiKey": TOOBIT_API_KEY, "secret": TOOBIT_SECRET})
    return ccxt.toobit(params)


def fetch_ohlcv(exchange, symbol, timeframe, limit=150):
    raw = exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
    df = pd.DataFrame(raw, columns=["timestamp", "open", "high", "low", "close", "volume"])
    if len(df) and df["timestamp"].iloc[-1] + TF_MS[timeframe] > now_ms():
        df = df.iloc[:-1]
    return df.reset_index(drop=True)


def calculate_indicators(df):
    df["ema9"] = df["close"].ewm(span=9, adjust=False).mean()
    df["ema21"] = df["close"].ewm(span=21, adjust=False).mean()
    df["ema50"] = df["close"].ewm(span=50, adjust=False).mean()

    delta = df["close"].diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()
    avg_loss = loss.ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    rsi = rsi.where(~((avg_loss == 0) & (avg_gain > 0)), 100.0)
    rsi = rsi.where(~((avg_loss == 0) & (avg_gain == 0)), 50.0)
    df["rsi"] = rsi

    high_low = df["high"] - df["low"]
    high_close = (df["high"] - df["close"].shift()).abs()
    low_close = (df["low"] - df["close"].shift()).abs()
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    df["atr"] = tr.ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()

    up = df["high"].diff()
    down = -df["low"].diff()
    plus_dm = up.where((up > down) & (up > 0), 0.0)
    minus_dm = down.where((down > up) & (down > 0), 0.0)
    atr_safe = df["atr"].replace(0, np.nan)
    plus_di = 100 * plus_dm.ewm(alpha=1 / 14, adjust=False, min_periods=14).mean() / atr_safe
    minus_di = 100 * minus_dm.ewm(alpha=1 / 14, adjust=False, min_periods=14).mean() / atr_safe
    di_sum = (plus_di + minus_di).replace(0, np.nan)
    dx = 100 * (plus_di - minus_di).abs() / di_sum
    df["adx"] = dx.ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()

    bb_mid = df["close"].rolling(20).mean()
    bb_sd = df["close"].rolling(20).std()
    df["bb_mid"] = bb_mid
    df["bb_up"] = bb_mid + 2 * bb_sd
    df["bb_lo"] = bb_mid - 2 * bb_sd
    return df


def get_data(ctx, symbol, timeframe):
    key = (symbol, timeframe)
    if key not in ctx.cache:
        df = fetch_ohlcv(ctx.exchange, symbol, timeframe, 150)
        if len(df) < 40:
            raise ValueError(f"داده‌ی کافی برای {symbol} {timeframe} نیست ({len(df)} کندل)")
        ctx.cache[key] = calculate_indicators(df)
    return ctx.cache[key]


def get_price(ctx, symbol):
    if symbol not in ctx.tickers:
        ctx.tickers[symbol] = float(ctx.exchange.fetch_ticker(symbol)["last"])
    return ctx.tickers[symbol]


def trend_of(df):
    last = df.iloc[-1]
    if last["ema9"] > last["ema21"]:
        return "LONG"
    if last["ema9"] < last["ema21"]:
        return "SHORT"
    return "NONE"


def get_btc_trend(ctx):
    try:
        t4 = trend_of(get_data(ctx, BTC_SYMBOL, "4h"))
        t1 = trend_of(get_data(ctx, BTC_SYMBOL, "1h"))
        return t4, t1
    except Exception as e:
        print(f"⚠️ خطا در دریافت روند بیت‌کوین: {e}")
        return "UNKNOWN", "UNKNOWN"


def atr_levels(direction, atr, sl_mult, tp_mult):
    def levels(entry):
        if direction == "LONG":
            return entry - atr * sl_mult, entry + atr * tp_mult
        return entry + atr * sl_mult, entry - atr * tp_mult
    return levels


def ratio(cur, avg):
    return cur / avg if avg and avg > 0 else 0.0


# =====================================================================
# استراتژی ۱: کراس EMA
# =====================================================================
def find_recent_cross(df, direction, lookback=B1_CROSS_LOOKBACK):
    if trend_of(df) != direction:
        return None, None
    n = len(df)
    for age in range(lookback):
        i = n - 1 - age
        if i < 1:
            break
        cur, prev = df.iloc[i], df.iloc[i - 1]
        if direction == "LONG" and prev["ema9"] <= prev["ema21"] and cur["ema9"] > cur["ema21"]:
            return age, int(df["timestamp"].iloc[i])
        if direction == "SHORT" and prev["ema9"] >= prev["ema21"] and cur["ema9"] < cur["ema21"]:
            return age, int(df["timestamp"].iloc[i])
    return None, None


def analyze_cross(symbol, ctx):
    df_4h = get_data(ctx, symbol, "4h")
    direction = cross_age = cross_ts = None
    for d in ("LONG", "SHORT"):
        age, ts = find_recent_cross(df_4h, d, lookback=B1_CROSS_LOOKBACK)
        if age is not None:
            direction, cross_age, cross_ts = d, age, ts
            break
    if direction is None:
        return None

    df_1h = get_data(ctx, symbol, "1h")
    if trend_of(df_1h) != direction:
        return None

    last_1h = df_1h.iloc[-1]
    atr_1h = float(last_1h["atr"])
    if np.isnan(atr_1h) or atr_1h <= 0:
        return None

    gap_1h = abs(float(last_1h["ema9"]) - float(last_1h["ema21"]))
    if gap_1h < 0.35 * atr_1h:
        print(f"  {symbol}: 1H trend too weak")
        return None

    vol_1h = float(last_1h["volume"])
    avg_vol_1h = float(df_1h["volume"].iloc[-21:-1].mean())
    vol_ratio_1h = ratio(vol_1h, avg_vol_1h)

    df_15m = get_data(ctx, symbol, "15m")
    last = df_15m.iloc[-1]
    rsi = float(last["rsi"])
    if np.isnan(rsi):
        return None

    lo, hi = B1_RSI_LONG if direction == "LONG" else B1_RSI_SHORT
    rsi_ok = lo <= rsi <= hi
    vol_ok = vol_ratio_1h >= B1_VOLUME_MULT

    print(f"  {symbol}: {direction} 4H cross(age={cross_age}) | 1H ok | "
          f"RSI {rsi:.1f} ok={rsi_ok} | Vol1H x{vol_ratio_1h:.2f} ok={vol_ok}")

    if not (rsi_ok and vol_ok):
        return None

    close = float(last["close"])
    if (atr_1h * B1_SL_ATR) / close < MIN_SL_PCT:
        return None

    trend_score = min(gap_1h / atr_1h, 1.6) / 1.6
    score = (0.32 * min(vol_ratio_1h, 3.5) / 3.5
             + 0.28 * (B1_CROSS_LOOKBACK - cross_age) / B1_CROSS_LOOKBACK
             + 0.25 * trend_score
             + 0.15 * min(abs(rsi - 50) / 22.0, 1.0))

    if score < B1_MIN_SCORE:
        print(f"  {symbol}: score too low ({score:.3f})")
        return None

    return {
        "symbol": symbol, "direction": direction, "close": close,
        "atr": atr_1h, "rsi": rsi,
        "volume": vol_1h, "avg_volume": avg_vol_1h,
        "signal_key": cross_ts, "score": score,
        "setup": f"EMA9/21 cross 4H (age {cross_age})",
        "levels": atr_levels(direction, atr_1h, B1_SL_ATR, B1_TP_ATR),
    }


# =====================================================================
# استراتژی ۲: Breakout
# =====================================================================
def analyze_breakout(symbol, ctx):
    df = get_data(ctx, symbol, "1h")
    lb = B2_LOOKBACK
    if len(df) < lb + 5:
        return None

    last = df.iloc[-1]
    prev = df.iloc[-2]

    range_high = float(df["high"].iloc[-(lb + 1):-1].max())
    range_low = float(df["low"].iloc[-(lb + 1):-1].min())
    range_size = range_high - range_low

    close = float(last["close"])
    high = float(last["high"])
    low = float(last["low"])
    open_ = float(last["open"])
    atr = float(last["atr"])
    rsi = float(last["rsi"])
    rng = high - low
    body = abs(close - open_)

    if np.isnan(atr) or atr <= 0 or rng <= 0 or range_size <= 0:
        return None

    if range_size > B2_MAX_RANGE_ATR * atr:
        print(f"  {symbol}: range too wide ({range_size / atr:.1f} ATR)")
        return None

    direction = level = None

    if (close > range_high and
            float(prev["close"]) <= range_high and
            (close - low) / rng >= B2_CLOSE_POS and
            (close - range_high) <= B2_MAX_EXTENSION_ATR * atr):
        direction, level = "LONG", range_high

    elif (close < range_low and
          float(prev["close"]) >= range_low and
          (high - close) / rng >= B2_CLOSE_POS and
          (range_low - close) <= B2_MAX_EXTENSION_ATR * atr):
        direction, level = "SHORT", range_low

    if direction is None:
        return None

    if body < B2_MIN_BODY_ATR * atr:
        print(f"  {symbol}: {direction} breakout but body too weak ({body / atr:.2f} ATR)")
        return None

    volume = float(last["volume"])
    avg_volume = float(df["volume"].iloc[-21:-1].mean())
    vol_ratio = ratio(volume, avg_volume)

    lo, hi = B2_RSI_LONG if direction == "LONG" else B2_RSI_SHORT
    rsi_ok = lo <= rsi <= hi
    vol_ok = vol_ratio >= B2_VOLUME_MULT

    df_4h = get_data(ctx, symbol, "4h")
    l4 = df_4h.iloc[-1]
    slow_trend = "LONG" if l4["ema21"] > l4["ema50"] else "SHORT" if l4["ema21"] < l4["ema50"] else "NONE"
    trend_ok = slow_trend == direction

    print(f"  {symbol}: {direction} breakout 1H | RSI {rsi:.1f} ok={rsi_ok} | "
          f"Vol x{vol_ratio:.2f} ok={vol_ok} | 4H ok={trend_ok}")

    if not (rsi_ok and vol_ok and trend_ok):
        reasons = []
        if not rsi_ok:
            reasons.append(f"RSI {rsi:.1f} خارج {lo}-{hi}")
        if not vol_ok:
            reasons.append(f"حجم {vol_ratio:.2f} < {B2_VOLUME_MULT}")
        if not trend_ok:
            reasons.append(f"روند ۴ساعته {slow_trend} مخالف {direction}")
        print(f"    -> rejected: " + " | ".join(reasons))
        return None

    if (atr * B2_SL_ATR) / close < MIN_SL_PCT:
        return None

    strength = min(abs(close - level) / atr, 1.0)
    body_score = min(body / atr, 1.5) / 1.5
    atr_4h = float(l4["atr"]) if not np.isnan(l4["atr"]) else 0.0
    gap_4h = abs(float(l4["ema21"]) - float(l4["ema50"]))
    trend_score = min(gap_4h / atr_4h, 1.0) if atr_4h > 0 else 0.0

    score = (0.35 * min(vol_ratio, 4.0) / 4.0
             + 0.25 * strength
             + 0.20 * body_score
             + 0.20 * trend_score)

    if score < B2_MIN_SCORE:
        print(f"    -> rejected (score {score:.3f} < {B2_MIN_SCORE})")
        return None

    return {
        "symbol": symbol, "direction": direction, "close": close,
        "atr": atr, "rsi": rsi,
        "volume": volume, "avg_volume": avg_volume,
        "signal_key": int(last["timestamp"]), "score": score,
        "setup": f"Breakout {lb}x1H ({'high' if direction == 'LONG' else 'low'} {format_number(level)})",
        "levels": atr_levels(direction, atr, B2_SL_ATR, B2_TP_ATR),
    }


# =====================================================================
# استراتژی ۳: Price Action
# =====================================================================
def analyze_price_action(symbol, ctx):
    df_4h = get_data(ctx, symbol, "4h")
    direction = trend_of(df_4h)
    if direction not in ("LONG", "SHORT"):
        return None

    l4 = df_4h.iloc[-1]
    atr_4h = float(l4["atr"])
    gap_4h = abs(float(l4["ema9"]) - float(l4["ema21"]))
    if np.isnan(atr_4h) or atr_4h <= 0 or gap_4h < 0.4 * atr_4h:
        return None

    df = get_data(ctx, symbol, "15m")
    last = df.iloc[-1]
    prev = df.iloc[-2]

    atr = float(last["atr"])
    rsi = float(last["rsi"])
    ema21 = float(last["ema21"])
    if np.isnan(atr) or np.isnan(rsi) or atr <= 0:
        return None

    o, h, l, c = (float(last[k]) for k in ("open", "high", "low", "close"))
    po, pc, ph, pl = (float(prev[k]) for k in ("open", "close", "high", "low"))

    body = abs(c - o)
    rng = h - l
    upper = h - max(c, o)
    lower = min(c, o) - l

    volume = float(last["volume"])
    avg_volume = float(df["volume"].iloc[-21:-1].mean())
    vol_ratio = ratio(volume, avg_volume)
    vol_ok = vol_ratio >= B3_VOLUME_MULT

    pattern = None
    extreme = None

    if direction == "LONG":
        if (pc < po and c > o and c >= po and o <= pc and
                body >= B3_MIN_BODY_ATR * atr and body > abs(pc - po) * 1.15):
            pattern = "Bullish Engulfing"
            extreme = min(l, pl)
        elif (rng >= 1.0 * atr and lower >= 2.4 * body and
              upper <= 0.30 * body and c >= (l + 0.68 * rng) and body >= 0.25 * atr):
            pattern = "Hammer"
            extreme = l
        elif (c > o and body >= 0.85 * atr and body > 2.0 * (upper + lower)):
            pattern = "Strong Bullish"
            extreme = l
        touch = (pattern is not None and
                 extreme <= ema21 + B3_TOUCH_ATR * atr and
                 c > ema21 + B3_MIN_DISTANCE_ATR * atr)
        rsi_lo, rsi_hi = B3_RSI_LONG
    else:
        if (pc > po and c < o and c <= po and o >= pc and
                body >= B3_MIN_BODY_ATR * atr and body > abs(pc - po) * 1.15):
            pattern = "Bearish Engulfing"
            extreme = max(h, ph)
        elif (rng >= 1.0 * atr and upper >= 2.4 * body and
              lower <= 0.30 * body and c <= (h - 0.68 * rng) and body >= 0.25 * atr):
            pattern = "Shooting Star"
            extreme = h
        elif (c < o and body >= 0.85 * atr and body > 2.0 * (upper + lower)):
            pattern = "Strong Bearish"
            extreme = h
        touch = (pattern is not None and
                 extreme >= ema21 - B3_TOUCH_ATR * atr and
                 c < ema21 - B3_MIN_DISTANCE_ATR * atr)
        rsi_lo, rsi_hi = B3_RSI_SHORT

    rsi_ok = rsi_lo <= rsi <= rsi_hi

    if pattern is None:
        return None

    print(f"  {symbol}: {direction} 4H | {pattern} | pullback ok={touch} | "
          f"RSI {rsi:.1f} ok={rsi_ok} | Vol x{vol_ratio:.2f} ok={vol_ok}")

    if not (touch and rsi_ok and vol_ok):
        return None

    if direction == "LONG":
        sl_level = extreme - B3_SL_BUFFER_ATR * atr
        risk = c - sl_level
    else:
        sl_level = extreme + B3_SL_BUFFER_ATR * atr
        risk = sl_level - c

    if not (B3_MIN_RISK_ATR * atr <= risk <= B3_MAX_RISK_ATR * atr) or risk / c < MIN_SL_PCT:
        print(f"  {symbol}: structural SL out of range")
        return None

    def levels(entry):
        r = (entry - sl_level) if direction == "LONG" else (sl_level - entry)
        if r <= 0:
            return None
        tp = entry + B3_RR * r if direction == "LONG" else entry - B3_RR * r
        return sl_level, tp

    trend_score = min(gap_4h / atr_4h, 1.2) / 1.2
    body_score = min(body / atr, 1.8) / 1.8
    score = (0.30 * min(vol_ratio, 3.5) / 3.5
             + 0.35 * body_score
             + 0.35 * trend_score)

    if score < B3_MIN_SCORE:
        print(f"  {symbol}: score too low ({score:.3f})")
        return None

    return {
        "symbol": symbol, "direction": direction, "close": c,
        "atr": atr, "rsi": rsi,
        "volume": volume, "avg_volume": avg_volume,
        "signal_key": int(last["timestamp"]), "score": score,
        "setup": f"{pattern} @ EMA21 pullback",
        "levels": levels,
    }


# =====================================================================
# استراتژی ۴: رژیم ADX
# =====================================================================
def analyze_regime(symbol, ctx):
    df = get_data(ctx, symbol, "1h")
    last = df.iloc[-1]

    close, open_, high, low = (float(last[k]) for k in ("close", "open", "high", "low"))
    atr = float(last["atr"])
    rsi = float(last["rsi"])
    adx = float(last["adx"])
    if any(np.isnan(v) for v in (atr, rsi, adx)) or atr <= 0:
        return None

    volume = float(last["volume"])
    avg_volume = float(df["volume"].iloc[-21:-1].mean())
    vol_ratio = ratio(volume, avg_volume)

    if adx >= B4_ADX_TREND:
        mode = "trend"
    elif adx <= B4_ADX_RANGE:
        mode = "range"
    else:
        print(f"  {symbol}: ADX {adx:.1f} بین دو رژیم، بدون معامله")
        return None

    if mode == "trend":
        df_4h = get_data(ctx, symbol, "4h")
        l4 = df_4h.iloc[-1]
        direction = trend_of(df_4h)
        atr_4h = float(l4["atr"])
        if direction not in ("LONG", "SHORT") or np.isnan(atr_4h) or atr_4h <= 0:
            return None
        gap_4h = abs(float(l4["ema9"]) - float(l4["ema21"]))
        if gap_4h < B4_TREND_GAP_4H_ATR * atr_4h:
            return None

        ema21 = float(last["ema21"])
        if direction == "LONG":
            touched = (low <= ema21 + B4_TREND_TOUCH_ATR * atr and close > ema21 and close > open_
                       and close - ema21 <= B4_TREND_MAX_EXT_ATR * atr)
            rsi_ok = B4_TREND_RSI_LONG[0] <= rsi <= B4_TREND_RSI_LONG[1]
        else:
            touched = (high >= ema21 - B4_TREND_TOUCH_ATR * atr and close < ema21 and close < open_
                       and ema21 - close <= B4_TREND_MAX_EXT_ATR * atr)
            rsi_ok = B4_TREND_RSI_SHORT[0] <= rsi <= B4_TREND_RSI_SHORT[1]

        print(f"  {symbol}: ADX {adx:.1f} TREND {direction} | پولبک ok={touched} | RSI {rsi:.1f} ok={rsi_ok}")
        if not (touched and rsi_ok):
            return None
        if (atr * B4_TREND_SL_ATR) / close < MIN_SL_PCT:
            return None

        score = (0.50 * min(adx / 40.0, 1.0)
                 + 0.30 * min(gap_4h / atr_4h, 1.0)
                 + 0.20 * min(vol_ratio / 2.0, 1.0))
        if score < B4_MIN_SCORE:
            print(f"  {symbol}: score too low ({score:.3f})")
            return None

        return {
            "symbol": symbol, "direction": direction, "close": close,
            "atr": atr, "rsi": rsi,
            "volume": volume, "avg_volume": avg_volume,
            "signal_key": int(last["timestamp"]), "score": score,
            "setup": "رژیم روند: پولبک به میانگین ۱H",
            "levels": atr_levels(direction, atr, B4_TREND_SL_ATR, B4_TREND_TP_ATR),
        }

    bb_lo, bb_mid, bb_up = (float(last[k]) for k in ("bb_lo", "bb_mid", "bb_up"))
    if any(np.isnan(v) for v in (bb_lo, bb_mid, bb_up)):
        return None

    if low <= bb_lo and close > bb_lo and rsi <= B4_RANGE_RSI_LONG_MAX:
        direction = "LONG"
        sl = low - B4_RANGE_SL_BUFFER_ATR * atr
        tp = bb_mid
    elif high >= bb_up and close < bb_up and rsi >= B4_RANGE_RSI_SHORT_MIN:
        direction = "SHORT"
        sl = high + B4_RANGE_SL_BUFFER_ATR * atr
        tp = bb_mid
    else:
        print(f"  {symbol}: ADX {adx:.1f} RANGE | بدون بازگشت از باند (RSI {rsi:.1f})")
        return None

    if (direction == "LONG" and not (sl < close < tp)) or (direction == "SHORT" and not (tp < close < sl)):
        return None
    risk = abs(close - sl)
    rr = abs(tp - close) / risk
    if rr < B4_RANGE_MIN_RR or risk / close < MIN_SL_PCT:
        print(f"  {symbol}: RANGE {direction} rejected (RR {rr:.2f})")
        return None

    def levels(entry):
        if direction == "LONG":
            return (sl, tp) if sl < entry < tp else None
        return (sl, tp) if tp < entry < sl else None

    score = (0.50 * min(rr / 3.0, 1.0)
             + 0.30 * min(abs(rsi - 50) / 20.0, 1.0)
             + 0.20 * min(vol_ratio / 2.0, 1.0))
    if score < B4_MIN_SCORE:
        print(f"  {symbol}: score too low ({score:.3f})")
        return None

    print(f"  {symbol}: ADX {adx:.1f} RANGE {direction} | RSI {rsi:.1f} | RR {rr:.2f}")
    return {
        "symbol": symbol, "direction": direction, "close": close,
        "atr": atr, "rsi": rsi,
        "volume": volume, "avg_volume": avg_volume,
        "signal_key": int(last["timestamp"]), "score": score,
        "setup": "رژیم رنج: بازگشت از باند به میانگین ۱H",
        "levels": levels,
    }


# =====================================================================
# استراتژی ۵: SMC/ICT
# =====================================================================
def analyze_smc(symbol, ctx):
    df4 = get_data(ctx, symbol, "4h")
    l4 = df4.iloc[-1]
    direction = trend_of(df4)
    atr4 = float(l4["atr"])
    if direction not in ("LONG", "SHORT") or np.isnan(atr4) or atr4 <= 0:
        return None
    if abs(float(l4["ema9"]) - float(l4["ema21"])) < B5_TREND_GAP_4H_ATR * atr4:
        return None

    df1 = get_data(ctx, symbol, "1h")
    n1 = len(df1)
    if n1 < B5_RANGE_BARS + B5_LOOKBACK_1H + 5:
        return None
    atr1 = float(df1["atr"].iloc[-1])
    if np.isnan(atr1) or atr1 <= 0:
        return None
    hi1, lo1, c1 = df1["high"].values, df1["low"].values, df1["close"].values
    ts1 = df1["timestamp"].values

    sweep = None
    for m in range(n1 - 1, n1 - 1 - B5_SWEEP_RECENT, -1):
        win = slice(m - B5_LOOKBACK_1H, m)
        if direction == "LONG":
            level = float(lo1[win].min())
            if lo1[m] < level < c1[m]:
                sweep = {"ts": int(ts1[m]), "extreme": float(lo1[m]), "level": level}
                break
        else:
            level = float(hi1[win].max())
            if c1[m] < level < hi1[m]:
                sweep = {"ts": int(ts1[m]), "extreme": float(hi1[m]), "level": level}
                break
    if sweep is None:
        return None

    rng = slice(n1 - B5_RANGE_BARS, n1)
    rng_hi, rng_lo = float(hi1[rng].max()), float(lo1[rng].min())
    eq = (rng_hi + rng_lo) / 2

    df15 = get_data(ctx, symbol, "15m")
    h, l, o, c, v = (df15[k].values for k in ("high", "low", "open", "close", "volume"))
    ts15 = df15["timestamp"].values
    last = len(df15) - 1
    price = float(c[last])
    if (direction == "LONG" and price > eq) or (direction == "SHORT" and price < eq):
        return None

    fvg = None
    for i in range(last - 1, max(2, last - B5_FVG_RECENT) - 1, -1):
        if ts15[i - 1] < sweep["ts"]:
            break
        if direction == "LONG" and h[i - 2] < l[i]:
            bottom, top = float(h[i - 2]), float(l[i])
            if (c[i + 1:last] < bottom).any():
                continue
            if l[last] <= top and c[last] > o[last] and c[last] >= (bottom + top) / 2:
                fvg = {"ts": int(ts15[i])}
                break
        if direction == "SHORT" and l[i - 2] > h[i]:
            bottom, top = float(h[i]), float(l[i - 2])
            if (c[i + 1:last] > top).any():
                continue
            if h[last] >= bottom and c[last] < o[last] and c[last] <= (bottom + top) / 2:
                fvg = {"ts": int(ts15[i])}
                break
    if fvg is None:
        return None

    if direction == "LONG":
        sl = sweep["extreme"] - B5_SL_BUFFER_ATR * atr1
        tp = rng_hi
    else:
        sl = sweep["extreme"] + B5_SL_BUFFER_ATR * atr1
        tp = rng_lo

    def levels(entry):
        if direction == "LONG":
            if not (sl < entry < tp):
                return None
            risk, reward = entry - sl, tp - entry
        else:
            if not (tp < entry < sl):
                return None
            risk, reward = sl - entry, entry - tp
        if risk <= 0 or risk > B5_MAX_RISK_ATR * atr1 or reward / risk < B5_MIN_RR:
            return None
        return sl, tp

    if levels(price) is None:
        print(f"  {symbol}: SMC {direction} rejected (RR/levels)")
        return None
    risk = abs(price - sl)
    if risk / price < MIN_SL_PCT:
        return None
    rr = abs(tp - price) / risk

    depth = abs(sweep["level"] - sweep["extreme"]) / atr1
    vol = float(v[last])
    avg_vol = float(df15["volume"].iloc[-21:-1].mean())
    vol_ratio = ratio(vol, avg_vol)
    score = (0.35 * min(depth / 0.5, 1.0)
             + 0.35 * min(vol_ratio / 2.0, 1.0)
             + 0.30 * min(rr / 3.0, 1.0))
    if score < B5_MIN_SCORE:
        print(f"  {symbol}: SMC score too low ({score:.3f})")
        return None

    rsi = float(df15["rsi"].iloc[-1])
    if np.isnan(rsi):
        rsi = 50.0
    print(f"  {symbol}: SMC {direction} | sweep ok | FVG ok | RR {rr:.2f} | score {score:.3f}")
    return {
        "symbol": symbol, "direction": direction, "close": price,
        "atr": atr1, "rsi": rsi,
        "volume": vol, "avg_volume": avg_vol,
        "signal_key": fvg["ts"], "score": score,
        "setup": "SMC: برداشت نقدینگی و FVG با پولبک",
        "levels": levels,
    }


# =====================================================================
# استراتژی ۶: فیلتر BTC + پولبک هم‌جهت
# =====================================================================
def get_btc_filter(ctx):
    """
    فیلتر ۱: 1D و 4H هم‌جهت (اجباری)
    فیلتر ۲: قدرت روند کافی + عدم گسترش افراطی در 4H
    1H هم‌جهت فقط برای امتیاز بیشتر
    """
    try:
        df_1d = get_data(ctx, BTC_SYMBOL, "1d")
        df_4h = get_data(ctx, BTC_SYMBOL, "4h")
        df_1h = get_data(ctx, BTC_SYMBOL, "1h")
    except Exception as e:
        print(f"⚠️ BTC filter data error: {e}")
        return None

    t_1d = trend_of(df_1d)
    t_4h = trend_of(df_4h)
    t_1h = trend_of(df_1h)

    if t_1d not in ("LONG", "SHORT") or t_4h not in ("LONG", "SHORT"):
        print(f"🌍 BTC filter: no clear bias (1D={t_1d}, 4H={t_4h})")
        return None
    if t_1d != t_4h:
        print(f"🌍 BTC filter: 1D/4H conflict (1D={t_1d}, 4H={t_4h})")
        return None

    bias = t_1d
    last = df_4h.iloc[-1]
    atr = float(last["atr"])
    close = float(last["close"])
    ema9, ema21 = float(last["ema9"]), float(last["ema21"])
    adx = float(last["adx"]) if not np.isnan(last["adx"]) else 0.0

    if np.isnan(atr) or atr <= 0:
        return None

    gap = abs(ema9 - ema21)
    gap_atr = gap / atr
    strength_ok = (gap_atr >= B6_MIN_GAP_ATR) or (adx >= B6_MIN_ADX)
    if not strength_ok:
        print(f"🌍 BTC filter: weak trend (gap={gap_atr:.2f} ATR, ADX={adx:.1f})")
        return None

    ext_atr = abs(close - ema21) / atr
    if ext_atr > B6_MAX_EXT_ATR:
        print(f"🌍 BTC filter: overextended ({ext_atr:.2f} ATR from EMA21)")
        return None

    align_1h = t_1h == bias
    print(f"🌍 BTC filter OK | bias={bias} | 1D={t_1d} 4H={t_4h} 1H={t_1h} "
          f"| gap={gap_atr:.2f} ADX={adx:.1f} ext={ext_atr:.2f} | 1H_align={align_1h}")

    return {
        "bias": bias,
        "t_1d": t_1d,
        "t_4h": t_4h,
        "t_1h": t_1h,
        "align_1h": align_1h,
        "gap_atr": gap_atr,
        "adx": adx,
        "ext_atr": ext_atr,
    }


def analyze_btc_aligned(symbol, ctx):
    btc = getattr(ctx, "btc_filter", None)
    if not btc:
        return None

    bias = btc["bias"]

    df_4h = get_data(ctx, symbol, "4h")
    if trend_of(df_4h) != bias:
        return None

    l4 = df_4h.iloc[-1]
    atr_4h = float(l4["atr"])
    if np.isnan(atr_4h) or atr_4h <= 0:
        return None
    gap_4h = abs(float(l4["ema9"]) - float(l4["ema21"]))
    if gap_4h < B6_ALT_GAP_ATR * atr_4h:
        return None

    df_1h = get_data(ctx, symbol, "1h")
    last = df_1h.iloc[-1]
    close = float(last["close"])
    open_ = float(last["open"])
    high = float(last["high"])
    low = float(last["low"])
    atr = float(last["atr"])
    rsi = float(last["rsi"])
    ema21 = float(last["ema21"])

    if np.isnan(atr) or np.isnan(rsi) or atr <= 0:
        return None

    if bias == "LONG":
        touched = (low <= ema21 + B6_TOUCH_ATR * atr
                   and close > ema21
                   and close > open_
                   and close - ema21 <= B6_MAX_EXT_ALT_ATR * atr)
        rsi_ok = B6_RSI_LONG[0] <= rsi <= B6_RSI_LONG[1]
    else:
        touched = (high >= ema21 - B6_TOUCH_ATR * atr
                   and close < ema21
                   and close < open_
                   and ema21 - close <= B6_MAX_EXT_ALT_ATR * atr)
        rsi_ok = B6_RSI_SHORT[0] <= rsi <= B6_RSI_SHORT[1]

    volume = float(last["volume"])
    avg_volume = float(df_1h["volume"].iloc[-21:-1].mean())
    vol_ratio = ratio(volume, avg_volume)
    vol_ok = vol_ratio >= B6_VOLUME_MULT

    print(f"  {symbol}: BTC={bias} | pullback ok={touched} | RSI {rsi:.1f} ok={rsi_ok} | "
          f"Vol x{vol_ratio:.2f} ok={vol_ok}")

    if not (touched and rsi_ok and vol_ok):
        return None
    if (atr * B6_SL_ATR) / close < MIN_SL_PCT:
        return None

    trend_score = min(gap_4h / atr_4h, 1.2) / 1.2
    vol_score = min(vol_ratio / 2.5, 1.0)
    btc_score = 0.55 + (B6_1H_ALIGN_BONUS if btc["align_1h"] else 0.0)
    btc_score += 0.15 * min(btc["gap_atr"] / 0.6, 1.0)
    score = (0.35 * btc_score
             + 0.30 * trend_score
             + 0.20 * vol_score
             + 0.15 * min(abs(rsi - 50) / 20.0, 1.0))

    if score < B6_MIN_SCORE:
        print(f"  {symbol}: score too low ({score:.3f})")
        return None

    return {
        "symbol": symbol,
        "direction": bias,
        "close": close,
        "atr": atr,
        "rsi": rsi,
        "volume": volume,
        "avg_volume": avg_volume,
        "signal_key": int(last["timestamp"]),
        "score": score,
        "setup": f"BTC-aligned pullback 1H (BTC {bias})",
        "levels": atr_levels(bias, atr, B6_SL_ATR, B6_TP_ATR),
    }


# =====================================================================
# تعریف ربات‌ها
# =====================================================================
class Bot:
    def __init__(self, name, label, analyze, heartbeat_file, signals_file,
                 cooldown_hours=0, max_signals=MAX_SIGNALS_PER_RUN,
                 btc_filter_4h=True, btc_filter_1h=False, live=True):
        self.name = name
        self.label = label
        self.analyze = analyze
        self.heartbeat_file = heartbeat_file
        self.signals_file = signals_file
        self.cooldown_ms = int(cooldown_hours * 3600 * 1000)
        self.max_signals = max_signals
        self.btc_filter_4h = btc_filter_4h
        self.btc_filter_1h = btc_filter_1h
        self.live = live

    @property
    def title_tag(self):
        return f"[{self.name}]" + (f" ({self.label})" if self.label else "")


BOTS = [
    Bot("crypto-signal-bot", "", analyze_cross,
        "server_messages.json", "last_signals.json"),
    Bot("crypto-signal-bot-v10", "Breakout", analyze_breakout,
        "server_messages_v10.json", "last_signals_v10.json"),
    Bot("crypto-signal-bot-v20", "Price Action", analyze_price_action,
        "server_messages_v20.json", "last_signals_v20.json",
        cooldown_hours=B3_COOLDOWN_HOURS),
    Bot("crypto-signal-bot-v40", "Regime", analyze_regime,
        "server_messages_v40.json", "last_signals_v40.json",
        cooldown_hours=B4_COOLDOWN_HOURS, btc_filter_4h=False),
    Bot("crypto-signal-bot-v50", "SMC", analyze_smc,
        "server_messages_v50.json", "last_signals_v50.json",
        cooldown_hours=B5_COOLDOWN_HOURS, live=True),
    Bot("crypto-signal-bot-v60", "BTC Filter", analyze_btc_aligned,
        "server_messages_v60.json", "last_signals_v60.json",
        cooldown_hours=B6_COOLDOWN_HOURS, btc_filter_4h=False),
]
LIVE_BOTS = [b for b in BOTS if b.live]


# =====================================================================
# Heartbeat
# =====================================================================
def send_heartbeat(bot, warning=None):
    date_gregorian, date_jalali, time_str = get_iran_time()
    extra = f"\n⚠️ {warning}" if warning else ""
    msg = f"""🖥️ {bot.title_tag} سرور آنلاین{extra}
━━━━━━━━━━━━━━━━━
📅 تاریخ شمسی: {date_jalali}
📅 تاریخ میلادی: {date_gregorian}
⏰ ساعت: {time_str}
━━━━━━━━━━━━━━━━━"""

    ids = load_json(bot.heartbeat_file, {}).get("message_ids", [])
    new_id = send_telegram(msg)
    if new_id:
        ids.append(new_id)
        while len(ids) > MAX_HEARTBEATS:
            delete_telegram(ids.pop(0))
        save_json(bot.heartbeat_file, {"message_ids": ids})


# =====================================================================
# مدیریت معاملات
# =====================================================================
def check_trade_result(exchange, symbol, data):
    direction, tp, sl = data["direction"], data["tp"], data["sl"]
    opened_ms = data.get("opened_ms")

    if opened_ms:
        try:
            candles = exchange.fetch_ohlcv(symbol, timeframe="5m", since=int(opened_ms), limit=1000)
        except Exception as e:
            print(f"⚠️ خطا در دریافت کندل‌های {symbol}: {e}")
            candles = []
        for cd in candles:
            if cd[0] < opened_ms:
                continue
            high, low = cd[2], cd[3]
            if direction == "LONG":
                hit_sl, hit_tp = low <= sl, high >= tp
            else:
                hit_sl, hit_tp = high >= sl, low <= tp
            if hit_sl:
                return "SL", sl
            if hit_tp:
                return "TP", tp

    price = float(exchange.fetch_ticker(symbol)["last"])
    if direction == "LONG":
        if price <= sl:
            return "SL", price
        if price >= tp:
            return "TP", price
    else:
        if price >= sl:
            return "SL", price
        if price <= tp:
            return "TP", price
    return None, None


def trade_r(rec):
    if rec.get("status") != "CLOSED":
        return None
    risk = abs(rec["entry"] - rec["sl"])
    if risk <= 0:
        return None
    return abs(rec["tp"] - rec["entry"]) / risk if rec.get("result") == "TP" else -1.0


def build_close_message(bot, symbol, direction, result, close_price, entry):
    date_gregorian, date_jalali, time_str = get_iran_time()
    emoji = "🎯" if result == "TP" else "🛑"
    title = "حد سود (TP) لمس شد" if result == "TP" else "حد ضرر (SL) لمس شد"
    return f"""{emoji} {bot.title_tag} بسته شدن معامله
━━━━━━━━━━━━━━━━━
📌 نماد: {symbol}
📊 جهت: {direction}
🏁 نتیجه: {title}
💰 قیمت بسته شدن: {format_number(close_price)}
🚪 قیمت ورود: {format_number(entry)}
━━━━━━━━━━━━━━━━━
📅 تاریخ شمسی: {date_jalali}
📅 تاریخ میلادی: {date_gregorian}
⏰ ساعت: {time_str}
━━━━━━━━━━━━━━━━━"""


CLOSE_MSG_MAX_ATTEMPTS = 5


def update_open_trades(bot, exchange):
    signals = load_json(bot.signals_file, {})
    updated = False

    for symbol, data in list(signals.items()):
        if data.get("status") == "OPEN":
            try:
                result, close_price = check_trade_result(exchange, symbol, data)
            except Exception as e:
                print(f"⚠️ خطا در بررسی {symbol}: {e}")
                continue
            if result:
                data["status"] = "CLOSED"
                data["result"] = result
                data["closed_ms"] = now_ms()
                data["close_price"] = float(close_price)
                data["close_telegram_sent"] = False
                data["close_msg_attempts"] = 0
                updated = True
                print(f"{'🎯' if result == 'TP' else '🛑'} {symbol} {data['direction']} hit {result} at {close_price}")

        if (data.get("status") == "CLOSED" and data.get("close_telegram_sent") is False
                and data.get("close_msg_attempts", 0) < CLOSE_MSG_MAX_ATTEMPTS):
            msg_id = send_telegram(build_close_message(
                bot, symbol, data["direction"], data["result"], data["close_price"], data["entry"]))
            data["close_msg_attempts"] = data.get("close_msg_attempts", 0) + 1
            data["close_telegram_sent"] = bool(msg_id)
            updated = True
            if not msg_id:
                print(f"⚠️ {symbol}: پیام بسته شدن ارسال نشد (تلاش {data['close_msg_attempts']})")

    if updated:
        save_json(bot.signals_file, signals)


def build_signal_message(bot, c, entry, sl, tp, rr):
    date_gregorian, date_jalali, time_str = get_iran_time()
    emoji = "🟢" if c["direction"] == "LONG" else "🔴"
    return f"""{emoji} {bot.title_tag} سیگنال {c['direction']}
━━━━━━━━━━━━━━━━━
📌 نماد: {c['symbol']}
🔎 ستاپ: {c['setup']}
💰 قیمت ورود: {format_number(entry)}
🎯 حد سود (TP): {format_number(tp)}
🛑 حد ضرر (SL): {format_number(sl)}
📊 نسبت R:R: 1:{rr:.1f}
📈 RSI: {c['rsi']:.2f}
📉 ATR: {format_number(c['atr'])}
📊 Volume: {c['volume']:.2f} (Avg: {c['avg_volume']:.2f})
━━━━━━━━━━━━━━━━━
📅 تاریخ شمسی: {date_jalali}
📅 تاریخ میلادی: {date_gregorian}
⏰ ساعت: {time_str}
━━━━━━━━━━━━━━━━━"""


# =====================================================================
# چرخه‌ی یک ربات
# =====================================================================
def run_bot(bot, ctx, btc_4h, btc_1h):
    print("=" * 50)
    print(f"▶ {bot.name} {('(' + bot.label + ')') if bot.label else ''}")

    update_open_trades(bot, ctx.exchange)
    signals = load_json(bot.signals_file, {})

    candidates = []
    t_now = now_ms()
    for symbol in SYMBOLS:
        try:
            prev = signals.get(symbol)
            if prev and prev.get("status") == "OPEN":
                print(f"⏳ {symbol} has an OPEN trade. Skipping.")
                continue
            if (prev and bot.cooldown_ms and prev.get("closed_ms")
                    and t_now - prev["closed_ms"] < bot.cooldown_ms):
                print(f"❄️ {symbol} in cooldown. Skipping.")
                continue

            c = bot.analyze(symbol, ctx)
            if c is None:
                continue

            prev_key = (prev.get("signal_key", prev.get("cross_ts")) if prev else None)
            if prev and prev_key == c["signal_key"] and prev.get("direction") == c["direction"]:
                print(f"♻️ {symbol} {c['direction']}: this setup was already signaled. Skipping.")
                continue

            if symbol != BTC_SYMBOL:
                if bot.btc_filter_4h and btc_4h in ("LONG", "SHORT") and c["direction"] != btc_4h:
                    print(f"🚫 {symbol} {c['direction']} rejected. BTC 4H trend is {btc_4h}.")
                    continue
                if bot.btc_filter_1h and btc_1h in ("LONG", "SHORT") and c["direction"] != btc_1h:
                    print(f"🚫 {symbol} {c['direction']} rejected. BTC 1H trend is {btc_1h}.")
                    continue

            candidates.append(c)
            print(f"✅ Candidate: {symbol} {c['direction']} score={c['score']:.3f}")
        except Exception as e:
            print(f"⚠️ خطا در {symbol}: {e}")
            continue

    candidates.sort(key=lambda x: x["score"], reverse=True)
    print(f"📋 {len(candidates)} candidate(s): " +
          ", ".join(f"{c['symbol']}({c['score']:.2f})" for c in candidates))

    sent = 0
    for c in candidates:
        if sent >= bot.max_signals:
            break
        symbol = c["symbol"]
        try:
            entry = get_price(ctx, symbol)
            if abs(entry - c["close"]) > c["atr"] * MAX_ENTRY_DRIFT_ATR:
                print(f"⌛ {symbol}: price drifted too far from signal candle. Skipping.")
                continue

            lv = c["levels"](entry)
            if lv is None:
                print(f"⚠️ {symbol}: price already beyond stop level. Skipping.")
                continue
            sl, tp = lv
            if sl <= 0 or tp <= 0:
                print(f"⚠️ {symbol}: invalid SL/TP. Skipping.")
                continue
            rr = abs(tp - entry) / abs(entry - sl)

            msg_id = send_telegram(build_signal_message(bot, c, entry, sl, tp, rr))

            record = {
                "direction": c["direction"], "entry": entry, "tp": tp, "sl": sl,
                "signal_key": c["signal_key"], "setup": c["setup"],
                "score": round(c["score"], 4),
                "time": datetime.now(timezone.utc).isoformat(),
                "telegram_sent": bool(msg_id), "telegram_message_id": msg_id,
            }
            if msg_id:
                record["status"] = "OPEN"
                record["opened_ms"] = now_ms()
                sent += 1
                print(f"✅ {c['direction']} signal for {symbol} sent! ({sent}/{bot.max_signals})")
            else:
                record["status"] = "NOT_SENT"
                print(f"⚠️ {symbol}: پیام تلگرام ارسال نشد؛ معامله ثبت نشد (NOT_SENT).")
            signals[symbol] = record
            save_json(bot.signals_file, signals)
        except Exception as e:
            print(f"⚠️ خطا در ارسال {symbol}: {e}")
            continue

    print(f"{bot.name}: analysis complete ({sent} signal(s) sent).")


# =====================================================================
# خلاصه‌ی روزانه (ساعت ۸ صبح ایران)
# =====================================================================
def maybe_send_daily_summary():
    now = datetime.now(ZoneInfo("Asia/Tehran"))
    today = now.strftime("%Y-%m-%d")
    state = load_json(SUMMARY_FILE, {})
    if now.hour < SUMMARY_HOUR or state.get("date") == today:
        return

    date_gregorian, date_jalali, time_str = get_iran_time()
    lines = []
    for bot in LIVE_BOTS:
        recs = list(load_json(bot.signals_file, {}).values())
        closed = [r for r in recs if r.get("status") == "CLOSED"]
        opened = [r for r in recs if r.get("status") == "OPEN"]
        rs = [x for x in (trade_r(r) for r in closed) if x is not None]
        if rs:
            wins = sum(1 for r in closed if r.get("result") == "TP")
            lines.append(f"🤖 {bot.name}\n"
                         f"   بسته‌شده: {len(rs)} | برد: {wins} ({wins / len(rs):.0%}) | "
                         f"R کل: {sum(rs):+.1f} | میانگین R: {sum(rs) / len(rs):+.2f}\n"
                         f"   باز: {len(opened)}")
        else:
            lines.append(f"🤖 {bot.name}\n   هنوز معامله‌ی بسته‌شده‌ای نیست | باز: {len(opened)}")

    msg = ("📊 خلاصه‌ی روزانه‌ی ربات‌ها\n━━━━━━━━━━━━━━━━━\n" + "\n".join(lines) +
           f"\n━━━━━━━━━━━━━━━━━\n📅 تاریخ شمسی: {date_jalali}\n📅 تاریخ میلادی: {date_gregorian}\n"
           f"⏰ ساعت: {time_str}\n━━━━━━━━━━━━━━━━━")
    if send_telegram(msg):
        save_json(SUMMARY_FILE, {"date": today})


# =====================================================================
# اجرای اصلی
# =====================================================================
if __name__ == "__main__":
    print("=" * 50)
    print("Starting multi-bot cycle (Quality Mode): " + ", ".join(b.name for b in LIVE_BOTS))

    exchange = create_exchange()
    ctx = Ctx(exchange)

    btc_4h, btc_1h = get_btc_trend(ctx)
    print(f"🌍 BTC 4H Trend: {btc_4h} | BTC 1H Trend: {btc_1h}")
    warning = "دریافت داده‌ی BTC ناموفق بود" if btc_4h == "UNKNOWN" else None

    ctx.btc_filter = get_btc_filter(ctx)
    if not ctx.btc_filter:
        print("🌍 BTC filter blocked — v60 will skip all symbols this cycle.")

    for bot in LIVE_BOTS:
        send_heartbeat(bot, warning)
    print("✅ Heartbeats sent.")

    for bot in LIVE_BOTS:
        try:
            run_bot(bot, ctx, btc_4h, btc_1h)
        except Exception as e:
            print(f"⚠️ خطای کلی در {bot.name}: {e}")

    try:
        maybe_send_daily_summary()
    except Exception as e:
        print(f"⚠️ خطا در خلاصه‌ی روزانه: {e}")

    print("All bots complete.")
    print("=" * 50)