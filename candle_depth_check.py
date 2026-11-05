"""
بررسی عمق کندل OKX برای هر تایم‌فریم — فقط اندازه‌گیری، بدون استراتژی.
برای هر تایم‌فریم و نماد، بزرگ‌ترین عقب‌گرد زمانی را پیدا می‌کند که هنوز کندل برمی‌گرداند.
"""
import os
import time
import ccxt

EXCHANGE = os.environ.get("CD_EXCHANGE", "okx")
SYMS = ["BTC/USDT:USDT", "ETH/USDT:USDT", "SOL/USDT:USDT"]
TFS = {"1w": 7 * 86400000, "1d": 86400000, "4h": 4 * 3600000,
       "1h": 3600000, "30m": 1800000, "15m": 900000}
LOOKBACK_DAYS = [30, 60, 90, 120, 180, 270, 365, 545, 730, 1095, 1460, 1825, 2555, 3650]
OUT = os.environ.get("CD_OUT", "candle_depth.txt")


def probe(ex, sym, tf, days):
    step = TFS[tf]
    since = int(time.time() * 1000) - days * 86400000
    try:
        rows = ex.fetch_ohlcv(sym, timeframe=tf, since=since, limit=100)
    except Exception as e:
        return None, str(e)[:120]
    if not rows:
        return False, "خالی"
    first = int(rows[0][0])
    first_date = time.strftime("%Y-%m-%d", time.gmtime(first / 1000))
    # اگر اولین کندل نزدیک since باشد، عمق کافی است
    return abs(first - since) <= 3 * step, first_date


def main():
    ex = getattr(ccxt, EXCHANGE)({"enableRateLimit": True})
    ex.load_markets()
    lines = [f"صرافی: {EXCHANGE}", "برای هر تایم‌فریم: 'بیشترین بازه‌ی موفق' (روز)"]
    for sym in SYMS:
        if sym not in ex.markets:
            lines.append(f"{sym}: در {EXCHANGE} نیست")
            continue
        lines.append(f"--- {sym} ---")
        for tf in TFS:
            best, best_info = None, ""
            for d in LOOKBACK_DAYS:
                ok, info = probe(ex, sym, tf, d)
                if ok is True:
                    best, best_info = d, info
                else:
                    break
            if best:
                lines.append(f"{tf:>4}: حداکثر ~{best} روز (اولین کندل: {best_info})")
            else:
                lines.append(f"{tf:>4}: کمتر از ۳۰ روز یا خطا ({info})")
    text = "\n".join(lines)
    print(text)
    with open(OUT, "w", encoding="utf-8") as fh:
        fh.write(text + "\n")


if __name__ == "__main__":
    main()
