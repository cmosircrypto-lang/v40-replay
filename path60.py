"""
مسیر قیمت بعد از صدور هر سیگنال (کندل ۵ دقیقه‌ای توبیت، ۶۰ دقیقه‌ی اول).
برای هر معامله: کدام اول خورد، TP یا SL، در چه دقیقه‌ای؛ بیشترین حرکت به سمت TP قبل از SL؛
و اگر اول به TP رفته و بعد SL خورده، چند دقیقه بعد.
قواعد: ورود = قیمت سیگنال. کندل‌های کامل بعد از زمان سیگنال (کندل جاری ناقص حذف می‌شود).
اگر TP و SL در یک کندل خورده باشند، SL محافظه‌کارانه اول حساب می‌شود و برچسب SAME_BAR می‌گیرد.
"""
import glob
import os
import csv
import statistics as st
from datetime import timedelta

IRAN = timedelta(hours=3, minutes=30)
BAR_MS = 300000
MIN_MS = 60000
HORIZON_MIN = 60
VERSIONS = [("V10", "*V10*.xlsx"), ("V20", "*V20*.xlsx"), ("V30", "*V30*.xlsx"), ("V40", "*V40*.xlsx"),
            ("V50", "*V50*.xlsx"), ("V60", "*V60*.xlsx"), ("Blank", "*Blank*.xlsx")]
DETAIL_BASES = ["SOL"]
MIN_SYM_N = 5
BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def find_file(pattern):
    m = glob.glob(os.path.join(BASE_DIR, pattern))
    if len(m) != 1:
        raise SystemExit(f"الگوی {pattern} باید دقیقاً یک فایل داشته باشد؛ پیدا شد: {m}")
    return m[0]


def load_trades(path, version):
    import openpyxl
    ws = openpyxl.load_workbook(path, data_only=True, read_only=True).worksheets[0]
    rows = list(ws.iter_rows(values_only=True))
    hi = next(i for i, r in enumerate(rows) if r and r[0] == "نماد")
    out = []
    for r in rows[hi + 1:]:
        if not r or r[0] in (None, ""):
            continue
        sym, _date, t, d, e, tp, sl, res = r[:8]
        d = str(d or "").upper()
        try:
            e, tp, sl = float(e), float(tp), float(sl)
        except Exception:
            continue
        if d not in ("LONG", "SHORT") or not hasattr(t, "year"):
            continue
        if (d == "LONG" and not (sl < e < tp)) or (d == "SHORT" and not (tp < e < sl)):
            continue
        res = str(res or "").strip().upper()
        exc = "TP" if res.startswith("TP") else "SL" if res.startswith("SL") else "OPEN"
        utc_ms = int((t - IRAN).timestamp() * 1000)
        base = str(sym).strip().upper()
        out.append({"version": version, "base": base, "sym": f"{base}-SWAP-USDT", "t": utc_ms,
                    "dir": d, "e": e, "tp": tp, "sl": sl, "excel": exc})
    return out


def ceil_bar(t_ms):
    return ((t_ms + BAR_MS - 1) // BAR_MS) * BAR_MS


def analyze(tr, bars, horizon_min=HORIZON_MIN):
    """bars: لیست [ts, o, h, l, c, ...] به ترتیب زمانی، ts = شروع کندل (ms)."""
    t0, E, SL, TP, d = tr["t"], tr["e"], tr["sl"], tr["tp"], tr["dir"]
    R = abs(E - SL)
    TPd = abs(TP - E)
    t_start, t_end = ceil_bar(t0), t0 + horizon_min * MIN_MS
    win = [b for b in bars if t_start <= b[0] < t_end]
    if not win:
        return None
    first_tp = first_sl = None
    mfe = mae = 0.0
    mfe_t = mae_t = None
    mfe_before_sl = 0.0
    same_bar = False
    for b in win:
        ts, _o, h, l, _c = b[:5]
        off = (ts - t0) / MIN_MS
        if d == "LONG":
            fav, adv = h - E, E - l
            sl_hit, tp_hit = l <= SL, h >= TP
        else:
            fav, adv = E - l, h - E
            sl_hit, tp_hit = h >= SL, l <= TP
        if fav > mfe:
            mfe, mfe_t = fav, off
        if adv > mae:
            mae, mae_t = adv, off
        if sl_hit and tp_hit and first_sl is None and first_tp is None:
            same_bar = True
        if tp_hit and first_tp is None:
            first_tp = off
        if sl_hit and first_sl is None:
            first_sl = off
        if first_sl is None:
            mfe_before_sl = max(mfe_before_sl, fav)
    if first_sl is not None and first_tp is not None and first_sl == first_tp:
        pattern = "SAME_BAR"
    elif first_tp is not None and first_sl is not None:
        pattern = "TP_THEN_SL" if first_tp < first_sl else "SL_THEN_TP"
    elif first_tp is not None:
        pattern = "TP_ONLY"
    elif first_sl is not None:
        pattern = "SL_ONLY"
    else:
        pattern = "NONE"
    if first_tp is not None and (first_sl is None or first_tp < first_sl):
        first_hit, hit_min = "TP", first_tp
    elif first_sl is not None:
        first_hit, hit_min = "SL", first_sl
    else:
        first_hit, hit_min = "NONE", None
    close = win[-1][4]
    close_R = ((close - E) if d == "LONG" else (E - close)) / R
    return {
        "first_hit": first_hit, "hit_min": hit_min, "pattern": pattern,
        "tp_min": first_tp, "sl_min": first_sl,
        "mfe_R": mfe / R, "mfe_min": mfe_t, "mfe_pct": mfe / E * 100,
        "mfe_before_sl_R": mfe_before_sl / R,
        "mfe_tp_frac": mfe / TPd if TPd else 0.0,
        "mae_R": mae / R, "mae_min": mae_t,
        "close_R": close_R, "n_bars": len(win), "same_bar": same_bar,
    }


def fetch_window(ex, sym, t0, t1, state):
    """چند روش برای گرفتن کندل‌های بازه؛ اولین روشی که پوشش می‌دهد نگه داشته می‌شود."""
    modes = [state["mode"]] if state.get("mode") else ["since", "startTime", "endTime"]
    errs = []
    for mode in modes:
        try:
            if mode == "since":
                bars = ex.fetch_ohlcv(sym, timeframe="5m", since=t0 - 2 * BAR_MS, limit=1000)
            elif mode == "startTime":
                bars = ex.fetch_ohlcv(sym, timeframe="5m", limit=1000,
                                      params={"startTime": t0 - 2 * BAR_MS})
            else:
                bars = ex.fetch_ohlcv(sym, timeframe="5m", limit=1000,
                                      params={"endTime": t1 + BAR_MS})
        except Exception as e:
            errs.append(f"{mode}: {str(e)[:100]}")
            continue
        if bars and bars[0][0] <= t0 and bars[-1][0] + BAR_MS >= t1:
            state["mode"] = mode
            return bars, mode
        errs.append(f"{mode}: no coverage")
    return None, " | ".join(errs)[:200]


def fmt(x, nd=2, sign=False):
    if x is None:
        return "-"
    return f"{x:+.{nd}f}" if sign else f"{x:.{nd}f}"


def agg(rows):
    n = len(rows)
    if n == 0:
        return "بدون داده"
    tp_first = sum(1 for r in rows if r["first_hit"] == "TP") / n * 100
    sl_first = sum(1 for r in rows if r["first_hit"] == "SL") / n * 100
    none = sum(1 for r in rows if r["first_hit"] == "NONE") / n * 100
    tts = sum(1 for r in rows if r["pattern"] == "TP_THEN_SL") / n * 100
    stt = sum(1 for r in rows if r["pattern"] == "SL_THEN_TP") / n * 100
    hit = [r["hit_min"] for r in rows if r["hit_min"] is not None]
    med_min = st.median(hit) if hit else None
    mfe_avg = st.mean(r["mfe_R"] for r in rows)
    reach_half = sum(1 for r in rows if r["mfe_before_sl_R"] >= 0.5 * r["tp_frac_plan"]) / n * 100
    return (f"n={n:<4} TP-اول={tp_first:5.1f}%  SL-اول={sl_first:5.1f}%  بدون-برخورد={none:5.1f}%  "
            f"TP_بعد_SL={tts:4.1f}%  SL_بعد_TP={stt:4.1f}%  میانه‌ی دقیقه‌ی اولین برخورد={fmt(med_min, 1)}  "
            f"میانگین MFE={mfe_avg:+.2f}R  نیمه‌ی راه به TP قبل از SL={reach_half:4.1f}%")


def main():
    import ccxt
    ex = ccxt.toobit({"enableRateLimit": True})
    trades = []
    for name, pat in VERSIONS:
        trades += load_trades(find_file(pat), name)
    state = {"mode": None}
    cache = {}
    rows = []
    skipped = {}
    for tr in trades:
        key = (tr["sym"], tr["t"])
        if key not in cache:
            cache[key] = fetch_window(ex, tr["sym"], tr["t"], tr["t"] + HORIZON_MIN * MIN_MS, state)
            if cache[key][0] is None:
                skipped[tr["sym"]] = cache[key][1]
                print(f"no data {tr['sym']}: {cache[key][1]}", flush=True)
        bars, info = cache[key]
        res = analyze(tr, bars) if bars else None
        if res is None:
            continue
        res.update({"version": tr["version"], "sym": tr["sym"], "base": tr["base"],
                    "t_utc": tr["t"], "dir": tr["dir"], "entry": tr["e"], "sl": tr["sl"], "tp": tr["tp"],
                    "excel": tr["excel"]})
        res["tp_frac_plan"] = abs(tr["tp"] - tr["e"]) / abs(tr["e"] - tr["sl"])
        rows.append(res)
    print(f"mode={state['mode']} rows={len(rows)} trades={len(trades)}", flush=True)

    L = []
    L.append("مسیر قیمت ۶۰ دقیقه‌ی اول بعد از سیگنال (توبیت، کندل ۵ دقیقه‌ای)")
    L.append(f"روش دریافت داده: {state['mode']} | معاملات کل: {len(trades)} | با داده: {len(rows)} | بدون داده: {len(trades) - len(rows)}")
    if skipped:
        L.append("نمونه‌ی علت بدون داده: " + " ; ".join(f"{k}: {v}" for k, v in list(skipped.items())[:5]))
    L.append("ستون‌ها: TP-اول/SL-اول/بدون‌برخورد = کدام زودتر در ۶۰ دقیقه خورد. TP_بعد_SL = اول TP و بعد SL.")
    L.append("MFE = بیشترین حرکت مطلوب بر حسب R (R = فاصله‌ی ورود تا SL). نیمه‌ی راه = قبل از SL به نصف فاصله‌ی TP رسیده.")
    L.append("")
    L.append("--- به تفکیک نسخه ---")
    for name, _ in VERSIONS:
        L.append(f"{name:6} {agg([r for r in rows if r['version'] == name])}")
    L.append("")
    uniq = {}
    for r in rows:
        uniq.setdefault((r["sym"], r["t_utc"], r["dir"]), r)
    L.append(f"--- سیگنال‌های یکتا (بدون تکرار بین نسخه‌ها): {len(uniq)} ---")
    L.append(f"همه {agg(list(uniq.values()))}")
    L.append("")
    L.append(f"--- به تفکیک ارز (حداقل {MIN_SYM_N} سیگنال یکتا) ---")
    by_base = {}
    for r in uniq.values():
        by_base.setdefault(r["base"], []).append(r)
    for base, rs in sorted(by_base.items(), key=lambda x: -len(x[1])):
        if len(rs) >= MIN_SYM_N:
            L.append(f"{base:10} {agg(rs)}")
    L.append("")
    for db in DETAIL_BASES:
        L.append(f"--- جزئیات مسیر {db} (سیگنال‌های یکتا به ترتیب زمان) ---")
        for r in sorted([r for r in uniq.values() if r["base"] == db], key=lambda x: x["t_utc"]):
            fb = []
            if r["tp_min"] is not None:
                fb.append(f"TP@{r['tp_min']:.0f}m")
            if r["sl_min"] is not None:
                fb.append(f"SL@{r['sl_min']:.0f}m")
            L.append(
                f"{r['dir']:5} ورود={r['entry']} | {r['pattern']:10} | {' '.join(fb) or 'هیچ'} | "
                f"اوج مطلوب={r['mfe_R']:+.2f}R ({r['mfe_pct']:+.2f}%) در {fmt(r['mfe_min'], 0)}m | "
                f"بازگشت: {r['mae_R']:.2f}R | بسته‌شدن ۶۰m={r['close_R']:+.2f}R | نسخه‌ها={r['version']}"
            )
        L.append("")
    text = "\n".join(L)
    print(text)
    with open(os.path.join(BASE_DIR, "path60_summary.txt"), "w", encoding="utf-8") as fh:
        fh.write(text + "\n")
    cols = ["version", "sym", "t_utc", "dir", "entry", "sl", "tp", "excel", "first_hit", "hit_min", "pattern",
            "tp_min", "sl_min", "mfe_R", "mfe_pct", "mfe_min", "mfe_before_sl_R", "mfe_tp_frac",
            "mae_R", "mae_min", "close_R", "n_bars", "same_bar"]
    with open(os.path.join(BASE_DIR, "path60_signals.csv"), "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(r)


if __name__ == "__main__":
    main()
