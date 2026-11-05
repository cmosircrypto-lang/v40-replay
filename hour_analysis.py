"""
تحلیل توصیفی ساعت روز — طبق PREREG_HOUR.txt. بدون معیار پذیرش.
"""
import math
import os
import time
from datetime import datetime, timezone

import ccxt

EXCHANGE = os.environ.get("HOUR_EXCHANGE", "okx")
H1 = 3600000
START = 1636156800000  # 2021-11-06 UTC
ATR_N = 14
HORIZONS = [4, 12]
SYMBOLS = ["BTC/USDT:USDT", "ETH/USDT:USDT", "SOL/USDT:USDT"]
OUT = os.environ.get("HOUR_OUT", "hour_summary.txt")


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


def tstat(xs):
    n = len(xs)
    if n < 2:
        return float("nan")
    m = sum(xs) / n
    sd = math.sqrt(sum((x - m) ** 2 for x in xs) / (n - 1))
    return m / (sd / math.sqrt(n)) if sd > 0 else float("nan")


def main():
    ex = getattr(ccxt, EXCHANGE)({"enableRateLimit": True})
    ex.load_markets()
    # samples[H][hour] = list of (time_ms, f)
    samples = {H: {h: [] for h in range(24)} for H in HORIZONS}
    for sym in SYMBOLS:
        h1 = fetch_all(ex, sym)
        atr = atr_series(h1)
        print(f"{sym}: {len(h1)} کندل", flush=True)
        for k in range(ATR_N, len(h1)):
            if atr[k] is None:
                continue
            hour = datetime.fromtimestamp(h1[k][0] / 1000, timezone.utc).hour
            for H in HORIZONS:
                if k + H >= len(h1):
                    continue
                f = (h1[k + H][4] - h1[k][4]) / atr[k]
                samples[H][hour].append((h1[k][0], f))

    lines = [f"تحلیل ساعت روز | {EXCHANGE} 1H | BTC/ETH/SOL | بدون کارمزد | f = حرکت بر حسب ATR"]
    for H in HORIZONS:
        lines.append(f"--- افق {H} ساعت ---")
        lines.append("ساعت UTC | n | میانگین کل | t کل | میانگین نیمه‌ی ۱ | میانگین نیمه‌ی ۲")
        all_t = sorted(t for h in range(24) for t, _ in samples[H][h])
        med = all_t[len(all_t) // 2] if all_t else 0
        for h in range(24):
            data = samples[H][h]
            xs = [f for _, f in data]
            if not xs:
                continue
            h1s = [f for t, f in data if t < med]
            h2s = [f for t, f in data if t >= med]
            m = sum(xs) / len(xs)
            m1 = sum(h1s) / len(h1s) if h1s else float("nan")
            m2 = sum(h2s) / len(h2s) if h2s else float("nan")
            lines.append(f"{h:>7} | {len(xs):>6} | {m:+.4f} | {tstat(xs):+.2f} | {m1:+.4f} | {m2:+.4f}")
    text = "\n".join(lines)
    print(text)
    with open(OUT, "w", encoding="utf-8") as fh:
        fh.write(text + "\n")


if __name__ == "__main__":
    main()
