"""
بک‌تست ربات AMD (قواعد ثبت‌شده‌ی قبل از تست؛ پارامترها برای بهتر شدن نتیجه تغییر نمی‌کنند)

  Accumulation : بازه‌ی آسیا، کندل‌های ۱ساعته ساعت ۰۰ تا ۰۶ UTC  (سقف AH و کف AL)
  فیلتر روز    : رنج آسیا بین ۰.۵ تا ۲ ATR روزانه‌ی روز قبل
  Manipulation : ساعت ۰۷ تا ۰۹ UTC، کندلی که از AH یا AL رد شود و داخل بازه بسته شود (sweep)
  Distribution : کندل جابه‌جایی مخالف با بدنه ≥ ۰.۸ ATR در ۴ کندل بعدی، با FVG بین سه کندل
                 ورود روی وسط FVG وقتی پولبک بخورد؛ ابطال اگر کندل بسته‌شدن را از FVG رد کند
  SL           : پشت فتیله‌ی sweep + ۰.۱ ATR
  TP           : لبه‌ی مقابل بازه‌ی آسیا
  فیلتر معامله : R:R ≥ ۱.۵ و ریسک ≤ ۳ ATR؛ هر نماد حداکثر یک ستاپ در روز

معیار پذیرش (از قبل):
  - حداقل ۵۰ معامله‌ی بسته‌شده
  - میانگین R مثبت
  - مثبت بودن R در هر دو نیمه‌ی بازه (بر اساس زمان ورود)

اجرا: کنار main.py ریپو، با GitHub Actions (Toobit در دسترس است).
"""
import csv
import os
import statistics as st

import main as M

FEE = float(os.environ.get("BT_FEE", "0.0006"))
DAYS = int(os.environ.get("AMD_DAYS", "100"))
H1 = M.TF_MS["1h"]
M5 = M.TF_MS["5m"]
D1 = M.TF_MS["1d"]

ASIA_START_H, ASIA_END_H = 0, 7        # [0, 7) UTC
SWEEP_HOURS = (7, 8, 9)                 # ساعت شروع کندل sweep
DISP_MAX_AFTER_SWEEP = 4
DISP_BODY_ATR = 0.8
SL_BUFFER_ATR = 0.1
MIN_RR = 1.5
MAX_RISK_ATR = 3.0
RANGE_MIN_D1_ATR = 0.5
RANGE_MAX_D1_ATR = 2.0
MAX_HOLD_MS = 24 * H1
EXCHANGE = os.environ.get("AMD_EXCHANGE", "binanceusdm")   # binanceusdm | bybit | okx | toobit
OUT_TRADES = os.environ.get("AMD_OUT", "amd_trades.csv")
OUT_SUMMARY = os.environ.get("AMD_SUMMARY", "amd_summary.txt")


def make_exchange():
    """منبع داده: Toobit (همان ربات) یا صرافی عمومی با تاریخچه‌ی طولانی‌تر."""
    if EXCHANGE == "toobit":
        return M.create_exchange()
    import ccxt
    ex = getattr(ccxt, EXCHANGE)({"enableRateLimit": True})
    ex.load_markets()
    return ex


def to_ccxt_symbol(ex, sym):
    """BTC-SWAP-USDT  ->  BTC/USDT:USDT  (None اگر در صرافی نباشد)."""
    if EXCHANGE == "toobit":
        return sym
    base = sym.split("-")[0]
    cand = f"{base}/USDT:USDT"
    return cand if cand in ex.markets else None


def fetch_all(ex, symbol, tf, since, until):
    step = M.TF_MS[tf]
    got = {}
    cur = since
    while cur < until:
        batch = ex.fetch_ohlcv(symbol, timeframe=tf, since=cur, limit=1000)
        if not batch:
            break
        for b in batch:
            if since <= b[0] < until:
                got[b[0]] = b
        nxt = batch[-1][0] + step
        if nxt <= cur:
            break
        cur = nxt
    return [got[k] for k in sorted(got)]


def to_rows(raw):
    """لیست کندل‌ها (ts, o, h, l, c, v) را به دیکشنری‌های ساده تبدیل می‌کند."""
    return [{"ts": int(b[0]), "o": float(b[1]), "h": float(b[2]), "l": float(b[3]),
             "c": float(b[4]), "v": float(b[5])} for b in raw]


def simulate(direction, entry, sl, tp, path):
    risk = abs(entry - sl)
    fee_r = 2 * FEE * entry / risk
    for c in path:
        if direction == "LONG":
            hit_sl, hit_tp = c["l"] <= sl, c["h"] >= tp
        else:
            hit_sl, hit_tp = c["h"] >= sl, c["l"] <= tp
        if hit_sl:
            return "SL", -1.0 - fee_r
        if hit_tp:
            return "TP", abs(tp - entry) / risk - fee_r
    if not path:
        return "NO_DATA", None
    last = path[-1]["c"]
    move = (last - entry) if direction == "LONG" else (entry - last)
    return "TIMEOUT", move / risk - fee_r


def atr_series(rows):
    """ATR ۱۴ (Wilder) روی کندل‌های بالا با همان تابع ربات."""
    import pandas as pd
    df = pd.DataFrame(rows)[["ts", "o", "h", "l", "c", "v"]]
    df.columns = ["timestamp", "open", "high", "low", "close", "volume"]
    df = M.calculate_indicators(df)
    return df["atr"].tolist()


def detect_setup(h1, atr1, d1_rows, d1_atr, s):
    """
    s: شروع روز UTC. h1: کندل‌های ۱ساعته (لیست مرتب). برمی‌گرداند dict ستاپ یا None.
    """
    idx = {r["ts"]: i for i, r in enumerate(h1)}

    def at(hour):
        return idx.get(s + hour * H1)

    asia_idx = [at(hh) for hh in range(ASIA_START_H, ASIA_END_H)]
    if any(i is None for i in asia_idx):
        return None
    asia = [h1[i] for i in asia_idx]
    AH = max(r["h"] for r in asia)
    AL = min(r["l"] for r in asia)
    if AH <= AL:
        return None

    # ATR روزانه‌ی روز قبل (فقط کندل بسته‌شده)
    prev = [i for i, r in enumerate(d1_rows) if r["ts"] + D1 <= s]
    if not prev:
        return None
    atr_d = d1_atr[prev[-1]]
    if not atr_d or atr_d <= 0:
        return None
    rng = AH - AL
    if not (RANGE_MIN_D1_ATR * atr_d <= rng <= RANGE_MAX_D1_ATR * atr_d):
        return None

    ref_i = at(ASIA_END_H - 1)
    atr_ref = atr1[ref_i] if ref_i is not None else None
    if not atr_ref or atr_ref <= 0:
        return None

    # ۱) sweep
    sweep_i = None
    direction = None
    ext = None
    for hh in SWEEP_HOURS:
        i = at(hh)
        if i is None:
            continue
        r = h1[i]
        bear = r["h"] > AH and r["c"] < AH
        bull = r["l"] < AL and r["c"] > AL
        if bear and bull:
            continue            # کندل مبهم
        if bear:
            direction, ext, sweep_i = "SHORT", r["h"], i
            break
        if bull:
            direction, ext, sweep_i = "LONG", r["l"], i
            break
    if sweep_i is None:
        return None

    # ۲) جابه‌جایی و FVG
    for k in range(sweep_i + 1, min(sweep_i + 1 + DISP_MAX_AFTER_SWEEP, len(h1) - 1)):
        disp = h1[k]
        body = abs(disp["c"] - disp["o"])
        if body < DISP_BODY_ATR * atr_ref:
            continue
        A, C = h1[k - 1], h1[k + 1]
        if direction == "SHORT":
            if not (disp["c"] < disp["o"] and A["l"] > C["h"]):
                continue
            zone_lo, zone_hi = C["h"], A["l"]
        else:
            if not (disp["c"] > disp["o"] and A["h"] < C["l"]):
                continue
            zone_lo, zone_hi = A["h"], C["l"]
        mid = (zone_lo + zone_hi) / 2

        # ۳) پولبک به وسط FVG (بعد از کندل C)
        entry_i = None
        for j in range(k + 2, len(h1)):
            r = h1[j]
            if h1[j]["ts"] - h1[sweep_i]["ts"] > 24 * H1:
                break
            if direction == "SHORT":
                if r["c"] > zone_hi:
                    break       # ابطال
                if r["h"] >= mid:
                    entry_i = j
                    break
            else:
                if r["c"] < zone_lo:
                    break
                if r["l"] <= mid:
                    entry_i = j
                    break
        if entry_i is None:
            return None         # این FVG پر نشد؛ ستاپ امروز کنار گذاشته می‌شود

        entry = mid
        if direction == "SHORT":
            sl = ext + SL_BUFFER_ATR * atr_ref
            tp = AL
            risk, reward = sl - entry, entry - tp
            ok = tp < entry < sl
        else:
            sl = ext - SL_BUFFER_ATR * atr_ref
            tp = AH
            risk, reward = entry - sl, tp - entry
            ok = sl < entry < tp
        if not ok or risk <= 0 or risk > MAX_RISK_ATR * atr_ref:
            return None
        rr = reward / risk
        if rr < MIN_RR:
            return None
        return {"direction": direction, "entry": entry, "sl": sl, "tp": tp, "rr": rr,
                "entry_ms": h1[entry_i]["ts"], "AH": AH, "AL": AL, "atr_ref": atr_ref,
                "sweep_ms": h1[sweep_i]["ts"]}
    return None


def run():
    ex = make_exchange()
    print(f"منبع داده: {EXCHANGE}")
    until = int(__import__("time").time() * 1000) // H1 * H1
    since = until - DAYS * 24 * H1
    trades = []
    errors = []
    for sym in M.SYMBOLS:
        csym = to_ccxt_symbol(ex, sym)
        if csym is None:
            print(f"skip {sym}: در {EXCHANGE} نیست")
            continue
        try:
            h1_raw = fetch_all(ex, csym, "1h", since - 24 * H1, until)
            d1_raw = fetch_all(ex, csym, "1d", since - 60 * D1, until)
        except Exception as e:
            errors.append(str(e)[:200])
            print(f"skip {sym}: {e}")
            continue
        if len(h1_raw) < 200 or len(d1_raw) < 30:
            print(f"skip {sym}: داده‌ی کم")
            continue
        h1 = to_rows(h1_raw)
        d1 = to_rows(d1_raw)
        atr1 = atr_series(h1)
        d1_atr = atr_series(d1)
        days = sorted({(r["ts"] // D1) * D1 for r in h1 if r["ts"] >= since})
        last_entry_day = None
        for s in days:
            # محدود کردن: پنجره‌ی جهت‌دار هر روز؛ هر روز حداکثر یک ستاپ
            setup = detect_setup(h1, atr1, d1, d1_atr, s)
            if setup is None:
                continue
            path = fetch_all(ex, csym, "5m", setup["entry_ms"] + H1, setup["entry_ms"] + H1 + MAX_HOLD_MS)
            path_tf = "5m"
            if not path:            # تاریخچه‌ی ۵دقیقه‌ای کوتاه است؛ برای ستاپ‌های قدیمی‌تر از ۱ساعته استفاده می‌شود
                path = fetch_all(ex, csym, "1h", setup["entry_ms"] + H1, setup["entry_ms"] + H1 + MAX_HOLD_MS)
                path_tf = "1h"
            path = [to_rows([b])[0] for b in path]
            res, R = simulate(setup["direction"], setup["entry"], setup["sl"], setup["tp"], path)
            trades.append({"symbol": sym, "day_utc": s, "entry_ms": setup["entry_ms"],
                           "direction": setup["direction"], "entry": setup["entry"],
                           "sl": setup["sl"], "tp": setup["tp"], "rr": round(setup["rr"], 3),
                           "result": res, "R": "" if R is None else round(R, 4), "path_tf": path_tf})
        print(f"{sym}: روزها {len(days)}")

    if not trades:
        print("هیچ ستاپی پیدا نشد.")
        if errors:
            print("نمونه‌ی خطا:", errors[0])
        return
    with open(OUT_TRADES, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(trades[0].keys()))
        w.writeheader()
        w.writerows(trades)
    summary(trades)


def summary(trades):
    lines = []
    closed = [t for t in trades if t["result"] in ("TP", "SL") and t["R"] != ""]
    n = len(closed)
    tpn = sum(1 for t in closed if t["result"] == "TP")
    Rs = [float(t["R"]) for t in closed]
    src5 = sum(1 for t in trades if t.get("path_tf") == "5m")
    lines.append(f"مسیر خروج: ۵دقیقه‌ای {src5} | ۱ساعته {len(trades) - src5}")
    lines.append(f"کل ستاپ‌ها: {len(trades)} | بسته‌شده: {n} | TIMEOUT: "
                 f"{sum(1 for t in trades if t['result'] == 'TIMEOUT')}")
    if n:
        lines.append(f"برد: {tpn / n:.1%} | R کل: {sum(Rs):+.1f} | میانگین R: {sum(Rs) / n:+.3f}")
        for d in ("LONG", "SHORT"):
            sub = [float(t["R"]) for t in closed if t["direction"] == d]
            if sub:
                lines.append(f"  {d}: {len(sub)} معامله | R {sum(sub):+.1f} | میانگین {sum(sub) / len(sub):+.3f}")
        times = sorted(t["entry_ms"] for t in closed)
        mid = times[len(times) // 2]
        h1r = [float(t["R"]) for t in closed if t["entry_ms"] < mid]
        h2r = [float(t["R"]) for t in closed if t["entry_ms"] >= mid]
        lines.append(f"نیمه‌ی اول: {len(h1r)} معامله | R {sum(h1r):+.1f}")
        lines.append(f"نیمه‌ی دوم: {len(h2r)} معامله | R {sum(h2r):+.1f}")
    ok_n = n >= 50
    ok_avg = n > 0 and sum(Rs) / n > 0
    ok_halves = bool(n) and sum(h1r) > 0 and sum(h2r) > 0
    verdict = "PASS" if (ok_n and ok_avg and ok_halves) else "FAIL"
    lines.append(f"معیار از قبل: n≥50 [{ok_n}] | میانگین R>0 [{ok_avg}] | هر دو نیمه مثبت [{ok_halves}]")
    lines.append(f"نتیجه: {verdict}")
    text = "\n".join(lines)
    print(text)
    with open(OUT_SUMMARY, "w", encoding="utf-8") as fh:
        fh.write(text + "\n")


if __name__ == "__main__":
    run()
