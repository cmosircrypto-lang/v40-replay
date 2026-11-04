"""
بررسی عمق تاریخچه‌ی فاندینگ در صرافی‌ها (فقط خواندن داده، بدون بک‌تست).
برای هر صرافی و چند نماد، بازه‌ی واقعی‌ای را که API برمی‌گرداند گزارش می‌کند.
"""
import os
import time
from datetime import datetime, timezone

import ccxt

EXCHANGES = os.environ.get("DEPTH_EXCHANGES", "okx,gateio,kucoin,bybit").split(",")
SYMS = ["BTC/USDT:USDT", "ETH/USDT:USDT", "SOL/USDT:USDT", "DOGE/USDT:USDT", "XRP/USDT:USDT"]
LOOKBACK_DAYS = int(os.environ.get("DEPTH_LOOKBACK", "400"))
H8 = 8 * 3600 * 1000
OUT = os.environ.get("DEPTH_OUT", "funding_depth_report.txt")


def iso(ms):
    return datetime.fromtimestamp(ms / 1000, timezone.utc).strftime("%Y-%m-%d")


def probe(ex, sym):
    since = int(time.time() * 1000) - LOOKBACK_DAYS * 86400000
    stamps = set()
    cur = since
    for _ in range(200):
        batch = ex.fetch_funding_rate_history(sym, since=cur, limit=100)
        if not batch:
            break
        new = [int(r["timestamp"]) for r in batch if r.get("timestamp") is not None]
        before = len(stamps)
        stamps.update(new)
        if not new:
            break
        nxt = max(new) + 1
        if nxt <= cur or len(stamps) == before:
            break
        cur = nxt
    if not stamps:
        return None
    lo, hi = min(stamps), max(stamps)
    return len(stamps), lo, hi, (hi - lo) / 86400000


def main():
    lines = [f"عمق فاندینگ (درخواست تا {LOOKBACK_DAYS} روز قبل)", ""]
    for name in EXCHANGES:
        name = name.strip()
        lines.append(f"== {name} ==")
        try:
            ex = getattr(ccxt, name)({"enableRateLimit": True})
            ex.load_markets()
        except Exception as e:
            lines.append(f"  خطا در اتصال: {str(e)[:150]}")
            continue
        for sym in SYMS:
            if sym not in ex.markets:
                lines.append(f"  {sym}: نماد موجود نیست")
                continue
            try:
                res = probe(ex, sym)
            except Exception as e:
                lines.append(f"  {sym}: خطا: {str(e)[:150]}")
                continue
            if res is None:
                lines.append(f"  {sym}: داده‌ای برنگشت")
            else:
                n, lo, hi, days = res
                lines.append(f"  {sym}: {n} نقطه | {iso(lo)} تا {iso(hi)} | {days:.0f} روز")
        lines.append("")
    text = "\n".join(lines)
    print(text)
    with open(OUT, "w", encoding="utf-8") as fh:
        fh.write(text + "\n")


if __name__ == "__main__":
    main()
