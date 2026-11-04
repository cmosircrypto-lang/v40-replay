"""
بک‌تست «سطوح گن» — طبق PREREG.txt (پارامترها ثابت‌اند).
"""
import bisect
import csv
import math
import os
import time
from datetime import datetime, timezone

import main as M

EXCHANGE = os.environ.get("GANN_EXCHANGE", "okx")
DAYS = int(os.environ.get("GANN_DAYS", "365"))
FEE = float(os.environ.get("BT_FEE", "0.0006"))
H1 = 3600000
D1 = 24 * H1
ATR_N = 14
STEP = 0.125
N_LEVELS = 16
ANCHOR_DAYS = 180
ATR_BUF = 0.5
MAX_TP_ATR = 3.0
RR_MIN = 1.5
MAX_HOLD = 48
COOLDOWN = 6
OUT_TRADES = os.environ.get("GANN_OUT", "gann_trades.csv")
OUT_SUMMARY = os.environ.get("GANN_SUMMARY", "gann_summary.txt")


def make_exchange():
    if EXCHANGE == "toobit":
        return M.create_exchange()
    import ccxt
    ex = getattr(ccxt, EXCHANGE)({"enableRateLimit": True})
    ex.load_markets()
    return ex


def to_ccxt_symbol(ex, sym):
    if EXCHANGE == "toobit":
        return sym
    base = sym.split("-")[0]
    cand = f"{base}/USDT:USDT"
    return cand if cand in ex.markets else None


def fetch_tf(ex, csym, tf, since, until):
    step = {"1h": H1, "1d": D1}[tf]
    got = {}
    cur = since
    while cur < until:
        batch = ex.fetch_ohlcv(csym, timeframe=tf, since=cur, limit=300)
        if not batch:
            break
        for b in batch:
            if since <= b[0] < until:
                got[int(b[0])] = (int(b[0]), float(b[1]), float(b[2]), float(b[3]), float(b[4]))
        nxt = int(batch[-1][0]) + step
        if nxt <= cur:
            break
        cur = nxt
    return [got[k] for k in sorted(got)]


def iso(ms):
    return datetime.fromtimestamp(ms / 1000, timezone.utc).strftime("%Y-%m-%d %H:%M")


def gann_levels(anchor):
    s0 = math.sqrt(anchor)
    lv = {anchor}
    for n in range(1, N_LEVELS + 1):
        up = (s0 + STEP * n) ** 2
        lv.add(up)
        dn_root = s0 - STEP * n
        if dn_root > 0:
            lv.add(dn_root ** 2)
    return sorted(lv)


def simulate_symbol(h1, d1):
    n = len(h1)
    tr = [0.0] * n
    for i in range(n):
        _, o, h, l, c = h1[i]
        tr[i] = h - l if i == 0 else max(h - l, abs(h - h1[i - 1][4]), abs(l - h1[i - 1][4]))
    atr = [None] * n
    for i in range(ATR_N, n):
        atr[i] = sum(tr[i - ATR_N + 1:i + 1]) / ATR_N

    trades = []
    next_ok = 0
    pd = -1
    levels = []
    level_day = None
    for k in range(n - 1):
        t = h1[k][0]
        while pd + 1 < len(d1) and d1[pd + 1][0] + D1 <= t:
            pd += 1
        if pd < 30:
            continue
        if level_day != pd:
            window = d1[max(0, pd - ANCHOR_DAYS + 1):pd + 1]
            anchor = min(r[3] for r in window)
            levels = gann_levels(anchor)
            level_day = pd
        if k < next_ok or atr[k] is None:
            continue

        a_k = atr[k]
        _, _, hi_k, lo_k, cl_k = h1[k]
        sig = None
        # LONG: لمس و بازیابی یک سطح حمایتی
        i1 = bisect.bisect_left(levels, lo_k)
        i2 = bisect.bisect_left(levels, cl_k)
        if i1 < i2:
            L = levels[i2 - 1]
            j = bisect.bisect_right(levels, cl_k)
            if j < len(levels):
                tp = levels[j]
                sl = L - ATR_BUF * a_k
                risk = cl_k - sl
                if risk > 0 and (tp - cl_k) <= MAX_TP_ATR * a_k and (tp - cl_k) / risk >= RR_MIN:
                    sig = ("LONG", cl_k, sl, tp, risk)
        # SHORT: لمس و بازیابی یک سطح مقاومتی
        if sig is None:
            i1 = bisect.bisect_right(levels, cl_k)
            i2 = bisect.bisect_right(levels, hi_k)
            if i1 < i2:
                L = levels[i1]
                j = bisect.bisect_left(levels, cl_k) - 1
                if j >= 0:
                    tp = levels[j]
                    sl = L + ATR_BUF * a_k
                    risk = sl - cl_k
                    if risk > 0 and (cl_k - tp) <= MAX_TP_ATR * a_k and (cl_k - tp) / risk >= RR_MIN:
                        sig = ("SHORT", cl_k, sl, tp, risk)
        if sig is None:
            continue

        direction, entry, sl, tp, risk = sig
        exit_idx = None
        reason = None
        exit_px = None
        last = min(k + MAX_HOLD, n - 1)
        for m in range(k + 1, last + 1):
            _, _, hi, lo, _ = h1[m]
            if direction == "LONG":
                if lo <= sl:
                    reason, exit_px, exit_idx = "SL", sl, m
                    break
                if hi >= tp:
                    reason, exit_px, exit_idx = "TP", tp, m
                    break
            else:
                if hi >= sl:
                    reason, exit_px, exit_idx = "SL", sl, m
                    break
                if lo <= tp:
                    reason, exit_px, exit_idx = "TP", tp, m
                    break
        if exit_idx is None:
            reason, exit_px, exit_idx = "TIMEOUT", h1[last][4], last
        gross = (exit_px - entry) / risk if direction == "LONG" else (entry - exit_px) / risk
        net = gross - 2 * FEE * entry / risk
        trades.append({"dir": direction, "entry_ms": t, "entry": entry, "sl": sl, "tp": tp,
                       "rr": round(abs(tp - entry) / risk, 3), "reason": reason,
                       "bars": exit_idx - k, "R": round(net, 4)})
        next_ok = exit_idx + COOLDOWN
    return trades


def run():
    ex = make_exchange()
    print(f"منبع: {EXCHANGE} | روز={DAYS} | fee={FEE}")
    until = int(time.time() * 1000) // H1 * H1
    since = until - DAYS * D1
    all_trades = []
    for sym in M.SYMBOLS:
        csym = to_ccxt_symbol(ex, sym)
        if csym is None:
            print(f"skip {sym}: در {EXCHANGE} نیست")
            continue
        try:
            h1 = fetch_tf(ex, csym, "1h", since - 10 * D1, until)
            d1 = fetch_tf(ex, csym, "1d", since - ANCHOR_DAYS * D1, until)
        except Exception as e:
            print(f"skip {sym}: {str(e)[:150]}")
            continue
        if len(h1) < 300 or len(d1) < 40:
            print(f"skip {sym}: داده‌ی کم")
            continue
        tr = simulate_symbol(h1, d1)
        for t in tr:
            t["symbol"] = sym
            t["entry_time"] = iso(t["entry_ms"])
        all_trades.extend(tr)
        print(f"{sym}: {len(tr)} معامله")

    if not all_trades:
        print("هیچ معامله‌ای ساخته نشد.")
        return
    all_trades.sort(key=lambda x: x["entry_ms"])
    keys = ["symbol", "entry_time", "dir", "entry", "sl", "tp", "rr", "reason", "bars", "R"]
    with open(OUT_TRADES, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=keys, extrasaction="ignore")
        w.writeheader()
        w.writerows(all_trades)
    summary(all_trades)


def summary(trades):
    Rs = [t["R"] for t in trades]
    n = len(Rs)
    mean = sum(Rs) / n
    sd = math.sqrt(sum((x - mean) ** 2 for x in Rs) / (n - 1)) if n > 1 else 0.0
    t_stat = mean / (sd / math.sqrt(n)) if sd > 0 else float("nan")
    med = trades[n // 2]["entry_ms"]
    h1 = [t["R"] for t in trades if t["entry_ms"] < med]
    h2 = [t["R"] for t in trades if t["entry_ms"] >= med]
    wins = sum(1 for x in Rs if x > 0)
    reasons = {r: sum(1 for t in trades if t["reason"] == r) for r in ("TP", "SL", "TIMEOUT")}
    lg = [t["R"] for t in trades if t["dir"] == "LONG"]
    sh = [t["R"] for t in trades if t["dir"] == "SHORT"]

    ok_n = n >= 100
    ok_mean = mean > 0
    ok_halves = bool(h1) and bool(h2) and sum(h1) / len(h1) > 0 and sum(h2) / len(h2) > 0
    verdict = "PASS" if (ok_n and ok_mean and ok_halves) else "FAIL"

    lines = [
        f"معاملات: {n} | TP={reasons['TP']} SL={reasons['SL']} TIMEOUT={reasons['TIMEOUT']} | برد={wins / n:.1%}",
        f"R کل خالص: {sum(Rs):+.1f} | میانگین: {mean:+.3f} | t-stat: {t_stat:.2f}",
        f"LONG: {len(lg)} معامله، میانگین {sum(lg) / max(len(lg), 1):+.3f}  |  "
        f"SHORT: {len(sh)} معامله، میانگین {sum(sh) / max(len(sh), 1):+.3f}",
        f"نیمه‌ی اول: {len(h1)} معامله، R {sum(h1):+.1f}  |  نیمه‌ی دوم: {len(h2)} معامله، R {sum(h2):+.1f}",
        f"معیار از قبل: n≥100 [{ok_n}] | میانگین>0 [{ok_mean}] | هر دو نیمه>0 [{ok_halves}]",
        f"نتیجه: {verdict}",
    ]
    text = "\n".join(lines)
    print(text)
    with open(OUT_SUMMARY, "w", encoding="utf-8") as fh:
        fh.write(text + "\n")


if __name__ == "__main__":
    run()
