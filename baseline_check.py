"""
تحلیل پایه: LONG و SHORT روی همه‌ی کندل‌های ۱ ساعته (بدون سیگنال) — طبق PREREG_BASELINE.txt
"""
import csv
import os
import time
from datetime import datetime, timezone

import ccxt

EXCHANGE = os.environ.get("BASE_EXCHANGE", "okx")
FEE = float(os.environ.get("BT_FEE", "0.0006"))
H1 = 3600000
START = 1636156800000  # 2021-11-06 UTC
ATR_N = 14
SL_ATR, TP_ATR, MAX_HOLD = 1.0, 2.0, 24
SYMBOLS = ["BTC/USDT:USDT", "ETH/USDT:USDT", "SOL/USDT:USDT"]
OUT = os.environ.get("BASE_OUT", "baseline_summary.txt")


def fetch_all(ex, sym):
    rows = {}
    cur = START
    end = int(time.time() * 1000)
    while cur < end:
        batch = ex.fetch_ohlcv(sym, timeframe="1h", since=cur, limit=100)
        if not batch:
            break
        for b in batch:
            rows[int(b[0])] = (int(b[0]), float(b[1]), float(b[2]), float(b[3]), float(b[4]))
        nxt = int(batch[-1][0]) + H1
        if nxt <= cur:
            break
        cur = nxt
    return [rows[k] for k in sorted(rows)]


def atr_series(h1):
    n = len(h1)
    tr = [0.0] * n
    for i in range(n):
        _, o, h, l, c = h1[i]
        tr[i] = h - l if i == 0 else max(h - l, abs(h - h1[i - 1][4]), abs(l - h1[i - 1][4]))
    atr = [None] * n
    for i in range(ATR_N, n):
        atr[i] = sum(tr[i - ATR_N + 1:i + 1]) / ATR_N
    return atr


def trade(h1, atr, k, direction):
    entry = h1[k][4]
    a = atr[k]
    risk = SL_ATR * a
    if direction == "LONG":
        sl, tp = entry - risk, entry + TP_ATR * a
    else:
        sl, tp = entry + risk, entry - TP_ATR * a
    n = len(h1)
    last = min(k + MAX_HOLD, n - 1)
    exit_px = h1[last][4]
    reason = "TIMEOUT"
    for j in range(k + 1, last + 1):
        _, _, hj, lj, _ = h1[j]
        if direction == "LONG":
            if lj <= sl:
                reason, exit_px = "SL", sl
                break
            if hj >= tp:
                reason, exit_px = "TP", tp
                break
        else:
            if hj >= sl:
                reason, exit_px = "SL", sl
                break
            if lj <= tp:
                reason, exit_px = "TP", tp
                break
    gross = (exit_px - entry) / risk if direction == "LONG" else (entry - exit_px) / risk
    return gross - 2 * FEE * entry / risk, reason


def main():
    ex = getattr(ccxt, EXCHANGE)({"enableRateLimit": True})
    ex.load_markets()
    lines = [f"تحلیل پایه | {EXCHANGE} 1H | بدون سیگنال | SL={SL_ATR} ATR، TP={TP_ATR} ATR، نگه‌داری {MAX_HOLD} کندل"]
    stats = {"LONG": [], "SHORT": []}
    reasons = {"LONG": {"TP": 0, "SL": 0, "TIMEOUT": 0}, "SHORT": {"TP": 0, "SL": 0, "TIMEOUT": 0}}
    for sym in SYMBOLS:
        h1 = fetch_all(ex, sym)
        atr = atr_series(h1)
        print(f"{sym}: {len(h1)} کندل", flush=True)
        for k in range(ATR_N + 1, len(h1) - 1):
            if atr[k] is None:
                continue
            for d in ("LONG", "SHORT"):
                R, reason = trade(h1, atr, k, d)
                stats[d].append(R)
                reasons[d][reason] += 1
    for d in ("LONG", "SHORT"):
        Rs = stats[d]
        n = len(Rs)
        mean = sum(Rs) / n
        win = sum(1 for x in Rs if x > 0) / n
        r = reasons[d]
        lines.append(f"{d}: n={n} | میانگین R خالص={mean:+.3f} | برد={win:.1%} | TP={r['TP']} SL={r['SL']} TIMEOUT={r['TIMEOUT']}")
    lines.append("نقطه‌ی سربه‌سر تئوری (بدون کارمزد) برای R:R=۲: ۳۳.۳٪")
    text = "\n".join(lines)
    print(text)
    with open(OUT, "w", encoding="utf-8") as fh:
        fh.write(text + "\n")


if __name__ == "__main__":
    main()
