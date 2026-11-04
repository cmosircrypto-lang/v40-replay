"""
بررسی عمق داده‌های حجم/موقعیت (فقط خواندن داده، بدون بک‌تست):
  - تاریخچه‌ی open interest
  - تاریخچه‌ی نسبت لانگ/شورت (long/short ratio) به‌عنوان جایگزین نزدیک برای جهت‌گیری بازار
برای هر صرافی و چند نماد، بازه‌ی واقعی برگشتی را گزارش می‌کند.
"""
import os
import time
from datetime import datetime, timezone

import ccxt

EXCHANGES = os.environ.get("OI_EXCHANGES", "okx,gate,kucoin,bybit").split(",")
SYMS = ["BTC/USDT:USDT", "ETH/USDT:USDT", "SOL/USDT:USDT"]
LOOKBACK_DAYS = int(os.environ.get("OI_LOOKBACK", "365"))   # Gate: حداکثر ۱۸۰ روز (در ادامه محدود می‌شود)
TIMEFRAMES = ["1h", "4h", "1d"]
OUT = os.environ.get("OI_OUT", "orderflow_depth_report.txt")
DAY = 86400000


def iso(ms):
    return datetime.fromtimestamp(ms / 1000, timezone.utc).strftime("%Y-%m-%d")


def probe(ex, method_name, sym, tf):
    method = getattr(ex, method_name)
    days = min(LOOKBACK_DAYS, 170) if ex.id == "gate" else LOOKBACK_DAYS
    since = int(time.time() * 1000) - days * DAY
    stamps = set()
    cur = since
    for _ in range(200):
        batch = method(sym, tf, since=cur, limit=100)
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
    return len(stamps), lo, hi, (hi - lo) / DAY


def check(ex, method_name, sym):
    last_err = None
    for tf in TIMEFRAMES:
        try:
            res = probe(ex, method_name, sym, tf)
        except Exception as e:
            last_err = str(e)[:120]
            continue
        if res is not None:
            n, lo, hi, days = res
            return f"{tf}: {n} نقطه | {iso(lo)} تا {iso(hi)} | {days:.0f} روز"
    return f"خطا یا داده‌ی خالی ({last_err or 'بدون داده'})"


def main():
    lines = [f"عمق داده‌های حجم/موقعیت (درخواست تا {LOOKBACK_DAYS} روز قبل؛ Gate تا ۱۷۰ روز)", ""]
    for name in EXCHANGES:
        name = name.strip()
        lines.append(f"== {name} ==")
        try:
            ex = getattr(ccxt, name)({"enableRateLimit": True})
            ex.load_markets()
        except Exception as e:
            lines.append(f"  خطا در اتصال: {str(e)[:150]}")
            lines.append("")
            continue
        for label, method_name in [
            ("open interest", "fetch_open_interest_history"),
            ("long/short ratio", "fetch_long_short_ratio_history"),
        ]:
            if not hasattr(ex, method_name):
                lines.append(f"  {label}: این صرافی در ccxt پشتیبانی نمی‌شود")
                continue
            for sym in SYMS:
                if sym not in ex.markets:
                    lines.append(f"  {label} {sym}: نماد موجود نیست")
                    continue
                lines.append(f"  {label} {sym}: {check(ex, method_name, sym)}")
        lines.append("")
    text = "\n".join(lines)
    print(text)
    with open(OUT, "w", encoding="utf-8") as fh:
        fh.write(text + "\n")


if __name__ == "__main__":
    main()
