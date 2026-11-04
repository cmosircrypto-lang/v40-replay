"""
بک‌تست مومنتوم مقطعی — طبق PREREG.txt
  هر HOLD روز: امتیاز = بازده LOOKBACK روزه؛ K نماد بالا LONG، K نماد پایین SHORT.
  بازده هفتگی = میانگین بازده خالص ۲K پا.
اجرا: کنار main.py ریپو (برای SYMBOLS و create_exchange در حالت toobit).
"""
import csv
import math
import os
import time
from datetime import datetime, timezone

import main as M

EXCHANGE = os.environ.get("MOM_EXCHANGE", "okx")
DAYS = int(os.environ.get("MOM_DAYS", "730"))
LOOKBACK = int(os.environ.get("MOM_LOOKBACK", "30"))   # پیش‌فرض ثبت‌شده
K = int(os.environ.get("MOM_K", "5"))                   # پیش‌فرض ثبت‌شده
HOLD = int(os.environ.get("MOM_HOLD", "7"))             # پیش‌فرض ثبت‌شده
FEE = float(os.environ.get("BT_FEE", "0.0006"))
D1 = 86400000
OUT_WEEKS = os.environ.get("MOM_OUT", "momentum_weeks.csv")
OUT_SUMMARY = os.environ.get("MOM_SUMMARY", "momentum_summary.txt")


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


def fetch_daily_closes(ex, csym, since, until):
    """ts -> close برای کندل‌های بسته‌شده‌ی روزانه در بازه‌ی [since, until)."""
    out = {}
    cur = since
    while cur < until:
        batch = ex.fetch_ohlcv(csym, timeframe="1d", since=cur, limit=300)
        if not batch:
            break
        for b in batch:
            if since <= b[0] < until:
                out[int(b[0])] = float(b[4])
        nxt = int(batch[-1][0]) + D1
        if nxt <= cur:
            break
        cur = nxt
    return out


def iso(ms):
    return datetime.fromtimestamp(ms / 1000, timezone.utc).strftime("%Y-%m-%d")


def run():
    ex = make_exchange()
    print(f"منبع: {EXCHANGE} | LOOKBACK={LOOKBACK} K={K} HOLD={HOLD} | روز={DAYS} | fee={FEE}")
    until = int(time.time() * 1000) // D1 * D1          # فقط کندل‌های بسته‌شده
    start = until - DAYS * D1
    since = start - (LOOKBACK + 2) * D1

    series = {}
    for sym in M.SYMBOLS:
        csym = to_ccxt_symbol(ex, sym)
        if csym is None:
            print(f"skip {sym}: در {EXCHANGE} نیست")
            continue
        try:
            closes = fetch_daily_closes(ex, csym, since, until)
        except Exception as e:
            print(f"skip {sym}: {str(e)[:150]}")
            continue
        if len(closes) < LOOKBACK + HOLD + 5:
            print(f"skip {sym}: داده‌ی کم ({len(closes)})")
            continue
        series[sym] = closes
    print(f"نمادهای قابل استفاده: {len(series)}")
    if len(series) < 2 * K:
        print("تعداد نماد کافی نیست.")
        return

    rows = []
    for t in range(start, until - HOLD * D1, HOLD * D1):
        scores = {}
        for sym, c in series.items():
            p0 = c.get(t - LOOKBACK * D1)
            p1 = c.get(t)
            p2 = c.get(t + HOLD * D1)
            if p0 is None or p1 is None or p2 is None or p0 <= 0 or p1 <= 0:
                continue
            scores[sym] = (p1 / p0 - 1, p1, p2)
        if len(scores) < 2 * K:
            continue
        ranked = sorted(scores, key=lambda s: scores[s][0])
        shorts, longs = ranked[:K], ranked[-K:]
        legs_net = []
        legs_gross = []
        for s in longs:
            r = scores[s][2] / scores[s][1] - 1
            legs_gross.append(r)
            legs_net.append(r - 2 * FEE)
        for s in shorts:
            r = scores[s][2] / scores[s][1] - 1
            legs_gross.append(-r)
            legs_net.append(-r - 2 * FEE)
        rows.append({
            "week_start": iso(t),
            "universe": len(scores),
            "longs": " ".join(longs),
            "shorts": " ".join(shorts),
            "long_net": round(sum(legs_net[:K]) / K, 6),
            "short_net": round(sum(legs_net[K:]) / K, 6),
            "week_net": round(sum(legs_net) / len(legs_net), 6),
            "week_gross": round(sum(legs_gross) / len(legs_gross), 6),
        })

    if not rows:
        print("هیچ دوره‌ی معتبری ساخته نشد.")
        return
    with open(OUT_WEEKS, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    summary(rows)


def summary(rows):
    net = [r["week_net"] for r in rows]
    gross = [r["week_gross"] for r in rows]
    n = len(net)
    mean = sum(net) / n
    var = sum((x - mean) ** 2 for x in net) / (n - 1) if n > 1 else 0.0
    sd = math.sqrt(var)
    se = sd / math.sqrt(n) if n > 1 else float("nan")
    t = mean / se if se and se > 0 else float("nan")
    sharpe = mean / sd * math.sqrt(52) if sd > 0 else float("nan")
    eq, peak, mdd = 1.0, 1.0, 0.0
    for x in net:
        eq *= 1 + x
        peak = max(peak, eq)
        mdd = min(mdd, eq / peak - 1)
    half = n // 2
    h1 = [r["week_net"] for r in rows[:half]]
    h2 = [r["week_net"] for r in rows[half:]]
    lng = sum(r["long_net"] for r in rows) / n
    sht = sum(r["short_net"] for r in rows) / n
    hit = sum(1 for x in net if x > 0) / n

    ok_n = n >= 50
    ok_mean = mean > 0
    ok_t = (not math.isnan(t)) and t >= 2.0
    ok_halves = bool(h1) and bool(h2) and sum(h1) / len(h1) > 0 and sum(h2) / len(h2) > 0
    verdict = "PASS" if (ok_n and ok_mean and ok_t and ok_halves) else "FAIL"

    lines = [
        f"هفته‌ها: {n} | نمادها (میانه): {sorted(r['universe'] for r in rows)[n // 2]}",
        f"میانگین هفتگی خالص: {mean * 100:+.3f}% | ناخالص: {sum(gross) / n * 100:+.3f}%",
        f"انحراف معیار: {sd * 100:.3f}% | t-stat: {t:.2f} | Sharpe سالانه: {sharpe:.2f}",
        f"بازده ترکیبی خالص: {(eq - 1) * 100:+.1f}% | MaxDD: {mdd * 100:.1f}%",
        f"پای LONG (میانگین هفتگی خالص): {lng * 100:+.3f}% | پای SHORT: {sht * 100:+.3f}%",
        f"درصد هفته‌های مثبت: {hit:.1%}",
        f"نیمه‌ی اول: {len(h1)} هفته، میانگین {sum(h1) / max(len(h1), 1) * 100:+.3f}%",
        f"نیمه‌ی دوم: {len(h2)} هفته، میانگین {sum(h2) / max(len(h2), 1) * 100:+.3f}%",
        f"معیار از قبل: n≥50 [{ok_n}] | میانگین>0 [{ok_mean}] | t≥2 [{ok_t}] | هر دو نیمه>0 [{ok_halves}]",
        f"نتیجه: {verdict}",
    ]
    text = "\n".join(lines)
    print(text)
    with open(OUT_SUMMARY, "w", encoding="utf-8") as fh:
        fh.write(text + "\n")


if __name__ == "__main__":
    run()
