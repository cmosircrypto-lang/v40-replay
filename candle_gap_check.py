"""
بررسی گپ کندل OKX برای ۱۵ دقیقه و ۱ ساعته — فقط اندازه‌گیری.
از ابتدای داده تا امروز همه‌ی کندل‌ها را می‌گیرد و گپ‌ها (کندل‌های جاافتاده) را می‌شمارد.
"""
import os
import time
from collections import Counter
import ccxt

EXCHANGE = os.environ.get("GAP_EXCHANGE", "okx")
SYMS = ["BTC/USDT:USDT", "ETH/USDT:USDT", "SOL/USDT:USDT"]
TFS = {"15m": 900000, "1h": 3600000}
START = int(os.environ.get("GAP_START_MS", "1635897600000"))  # 2021-11-03 UTC
OUT = os.environ.get("GAP_OUT", "candle_gap.txt")


def fetch_all(ex, sym, tf, step):
    rows = {}
    cur = START
    end = int(time.time() * 1000)
    calls = 0
    print(f"شروع {sym} {tf}", flush=True)
    while cur < end:
        batch = ex.fetch_ohlcv(sym, timeframe=tf, since=cur, limit=100)
        calls += 1
        if calls % 100 == 0:
            print(f"  {sym} {tf}: {calls} درخواست، رسیده به {iso(cur)}", flush=True)
        if not batch:
            break
        for b in batch:
            rows[int(b[0])] = b
        nxt = int(batch[-1][0]) + step
        if nxt <= cur:
            break
        cur = nxt
    print(f"پایان {sym} {tf}: {len(rows)} کندل در {calls} درخواست", flush=True)
    return sorted(rows)


def analyze(ts, step):
    gaps = []
    for a, b in zip(ts, ts[1:]):
        d = b - a
        if d != step:
            gaps.append((a, (d // step) - 1))
    missing = sum(m for _, m in gaps)
    sizes = Counter(m for _, m in gaps)
    worst = max(gaps, key=lambda g: g[1]) if gaps else None
    return len(ts), len(gaps), missing, sizes, worst


def iso(ms):
    return time.strftime("%Y-%m-%d %H:%M", time.gmtime(ms / 1000))


def main():
    ex = getattr(ccxt, EXCHANGE)({"enableRateLimit": True})
    ex.load_markets()
    lines = [f"صرافی: {EXCHANGE} | از {iso(START)} تا امروز"]
    for sym in SYMS:
        if sym not in ex.markets:
            lines.append(f"{sym}: در {EXCHANGE} نیست")
            continue
        for tf, step in TFS.items():
            try:
                ts = fetch_all(ex, sym, tf, step)
            except Exception as e:
                lines.append(f"{sym} {tf}: خطا {str(e)[:120]}")
                continue
            n, ng, miss, sizes, worst = analyze(ts, step)
            if n == 0:
                lines.append(f"{sym} {tf}: بدون داده")
                continue
            lines.append(f"{sym} {tf}: {n} کندل | گپ‌ها={ng} | کندل‌های جاافتاده={miss}")
            if worst:
                lines.append(f"   بزرگ‌ترین گپ: {worst[1]} کندل از {iso(worst[0])}")
            if sizes:
                lines.append(f"   توزیع اندازه‌ی گپ (تعداد کندل جاافتاده: تعداد رخداد): {dict(sorted(sizes.items())[:8])}")
    text = "\n".join(lines)
    print(text)
    with open(OUT, "w", encoding="utf-8") as fh:
        fh.write(text + "\n")


if __name__ == "__main__":
    main()
