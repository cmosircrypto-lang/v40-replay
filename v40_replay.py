"""
بازپخش معاملات زنده‌ی V40 روی کندل‌های واقعی Toobit با SL و TP بر حسب ATR.

ورودی‌ها (کنار هم در یک پوشه):
  main.py          نسخه‌ی ریپو (برای calculate_indicators و create_exchange)
  v40_trades.csv   معاملات زنده (زمان ورود به وقت ایران)

منطق:
  - ATR هر معامله از آخرین کندل ۱ساعته‌ی بسته‌شده قبل از ورود محاسبه می‌شود (همان روش ربات).
  - برای هر ترکیب SL و TP (بر حسب ATR)، از زمان ورود روی کندل‌های ۵دقیقه‌ای جلو می‌رویم.
    اگر در یک کندل هم SL و هم TP لمس شوند، SL فرض می‌شود (محافظه‌کارانه).
  - R هر معامله: TP = |tp-entry|/|entry-sl| ، SL = -1 ، و کارمزد رفت‌وبرگشت از R کم می‌شود.
  - اعتبارسنجی: با سطوح واقعی خود فایل (بدون ATR) بازپخش می‌شود تا با نتیجه‌ی ثبت‌شده مقایسه شود.

اجرا (در GitHub Actions یا هر جایی که Toobit در دسترس است):
  python v40_replay.py
"""
import csv
import datetime as dt
import os
from zoneinfo import ZoneInfo

import pandas as pd

import main as M

IRAN = ZoneInfo("Asia/Tehran")
CSV_PATH = os.environ.get("V40_CSV", "v40_trades.csv")
OUT_TRADES = os.environ.get("V40_OUT", "v40_replay_trades.csv")
FEE = float(os.environ.get("BT_FEE", "0.0006"))
H1 = M.TF_MS["1h"]
M5 = M.TF_MS["5m"]
MAX_HOLD_MS = 4 * 24 * H1          # حداکثر نگه‌داشتن: ۴ روز
SL_GRID = [1.0, 1.2, 1.5, 2.0]
TP_GRID = [2.0, 2.5, 3.0, 3.5]


def to_ms(text):
    d = dt.datetime.fromisoformat(text).replace(tzinfo=IRAN)
    return int(d.timestamp() * 1000)


def fetch_all(ex, symbol, tf, since, until):
    """کندل‌ها را صفحه‌صفحه می‌گیرد؛ تکراری‌ها حذف می‌شوند."""
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
    cols = ["timestamp", "open", "high", "low", "close", "volume"]
    df = pd.DataFrame(sorted(got.values()), columns=cols)
    return df.reset_index(drop=True)


def atr_at(ex, symbol, entry_ms):
    """ATR ۱ساعته‌ی آخرین کندل بسته‌شده قبل از ورود (همان تعریف ربات)."""
    h1 = fetch_all(ex, symbol, "1h", entry_ms - 400 * H1, entry_ms + H1)
    if len(h1) < 60:
        return None
    h1 = M.calculate_indicators(h1)
    closed = h1[h1["timestamp"] + H1 <= entry_ms]
    if closed.empty:
        return None
    atr = float(closed.iloc[-1]["atr"])
    return atr if atr > 0 else None


BTC = M.BTC_SYMBOL


def btc_trend_at(ex, entry_ms):
    """
    روند BTC ۴ساعته در لحظه‌ی ورود (همان قاعده‌ی trend_of ربات:
    EMA9 بالاتر از EMA21 یعنی LONG، پایین‌تر یعنی SHORT) روی آخرین کندل ۴ساعته‌ی بسته‌شده.
    """
    h4 = M.TF_MS["4h"]
    df = fetch_all(ex, BTC, "4h", entry_ms - 120 * h4, entry_ms + h4)
    if len(df) < 60:
        return "UNKNOWN"
    df = M.calculate_indicators(df)
    closed = df[df["timestamp"] + h4 <= entry_ms]
    if closed.empty:
        return "UNKNOWN"
    last = closed.iloc[-1]
    if last["ema9"] > last["ema21"]:
        return "LONG"
    if last["ema9"] < last["ema21"]:
        return "SHORT"
    return "NONE"


def simulate(direction, entry, sl, tp, path):
    """
    path: کندل‌های ۵دقیقه‌ای از ورود به بعد.
    برمی‌گرداند (نتیجه, R خالص).
    """
    risk = abs(entry - sl)
    if risk <= 0:
        return "BAD", None
    fee_r = 2 * FEE * entry / risk
    for c in path.itertuples(index=False):
        if direction == "LONG":
            hit_sl, hit_tp = c.low <= sl, c.high >= tp
        else:
            hit_sl, hit_tp = c.high >= sl, c.low <= tp
        if hit_sl:                       # SL اول: محافظه‌کارانه
            return "SL", -1.0 - fee_r
        if hit_tp:
            return "TP", abs(tp - entry) / risk - fee_r
    if len(path) == 0:
        return "NO_DATA", None
    last = float(path["close"].iloc[-1])
    move = (last - entry) if direction == "LONG" else (entry - last)
    return "TIMEOUT", move / risk - fee_r


def summarize(label, outcomes):
    rs = [r for _, r in outcomes if r is not None]
    n = len(rs)
    if n == 0:
        print(f"{label}: بدون داده")
        return
    tp = sum(1 for k, _ in outcomes if k == "TP")
    sl = sum(1 for k, _ in outcomes if k == "SL")
    to = sum(1 for k, _ in outcomes if k == "TIMEOUT")
    print(f"{label:<14} n={n:<4} TP={tp:<3} SL={sl:<3} TIMEOUT={to:<3} "
          f"برد={tp / n:5.1%}  R کل={sum(rs):+8.1f}  میانگین R={sum(rs) / n:+.3f}")


def run_grid(label, sel, detail):
    for sl_m in SL_GRID:
        for tp_m in TP_GRID:
            outcomes = []
            for p in sel:
                a = p["atr"]
                if p["dir"] == "LONG":
                    sl, tp = p["entry"] - sl_m * a, p["entry"] + tp_m * a
                else:
                    sl, tp = p["entry"] + sl_m * a, p["entry"] - tp_m * a
                k, r = simulate(p["dir"], p["entry"], sl, tp, p["path"])
                outcomes.append((k, r))
                detail.append({"mode": label, "symbol": p["sym"], "entry_time": p["row"]["entry_time_iran"],
                               "direction": p["dir"], "btc_4h": p["btc"], "sl_atr": sl_m, "tp_atr": tp_m,
                               "result": k, "R": "" if r is None else round(r, 4)})
            tag = "  <- قبلی" if (sl_m, tp_m) == (1.2, 3.0) else ""
            summarize(f"SL {sl_m:.1f} / TP {tp_m:.1f}{tag}", outcomes)


def main_run():
    ex = M.create_exchange()
    with open(CSV_PATH, encoding="utf-8") as fh:
        rows = [r for r in csv.DictReader(fh) if r["status"] in ("TP", "SL")]
    print(f"معاملات بسته‌شده‌ی قابل بازپخش: {len(rows)}")

    prepared = []
    skipped = []
    for r in rows:
        sym = r["symbol"]
        entry = float(r["entry"])
        tp_rec = float(r["tp"])
        sl_rec = float(r["sl"])
        direction = r["direction"]
        ems = to_ms(r["entry_time_iran"])
        try:
            atr = atr_at(ex, sym, ems)
            path = fetch_all(ex, sym, "5m", ems, ems + MAX_HOLD_MS)
            path = path[path["timestamp"] + M5 > ems].reset_index(drop=True)
        except Exception as e:
            skipped.append((sym, r["entry_time_iran"], f"خطای داده: {e}"))
            continue
        if atr is None or len(path) == 0:
            skipped.append((sym, r["entry_time_iran"], "ATR یا کندل ۵دقیقه‌ای نبود"))
            continue
        try:
            btc = btc_trend_at(ex, ems)
        except Exception:
            btc = "UNKNOWN"
        prepared.append({"row": r, "sym": sym, "entry": entry, "dir": direction,
                         "tp_rec": tp_rec, "sl_rec": sl_rec, "rec_status": r["status"],
                         "atr": atr, "path": path, "ems": ems, "btc": btc})

    print(f"قابل بازپخش: {len(prepared)} | کنار گذاشته‌شده: {len(skipped)}")
    for s_ in skipped[:10]:
        print("  skip:", s_)

    # ---- اعتبارسنجی ۱: ATR
    ratios = []
    for p in prepared:
        rec_risk = abs(p["entry"] - p["sl_rec"])
        if rec_risk <= 0:
            continue
        implied = ((p["tp_rec"] - p["entry"]) if p["dir"] == "LONG" else (p["entry"] - p["tp_rec"])) / 3.0
        if implied > 0 and abs(abs(p["tp_rec"] - p["entry"]) / rec_risk - 2.5) < 0.05:
            ratios.append(p["atr"] / implied)
    if ratios:
        ratios.sort()
        print(f"اعتبارسنجی ATR (فقط معاملات روند): نسبت میانه = {ratios[len(ratios) // 2]:.3f} "
              f"(باید نزدیک ۱ باشد) | تعداد = {len(ratios)}")

    # ---- اعتبارسنجی ۲: بازپخش با سطوح واقعی
    rec_out = []
    match = 0
    for p in prepared:
        k, r = simulate(p["dir"], p["entry"], p["sl_rec"], p["tp_rec"], p["path"])
        rec_out.append((k, r))
        if k == p["rec_status"]:
            match += 1
    print(f"اعتبارسنجی بازپخش با سطوح واقعی: {match}/{len(prepared)} هم‌خوان با نتیجه‌ی ثبت‌شده")
    summarize("سطوح واقعی", rec_out)

    detail = []
    filt = [p for p in prepared if p["btc"] in ("LONG", "SHORT") and p["btc"] == p["dir"]]
    print("=" * 110)
    print(f"بدون فیلتر BTC: {len(prepared)} معامله")
    run_grid("no_filter", prepared, detail)
    print("=" * 110)
    print(f"با فیلتر BTC ۴ساعته (فقط جهت هم‌راستا با روند BTC): {len(filt)} معامله از {len(prepared)}")
    run_grid("btc4h_filter", filt, detail)

    with open(OUT_TRADES, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(detail[0].keys()))
        w.writeheader()
        w.writerows(detail)
    print(f"جزئیات هر معامله در {OUT_TRADES} ذخیره شد.")


if __name__ == "__main__":
    main_run()
