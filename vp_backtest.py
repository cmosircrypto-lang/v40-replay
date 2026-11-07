"""
بک‌تست VP_A (PREREG_VP_A.txt) روی ۸۸ ارز ربات، کندل ۱۵ دقیقه‌ای توبیت (آخرین ~۱۰ روز).
توصیفی/اکتشافی: این داده قبل از ثبت است، پس پذیرش نیست؛ کنترل (پروفایل D-2) هم محاسبه می‌شود.
"""
import os
import statistics as st
from datetime import datetime, timezone

import numpy as np

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TF_MS = 900000
DAY_MS = 86400000
FEE_PCT = 0.12
VA_FRAC = 0.70
HORIZON = 24
ATR_N = 14
SL_ATR = 0.5
MIN_SYM = 0
SYMBOLS = [
    "BTC-SWAP-USDT",
    "ETH-SWAP-USDT",
    "SOL-SWAP-USDT",
    "XRP-SWAP-USDT",
    "BNB-SWAP-USDT",
    "DOGE-SWAP-USDT",
    "ADA-SWAP-USDT",
    "TRX-SWAP-USDT",
    "AVAX-SWAP-USDT",
    "LINK-SWAP-USDT",
    "DOT-SWAP-USDT",
    "LTC-SWAP-USDT",
    "BCH-SWAP-USDT",
    "TON-SWAP-USDT",
    "SUI-SWAP-USDT",
    "NEAR-SWAP-USDT",
    "APT-SWAP-USDT",
    "ARB-SWAP-USDT",
    "OP-SWAP-USDT",
    "ATOM-SWAP-USDT",
    "UNI-SWAP-USDT",
    "AAVE-SWAP-USDT",
    "FIL-SWAP-USDT",
    "INJ-SWAP-USDT",
    "TIA-SWAP-USDT",
    "JUP-SWAP-USDT",
    "ENA-SWAP-USDT",
    "WIF-SWAP-USDT",
    "1000PEPE-SWAP-USDT",
    "1000SHIB-SWAP-USDT",
    "WLD-SWAP-USDT",
    "SEI-SWAP-USDT",
    "RUNE-SWAP-USDT",
    "LDO-SWAP-USDT",
    "STX-SWAP-USDT",
    "IMX-SWAP-USDT",
    "HBAR-SWAP-USDT",
    "ICP-SWAP-USDT",
    "ETC-SWAP-USDT",
    "XLM-SWAP-USDT",
    "CRV-SWAP-USDT",
    "SNX-SWAP-USDT",
    "COMP-SWAP-USDT",
    "SUSHI-SWAP-USDT",
    "1INCH-SWAP-USDT",
    "GRT-SWAP-USDT",
    "DYDX-SWAP-USDT",
    "GMX-SWAP-USDT",
    "PENDLE-SWAP-USDT",
    "ONDO-SWAP-USDT",
    "JTO-SWAP-USDT",
    "PYTH-SWAP-USDT",
    "STRK-SWAP-USDT",
    "MANTA-SWAP-USDT",
    "1000BONK-SWAP-USDT",
    "1000FLOKI-SWAP-USDT",
    "MEME-SWAP-USDT",
    "ORDI-SWAP-USDT",
    "1000SATS-SWAP-USDT",
    "1000RATS-SWAP-USDT",
    "POPCAT-SWAP-USDT",
    "BRETT-SWAP-USDT",
    "TURBO-SWAP-USDT",
    "1000000MOG-SWAP-USDT",
    "DOGS-SWAP-USDT",
    "FET-SWAP-USDT",
    "TAO-SWAP-USDT",
    "AKT-SWAP-USDT",
    "ILV-SWAP-USDT",
    "AXS-SWAP-USDT",
    "SAND-SWAP-USDT",
    "MANA-SWAP-USDT",
    "GALA-SWAP-USDT",
    "ALGO-SWAP-USDT",
    "VET-SWAP-USDT",
    "EGLD-SWAP-USDT",
    "FLOW-SWAP-USDT",
    "KAVA-SWAP-USDT",
    "ROSE-SWAP-USDT",
    "KAS-SWAP-USDT",
    "THETA-SWAP-USDT",
    "CHZ-SWAP-USDT",
    "ENJ-SWAP-USDT",
    "ZIL-SWAP-USDT",
    "ONE-SWAP-USDT",
    "QTUM-SWAP-USDT",
    "IOTA-SWAP-USDT",
    "NEO-SWAP-USDT",
]


def profile(bars, w):
    """bars: لیست [ts,o,h,l,c,v]. برمی‌گرداند (POC, VAH, VAL) یا None."""
    if not bars:
        return None
    lo_all = min(b[3] for b in bars)
    hi_all = max(b[2] for b in bars)
    i0 = int(np.floor(lo_all / w))
    i1 = int(np.floor(hi_all / w))
    if i1 < i0:
        return None
    vol = np.zeros(i1 - i0 + 1)
    for b in bars:
        a = int(np.floor(b[3] / w)) - i0
        z = int(np.floor(b[2] / w)) - i0
        v = b[5]
        if v <= 0:
            continue
        vol[a:z + 1] += v / (z - a + 1)
    total = vol.sum()
    if total <= 0:
        return None
    p = int(np.argmax(vol))
    lo = hi = p
    acc = vol[p]
    while acc < VA_FRAC * total and (lo > 0 or hi < len(vol) - 1):
        up = vol[hi + 1] if hi < len(vol) - 1 else -1
        dn = vol[lo - 1] if lo > 0 else -1
        if up >= dn:
            hi += 1
            acc += up
        else:
            lo -= 1
            acc += dn
    poc = (p + i0 + 0.5) * w
    vah = (hi + i0 + 1) * w
    val = (lo + i0) * w
    return poc, vah, val


def atr_before(bars, idx):
    if idx < ATR_N + 1:
        return None
    trs = []
    for k in range(idx - ATR_N, idx):
        h, l = bars[k][2], bars[k][3]
        pc = bars[k - 1][4]
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    return sum(trs) / ATR_N


def run_day(bars_by_day, day, prof_day, c_idx_map):
    """روز `day` را با پروفایل `prof_day` بررسی می‌کند. خروجی: (side, R_gross, R_net) یا None."""
    pr = prof_day
    if pr is None:
        return None
    poc, vah, val = pr
    day_bars = bars_by_day.get(day)
    if not day_bars:
        return None
    state = None
    w_all = None
    for k, b in enumerate(day_bars):
        c = b[4]
        if c > vah:
            state = "up"
        elif c < val:
            state = "dn"
        else:
            if state is None:
                continue
            side = "SHORT" if state == "up" else "LONG"
            # ورود = close همین کندل
            E = c
            gi = c_idx_map[b[0]]
            A = atr_before(ALL_BARS, gi)
            if not A:
                return None
            if side == "LONG":
                SL = val - SL_ATR * A
                TP = poc
                if not (TP > E > SL):
                    return None
            else:
                SL = vah + SL_ATR * A
                TP = poc
                if not (SL > E > TP):
                    return None
            R = abs(E - SL)
            out = None
            pnl = 0.0
            for j in range(gi + 1, min(gi + 1 + HORIZON, len(ALL_BARS))):
                _, _o, h, l, cl = ALL_BARS[j][:5]
                if side == "LONG":
                    if l <= SL:
                        pnl = SL - E
                        break
                    if h >= TP:
                        pnl = TP - E
                        break
                else:
                    if h >= SL:
                        pnl = E - SL
                        break
                    if l <= TP:
                        pnl = E - TP
                        break
            else:
                last = ALL_BARS[min(gi + HORIZON, len(ALL_BARS) - 1)][4]
                pnl = (last - E) if side == "LONG" else (E - last)
            fee_R = (FEE_PCT / 100) * E / R
            return side, pnl / R, pnl / R - fee_R, gi
    return None


ALL_BARS = []


def main():
    import ccxt
    ex = ccxt.toobit({"enableRateLimit": True})
    res_all, res_ctrl = [], []
    per_sym = {}
    skipped = []
    global ALL_BARS
    for sym in SYMBOLS:
        try:
            bars = ex.fetch_ohlcv(sym, timeframe="15m", limit=1000)
        except Exception as e:
            skipped.append(f"{sym}: {str(e)[:60]}")
            continue
        if not bars or len(bars) < 300:
            skipped.append(f"{sym}: داده کم")
            continue
        ALL_BARS = bars
        c_idx_map = {b[0]: i for i, b in enumerate(bars)}
        by_day = {}
        for b in bars:
            d = (b[0] // DAY_MS)
            by_day.setdefault(d, []).append(b)
        days = sorted(by_day)
        sym_rows = []
        for d in days:
            if d - 1 not in by_day or d - 2 not in by_day:
                continue
            if len(by_day[d - 1]) < 90 or len(by_day[d - 2]) < 90 or len(by_day[d]) < 90:
                continue
            last_close = by_day[d - 1][-1][4]
            w = 0.001 * last_close
            p1 = profile(by_day[d - 1], w)
            p2 = profile(by_day[d - 2], w)
            r1 = run_day(by_day, d, p1, c_idx_map)
            r2 = run_day(by_day, d, p2, c_idx_map)
            if r1:
                sym_rows.append((sym, bars[r1[3]][0], r1[1], r1[2]))
                res_all.append((sym, bars[r1[3]][0], r1[1], r1[2]))
            if r2:
                res_ctrl.append((sym, bars[r2[3]][0], r2[1], r2[2]))
        per_sym[sym] = sym_rows

    def summ(rows):
        if not rows:
            return "بدون معامله"
        rows = sorted(rows, key=lambda x: x[1])
        n = len(rows)
        net = [r[3] for r in rows]
        gross = [r[2] for r in rows]
        h = n // 2
        f = lambda v: f"{v:+.3f}R"
        return (f"n={n:<4} ناخالص={f(st.mean(gross))} خالص={f(st.mean(net))} "
                f"نیمه‌ی اول={f(st.mean(net[:h])) if h else '-'} نیمه‌ی دوم={f(st.mean(net[h:])) if n-h else '-'} "
                f"برد(TP)={sum(1 for g in gross if g>0)/n*100:.0f}%")

    L = ["VP_A بک‌تست توصیفی روی ۸۸ ارز (توبیت، ۱۵ دقیقه، ~۱۰ روز) — پیش از ثبت، پذیرش ندارد",
         f"ارزهای بدون داده: {len(skipped)}" + (" | " + " ; ".join(skipped[:8]) if skipped else ""),
         "",
         "--- کل (پروفایل D-1، فرضیه) ---",
         summ(res_all),
         "--- کنترل (پروفایل D-2) ---",
         summ(res_ctrl),
         "",
         "--- به تفکیک ارز (فقط ارزهایی که معامله داشتند) ---"]
    for sym, rows in sorted(per_sym.items(), key=lambda x: -len(x[1])):
        if rows:
            L.append(f"{sym:18} {summ(rows)}")
    text = "\n".join(L)
    print(text)
    with open(os.path.join(BASE_DIR, "vp_a_backtest_summary.txt"), "w", encoding="utf-8") as fh:
        fh.write(text + "\n")


if __name__ == "__main__":
    main()
