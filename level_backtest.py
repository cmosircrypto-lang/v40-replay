"""
بک‌تست «ورود نزدیک سطح» (PDH/PDL) — طبق PREREG.txt
"""
import csv
import math
import os
import time
from datetime import datetime, timezone

import ccxt

EXCHANGE = os.environ.get("LVL_EXCHANGE", "okx")
FEE = float(os.environ.get("BT_FEE", "0.0006"))
H1 = 3600000
D1 = 86400000
START = int(os.environ.get("LVL_START_MS", "1636156800000"))  # 2021-11-06 UTC
ATR_N = 14
SL_ATR = 1.0
TP_ATR = 2.0
MAX_HOLD = 24
SYMBOLS = ["BTC/USDT:USDT", "ETH/USDT:USDT", "SOL/USDT:USDT"]
OUT_TRADES = os.environ.get("LVL_OUT", "lvl_trades.csv")
OUT_SUMMARY = os.environ.get("LVL_SUMMARY", "lvl_summary.txt")


def fetch_all(ex, sym, tf, step):
    rows = {}
    cur = START
    end = int(time.time() * 1000)
    while cur < end:
        batch = ex.fetch_ohlcv(sym, timeframe=tf, since=cur, limit=100)
        if not batch:
            break
        for b in batch:
            rows[int(b[0])] = (int(b[0]), float(b[1]), float(b[2]), float(b[3]), float(b[4]))
        nxt = int(batch[-1][0]) + step
        if nxt <= cur:
            break
        cur = nxt
    return [rows[k] for k in sorted(rows)]


def iso(ms):
    return datetime.fromtimestamp(ms / 1000, timezone.utc).strftime("%Y-%m-%d %H:%M")


def simulate(h1, daily):
    n = len(h1)
    tr = [0.0] * n
    for i in range(n):
        _, o, h, l, c = h1[i]
        tr[i] = h - l if i == 0 else max(h - l, abs(h - h1[i - 1][4]), abs(l - h1[i - 1][4]))
    atr = [None] * n
    for i in range(ATR_N, n):
        atr[i] = sum(tr[i - ATR_N + 1:i + 1]) / ATR_N

    trades = []
    touched = set()  # (day_ms, "PDL"/"PDH")
    next_ok = 0  # اندیس اولین کندلی که ورود جدید مجاز است
    for k in range(n):
        t = h1[k][0]
        day = t // D1 * D1
        prev = daily.get(day - D1)
        if prev is None or atr[k] is None:
            continue
        pdh, pdl = prev
        _, _, hi, lo, _ = h1[k]
        in_pos = k < next_ok
        hit_l = lo <= pdl <= hi and (day, "PDL") not in touched
        hit_h = lo <= pdh <= hi and (day, "PDH") not in touched
        if hit_l:
            touched.add((day, "PDL"))
        if hit_h:
            touched.add((day, "PDH"))
        if in_pos or (hit_l and hit_h):
            continue
        if hit_l:
            direction, entry = "LONG", pdl
        elif hit_h:
            direction, entry = "SHORT", pdh
        else:
            continue

        a = atr[k]
        risk = SL_ATR * a
        if direction == "LONG":
            sl, tp = entry - risk, entry + TP_ATR * a
        else:
            sl, tp = entry + risk, entry - TP_ATR * a

        exit_idx, reason, exit_px = None, None, None
        last = min(k + MAX_HOLD, n - 1)
        for j in range(k, last + 1):
            _, _, hj, lj, _ = h1[j]
            if direction == "LONG":
                if lj <= sl:
                    reason, exit_px, exit_idx = "SL", sl, j
                    break
                if j > k and hj >= tp:
                    reason, exit_px, exit_idx = "TP", tp, j
                    break
            else:
                if hj >= sl:
                    reason, exit_px, exit_idx = "SL", sl, j
                    break
                if j > k and lj <= tp:
                    reason, exit_px, exit_idx = "TP", tp, j
                    break
        if exit_idx is None:
            reason, exit_px, exit_idx = "TIMEOUT", h1[last][4], last
        gross = (exit_px - entry) / risk if direction == "LONG" else (entry - exit_px) / risk
        net = gross - 2 * FEE * entry / risk
        trades.append({"dir": direction, "entry_ms": t, "entry": entry, "sl": sl, "tp": tp,
                       "reason": reason, "bars": exit_idx - k, "R": round(net, 4)})
        next_ok = exit_idx + 1
    return trades


def run():
    ex = getattr(ccxt, EXCHANGE)({"enableRateLimit": True})
    ex.load_markets()
    all_trades = []
    for sym in SYMBOLS:
        if sym not in ex.markets:
            print(f"skip {sym}: نیست")
            continue
        h1 = fetch_all(ex, sym, "1h", H1)
        d1 = fetch_all(ex, sym, "1d", D1)
        daily = {r[0]: (r[2], r[3]) for r in d1}  # day -> (high, low)
        tr = simulate(h1, daily)
        for t in tr:
            t["symbol"] = sym
            t["entry_time"] = iso(t["entry_ms"])
        all_trades.extend(tr)
        print(f"{sym}: {len(h1)} ساعت، {len(d1)} روز | {len(tr)} معامله", flush=True)

    if not all_trades:
        print("هیچ معامله‌ای ساخته نشد.")
        return
    all_trades.sort(key=lambda x: x["entry_ms"])
    keys = ["symbol", "entry_time", "dir", "entry", "sl", "tp", "reason", "bars", "R"]
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
        f"نیمه‌ی اول: {len(h1)} معامله، میانگین {sum(h1) / max(len(h1), 1):+.3f}  |  "
        f"نیمه‌ی دوم: {len(h2)} معامله، میانگین {sum(h2) / max(len(h2), 1):+.3f}",
        f"معیار از قبل: n≥100 [{ok_n}] | میانگین>0 [{ok_mean}] | هر دو نیمه>0 [{ok_halves}]",
        f"نتیجه: {verdict}",
    ]
    text = "\n".join(lines)
    print(text)
    with open(OUT_SUMMARY, "w", encoding="utf-8") as fh:
        fh.write(text + "\n")


if __name__ == "__main__":
    run()
