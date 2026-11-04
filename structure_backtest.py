"""
بک‌تست «ساختار + بازیابی سطح» — طبق PREREG.txt (پارامترها ثابت‌اند).
"""
import csv
import math
import os
import time
from datetime import datetime, timezone

import main as M

EXCHANGE = os.environ.get("SKL_EXCHANGE", "okx")
DAYS = int(os.environ.get("SKL_DAYS", "365"))
FEE = float(os.environ.get("BT_FEE", "0.0006"))
H1 = 3600000
H4 = 4 * H1
D1 = 24 * H1
EMA_N = 50
ATR_N = 14
RR_MIN = 2.0
ATR_BUF = 0.2
SWEEP_BARS = 3
MAX_HOLD = 48
COOLDOWN = 6
OUT_TRADES = os.environ.get("SKL_OUT", "structure_trades.csv")
OUT_SUMMARY = os.environ.get("SKL_SUMMARY", "structure_summary.txt")


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
    """لیست (ts, o, h, l, c) مرتب برای کندل‌های بسته‌شده."""
    step = {"1h": H1, "4h": H4, "1d": D1}[tf]
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


def prepare(h1, h4, d1):
    """ATR ساعتی (میانگین ساده‌ی TR)، EMA۵۰ ۴ساعته، سوئینگ‌های ۴ساعته با زمان تأیید."""
    n = len(h1)
    tr = [0.0] * n
    for i in range(n):
        _, o, h, l, c = h1[i]
        tr[i] = h - l if i == 0 else max(h - l, abs(h - h1[i - 1][4]), abs(l - h1[i - 1][4]))
    atr = [None] * n
    for i in range(ATR_N, n):
        atr[i] = sum(tr[i - ATR_N + 1:i + 1]) / ATR_N

    m = len(h4)
    ema4 = [None] * m
    a = 2 / (EMA_N + 1)
    e = None
    for i, r in enumerate(h4):
        e = r[4] if e is None else e + a * (r[4] - e)
        ema4[i] = e if i >= EMA_N else None

    sw_hi, sw_lo = [], []
    for i in range(2, m - 2):
        hi = h4[i][2]
        lo = h4[i][3]
        if hi > max(h4[i - 2][2], h4[i - 1][2], h4[i + 1][2], h4[i + 2][2]):
            sw_hi.append((h4[i][0] + 3 * H4, hi))
        if lo < min(h4[i - 2][3], h4[i - 1][3], h4[i + 1][3], h4[i + 2][3]):
            sw_lo.append((h4[i][0] + 3 * H4, lo))
    return atr, ema4, sw_hi, sw_lo


def simulate_symbol(h1, h4, d1):
    atr, ema4, sw_hi, sw_lo = prepare(h1, h4, d1)
    n = len(h1)
    trades = []
    next_ok = 0
    pd = -1          # آخرین کندل روزانه‌ی بسته‌شده
    p4 = -1          # آخرین کندل ۴ساعته‌ی بسته‌شده
    ph = -1          # آخرین سوئینگ سقف تأییدشده
    pl = -1          # آخرین سوئینگ کف تأییدشده
    last_hi = None
    last_lo = None
    for k in range(n - 1):
        t = h1[k][0]
        while pd + 1 < len(d1) and d1[pd + 1][0] + D1 <= t:
            pd += 1
        while p4 + 1 < len(h4) and h4[p4 + 1][0] + H4 <= t:
            p4 += 1
        while ph + 1 < len(sw_hi) and sw_hi[ph + 1][0] <= t:
            ph += 1
            last_hi = sw_hi[ph][1]
        while pl + 1 < len(sw_lo) and sw_lo[pl + 1][0] <= t:
            pl += 1
            last_lo = sw_lo[pl][1]

        if k < next_ok or pd < 0 or p4 < 0 or k < SWEEP_BARS or ema4[p4] is None or atr[k] is None:
            continue
        pdh, pdl = d1[pd][2], d1[pd][3]
        a_k = atr[k]
        c4 = h4[p4][4]
        allow_long = c4 > ema4[p4]
        allow_short = c4 < ema4[p4]
        win = h1[k - SWEEP_BARS:k + 1]
        close_k = h1[k][4]

        sig = None
        if allow_long:
            for L in [x for x in (pdl, last_lo) if x is not None]:
                if min(b[3] for b in win) < L and close_k > L:
                    sweep = min(b[3] for b in win)
                    sl = sweep - ATR_BUF * a_k
                    risk = close_k - sl
                    tps = [x for x in (pdh, last_hi) if x is not None and x > close_k]
                    if risk > 0 and tps:
                        tp = min(tps)
                        if (tp - close_k) / risk >= RR_MIN:
                            sig = ("LONG", close_k, sl, tp, risk)
                    break
        if sig is None and allow_short:
            for L in [x for x in (pdh, last_hi) if x is not None]:
                if max(b[2] for b in win) > L and close_k < L:
                    sweep = max(b[2] for b in win)
                    sl = sweep + ATR_BUF * a_k
                    risk = sl - close_k
                    tps = [x for x in (pdl, last_lo) if x is not None and x < close_k]
                    if risk > 0 and tps:
                        tp = max(tps)
                        if (close_k - tp) / risk >= RR_MIN:
                            sig = ("SHORT", close_k, sl, tp, risk)
                    break
        if sig is None:
            continue

        direction, entry, sl, tp, risk = sig
        exit_idx = None
        reason = None
        exit_px = None
        last = min(k + MAX_HOLD, n - 1)
        for m in range(k + 1, last + 1):
            _, _, hi, lo, cl = h1[m]
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
            h4 = fetch_tf(ex, csym, "4h", since - 20 * D1, until)
            d1 = fetch_tf(ex, csym, "1d", since - 10 * D1, until)
        except Exception as e:
            print(f"skip {sym}: {str(e)[:150]}")
            continue
        if len(h1) < 300 or len(h4) < 80 or len(d1) < 10:
            print(f"skip {sym}: داده‌ی کم")
            continue
        tr = simulate_symbol(h1, h4, d1)
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
