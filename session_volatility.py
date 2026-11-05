"""
تحلیل توصیفی نوسان در شروع سشن‌ها (یک سال گذشته، BTC/ETH/SOL، ۱ ساعته، UTC).
بدون قاعده‌ی ورود، بدون کارمزد، بدون معیار پذیرش.
نوسان هر کندل = (high − low) / ATR14 ساعتی.
جهش شروع سشن = میانگین نوسان دو ساعت اول سشن ÷ میانگین نوسان دو ساعت قبل از شروع.
"""
import os
import time

import ccxt

EXCHANGE = os.environ.get("SESS_EXCHANGE", "okx")
H1 = 3600000
DAYS = 365
ATR_N = 14
SYMBOLS = ["BTC/USDT:USDT", "ETH/USDT:USDT", "SOL/USDT:USDT"]
# سشن‌ها: (نام، ساعت شروع UTC، ساعت پایان UTC)
SESSIONS = [("سیدنی", 21, 6), ("توکیو", 0, 9), ("لندن", 8, 17), ("نیویورک", 13, 22)]
OUT = os.environ.get("SESS_OUT", "session_summary.txt")


def fetch_year(ex, sym):
    rows = {}
    end = int(time.time() * 1000) // H1 * H1
    cur = end - DAYS * 24 * H1
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


def hour_of(ms):
    return (ms // H1) % 24


def main():
    ex = getattr(ccxt, EXCHANGE)({"enableRateLimit": True})
    ex.load_markets()
    # hour_vals[h] = list of normalized ranges
    hour_vals = {h: [] for h in range(24)}
    for sym in SYMBOLS:
        h1 = fetch_year(ex, sym)
        n = len(h1)
        tr = [0.0] * n
        for i in range(n):
            _, o, h, l, c = h1[i]
            tr[i] = h - l if i == 0 else max(h - l, abs(h - h1[i - 1][4]), abs(l - h1[i - 1][4]))
        for i in range(ATR_N, n):
            atr = sum(tr[i - ATR_N + 1:i + 1]) / ATR_N
            if atr <= 0:
                continue
            _, o, h, l, c = h1[i]
            hour_vals[hour_of(h1[i][0])].append((h - l) / atr)
        print(f"{sym}: {n} کندل", flush=True)

    avg = {h: sum(v) / len(v) for h, v in hour_vals.items() if v}
    overall = sum(avg.values()) / len(avg)
    lines = [f"نوسان ساعتی یک‌ساله | {EXCHANGE} | BTC/ETH/SOL | میانگین کل = ۱.۰۰",
             "ساعت UTC | نوسان نسبی (میانگین کل=۱)"]
    for h in range(24):
        if h in avg:
            lines.append(f"{h:>8} | {avg[h] / overall:.2f}")

    lines.append("")
    lines.append("سشن | شروع | نوسان دو ساعت اول ÷ دو ساعت قبل | نوسان میانگین کل سشن (نسبی)")
    ranking = []
    for name, start, end in SESSIONS:
        first2 = [avg[(start + k) % 24] for k in (0, 1)]
        pre2 = [avg[(start - k) % 24] for k in (1, 2)]
        jump = (sum(first2) / 2) / (sum(pre2) / 2)
        hours = []
        h = start
        while h != end:
            hours.append(h)
            h = (h + 1) % 24
        sess_mean = sum(avg[x] for x in hours) / len(hours) / overall
        ranking.append((name, start, jump, sess_mean))
        lines.append(f"{name} | {start:02d}:00 | {jump:.2f} | {sess_mean:.2f}")

    lines.append("")
    lines.append("اولویت‌بندی (بر اساس جهش شروع سشن):")
    for i, (name, start, jump, sm) in enumerate(sorted(ranking, key=lambda x: -x[2]), 1):
        lines.append(f"{i}. {name} (جهش {jump:.2f}، میانگین سشن {sm:.2f})")
    lines.append("")
    lines.append("توجه: این نسبت‌ها توصیفی‌اند. تفاوت کوچک (مثلاً ۱.۰۵) با داده‌ی یک‌ساله معنادار نیست؛ فقط بزرگ‌ترها ارزش بررسی دارند.")

    text = "\n".join(lines)
    print(text)
    with open(OUT, "w", encoding="utf-8") as fh:
        fh.write(text + "\n")


if __name__ == "__main__":
    main()
