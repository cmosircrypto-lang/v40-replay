"""
شبکه‌ی SL/TP بر حسب ATR روی همه‌ی نسخه‌ها (کندل ۱۵ دقیقه‌ای توبیت).
ورود و جهت از فایل‌ها؛ SL و TP جدید = ورود ∓/± ضریب×ATR۱۴ (ATR از ۱۴ کندل بسته‌شده‌ی قبل از ورود).
معیارها بر حسب ATR: سود میانگین هر معامله، با و بدون کارمزد.
ردیف "فایل": SL/TP خود فایل (برای مقایسه).
قواعد: SL اولویت دارد؛ در کندل ورود فقط SL؛ حداکثر ۷ روز؛ بعد با close آخر.
"""
import glob
import os
from datetime import timedelta
import statistics as st

import ccxt
import openpyxl

FEE = 0.0006
IRAN = timedelta(hours=3, minutes=30)
M15 = 900000
MAX_BARS = 672
ATR_N = 14
SL_GRID = [1.0, 1.5, 2.0]
TP_GRID = [1.5, 2.0, 2.5, 2.7, 3.0, 4.0]
VERSIONS = [("V10", "*V10*.xlsx"), ("V20", "*V20*.xlsx"), ("V30", "*V30*.xlsx"), ("V40", "*V40*.xlsx"),
            ("V50", "*V50*.xlsx"), ("V60", "*V60*.xlsx"), ("Blank", "*Blank*.xlsx")]
BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def find_file(pattern):
    m = glob.glob(os.path.join(BASE_DIR, pattern))
    if len(m) != 1:
        raise SystemExit(f"الگوی {pattern} باید دقیقاً یک فایل داشته باشد؛ پیدا شد: {m}")
    return m[0]


def load_trades(path):
    ws = openpyxl.load_workbook(path, data_only=True, read_only=True).worksheets[0]
    rows = list(ws.iter_rows(values_only=True))
    hi = next(i for i, r in enumerate(rows) if r and r[0] == "نماد")
    out = []
    for r in rows[hi + 1:]:
        if not r or r[0] in (None, ""):
            continue
        sym, date, t, d, e, tp, sl, res = r[:8]
        d = str(d or "").upper()
        try:
            e, tp, sl = float(e), float(tp), float(sl)
        except Exception:
            continue
        if d not in ("LONG", "SHORT") or not hasattr(t, "year"):
            continue
        if (d == "LONG" and not (sl < e < tp)) or (d == "SHORT" and not (tp < e < sl)):
            continue
        utc_ms = int((t - IRAN).timestamp() * 1000)
        base = str(sym).strip().upper()
        out.append({"sym": f"{base}-SWAP-USDT", "t": utc_ms, "dir": d, "e": e, "tp": tp, "sl": sl})
    return out


def locate(bars, t_ms):
    for j, b in enumerate(bars):
        if b[0] <= t_ms < b[0] + M15:
            return j
    return None


def atr_before(bars, idx):
    if idx < ATR_N + 1:
        return None
    trs = []
    for k in range(idx - ATR_N, idx):
        h, l = bars[k][2], bars[k][3]
        pc = bars[k - 1][4]
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    return sum(trs) / ATR_N


def sim(bars, idx, entry, sl_px, tp_px, d):
    end = min(idx + MAX_BARS, len(bars))
    reason, exit_px = None, None
    for j in range(idx, end):
        _, o, h, l, c = bars[j][:5]
        if d == "LONG":
            if l <= sl_px:
                reason, exit_px = "SL", sl_px
                break
            if j > idx and h >= tp_px:
                reason, exit_px = "TP", tp_px
                break
        else:
            if h >= sl_px:
                reason, exit_px = "SL", sl_px
                break
            if j > idx and l <= tp_px:
                reason, exit_px = "TP", tp_px
                break
    if reason is None:
        reason, exit_px = "TIMEOUT", bars[end - 1][4]
    pnl = (exit_px - entry) if d == "LONG" else (entry - exit_px)
    return reason, pnl


def main():
    ex = ccxt.toobit({"enableRateLimit": True})
    cache = {}
    lines = ["شبکه‌ی SL/TP بر حسب ATR۱۴ (۱۵ دقیقه‌ای، ~۱۰ روز، توبیت)",
             "ستون‌ها: n | برد% | نقطه‌ی سربه‌سر% (=SL/(SL+TP)) | سود میانگین بر حسب ATR (ناخالص) | (خالص) | TIMEOUT",
             ""]
    for name, pat in VERSIONS:
        trades = load_trades(find_file(pat))
        combos = [("فایل", None, None)] + [(f"SL{s}/TP{t}", s, t) for s in SL_GRID for t in TP_GRID]
        results = {c[0]: {"res": [], "win": 0} for c in combos}
        used = 0
        for tr in trades:
            if tr["sym"] not in cache:
                try:
                    cache[tr["sym"]] = ex.fetch_ohlcv(tr["sym"], timeframe="15m", limit=1000)
                except Exception as e:
                    cache[tr["sym"]] = None
                    print(f"skip {tr['sym']}: {str(e)[:120]}", flush=True)
            bars = cache[tr["sym"]]
            if not bars:
                continue
            idx = locate(bars, tr["t"])
            if idx is None:
                continue
            atr = atr_before(bars, idx)
            if not atr:
                continue
            used += 1
            e, d = tr["e"], tr["dir"]
            for label, s, t in combos:
                if label == "فایل":
                    sl_px, tp_px = tr["sl"], tr["tp"]
                    risk = abs(e - sl_px)
                else:
                    sl_px = e - s * atr if d == "LONG" else e + s * atr
                    tp_px = e + t * atr if d == "LONG" else e - t * atr
                    risk = s * atr
                reason, pnl = sim(bars, idx, e, sl_px, tp_px, d)
                g_atr = pnl / atr
                n_atr = g_atr - 2 * FEE * e / atr
                results[label]["res"].append((reason, g_atr, n_atr, risk / atr))
        lines.append(f"--- {name} (معاملات قابل‌محاسبه: {used}) ---")
        for label, s, t in combos:
            R = results[label]["res"]
            if not R:
                lines.append(f"{label:12} بدون داده")
                continue
            n = len(R)
            win = sum(1 for x in R if x[0] == "TP") / n * 100
            tmo = sum(1 for x in R if x[0] == "TIMEOUT")
            if label == "فایل":
                be = float("nan")
            else:
                be = s / (s + t) * 100
            g = st.mean(x[1] for x in R)
            nt = st.mean(x[2] for x in R)
            lines.append(f"{label:12} n={n:<4} برد={win:5.1f}%  BE={be:5.1f}%  ناخ.={g:+.3f}  خالص={nt:+.3f}  TIMEOUT={tmo}")
        lines.append("")
    text = "\n".join(lines)
    print(text)
    with open(os.path.join(BASE_DIR, "tp2_grid_summary.txt"), "w", encoding="utf-8") as fh:
        fh.write(text + "\n")


if __name__ == "__main__":
    main()
