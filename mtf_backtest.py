"""
بک‌تست «هم‌راستایی روند BTC + کراس ۱ساعته» — طبق PREREG.txt
"""
import csv
import math
import os
import time
from datetime import datetime, timezone

import main as M

EXCHANGE = os.environ.get("MTF_EXCHANGE", "okx")
DAYS = int(os.environ.get("MTF_DAYS", "365"))
FEE = float(os.environ.get("BT_FEE", "0.0006"))
H1 = 3600000
H4 = 4 * H1
D1 = 24 * H1
BTC = "BTC-SWAP-USDT"
ATR_N = 14
VOL_N = 20
VOL_MULT = 1.5
SL_ATR = 1.5
TP_ATR = 3.0
MAX_HOLD = 48
COOLDOWN = 6
OUT_TRADES = os.environ.get("MTF_OUT", "mtf_trades.csv")
OUT_SUMMARY = os.environ.get("MTF_SUMMARY", "mtf_summary.txt")


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
    step = {"1h": H1, "4h": H4, "1d": D1}[tf]
    got = {}
    cur = since
    while cur < until:
        batch = ex.fetch_ohlcv(csym, timeframe=tf, since=cur, limit=300)
        if not batch:
            break
        for b in batch:
            if since <= b[0] < until:
                got[int(b[0])] = (int(b[0]), float(b[1]), float(b[2]), float(b[3]), float(b[4]), float(b[5]))
        nxt = int(batch[-1][0]) + step
        if nxt <= cur:
            break
        cur = nxt
    return [got[k] for k in sorted(got)]


def iso(ms):
    return datetime.fromtimestamp(ms / 1000, timezone.utc).strftime("%Y-%m-%d %H:%M")


def ema_list(vals, n):
    a = 2 / (n + 1)
    out = [None] * len(vals)
    e = None
    for i, v in enumerate(vals):
        e = v if e is None else e + a * (v - e)
        out[i] = e if i >= n else None
    return out


def btc_direction_map(b1, b4, bd):
    """ts (ساعتی) -> جهت هم‌راستا (LONG/SHORT) یا None."""
    e4 = ema_list([r[4] for r in b4], 50)
    e20_4 = ema_list([r[4] for r in b4], 20)
    ed50 = ema_list([r[4] for r in bd], 50)
    ed20 = ema_list([r[4] for r in bd], 20)
    e9 = ema_list([r[4] for r in b1], 21)
    e9f = ema_list([r[4] for r in b1], 9)
    out = {}
    p4 = -1
    pd = -1
    for i, r in enumerate(b1):
        t = r[0]
        while pd + 1 < len(bd) and bd[pd + 1][0] + D1 <= t:
            pd += 1
        while p4 + 1 < len(b4) and b4[p4 + 1][0] + H4 <= t:
            p4 += 1
        if pd < 50 or p4 < 50 or e9[i] is None or e9f[i] is None:
            out[t] = None
            continue
        d_dir = "LONG" if ed20[pd] > ed50[pd] else ("SHORT" if ed20[pd] < ed50[pd] else None)
        f_dir = "LONG" if e20_4[p4] > e4[p4] else ("SHORT" if e20_4[p4] < e4[p4] else None)
        h_dir = "LONG" if e9f[i] > e9[i] else ("SHORT" if e9f[i] < e9[i] else None)
        out[t] = d_dir if (d_dir and d_dir == f_dir == h_dir) else None
    return out


def simulate_symbol(h1, dir_map):
    n = len(h1)
    e9 = ema_list([r[4] for r in h1], 9)
    e21 = ema_list([r[4] for r in h1], 21)
    tr = [0.0] * n
    for i in range(n):
        _, o, h, l, c, v = h1[i]
        tr[i] = h - l if i == 0 else max(h - l, abs(h - h1[i - 1][4]), abs(l - h1[i - 1][4]))
    atr = [None] * n
    for i in range(ATR_N, n):
        atr[i] = sum(tr[i - ATR_N + 1:i + 1]) / ATR_N

    trades = []
    next_ok = 0
    for k in range(max(ATR_N, VOL_N, 25), n - 1):
        if k < next_ok or e9[k] is None or e21[k] is None or e9[k - 1] is None or e21[k - 1] is None:
            continue
        d = dir_map.get(h1[k][0])
        if d is None or atr[k] is None:
            continue
        if d == "LONG":
            cross = e9[k - 1] <= e21[k - 1] and e9[k] > e21[k]
        else:
            cross = e9[k - 1] >= e21[k - 1] and e9[k] < e21[k]
        if not cross:
            continue
        vol_avg = sum(h1[j][5] for j in range(k - VOL_N, k)) / VOL_N
        if vol_avg <= 0 or h1[k][5] < VOL_MULT * vol_avg:
            continue

        entry = h1[k][4]
        a_k = atr[k]
        if d == "LONG":
            sl = entry - SL_ATR * a_k
            tp = entry + TP_ATR * a_k
        else:
            sl = entry + SL_ATR * a_k
            tp = entry - TP_ATR * a_k
        risk = abs(entry - sl)

        exit_idx = None
        reason = None
        exit_px = None
        last = min(k + MAX_HOLD, n - 1)
        for m in range(k + 1, last + 1):
            _, _, hi, lo, _, _ = h1[m]
            if d == "LONG":
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
        gross = (exit_px - entry) / risk if d == "LONG" else (entry - exit_px) / risk
        net = gross - 2 * FEE * entry / risk
        trades.append({"dir": d, "entry_ms": h1[k][0], "entry": entry, "sl": sl, "tp": tp,
                       "rr": round(TP_ATR / SL_ATR, 3), "reason": reason,
                       "bars": exit_idx - k, "R": round(net, 4)})
        next_ok = exit_idx + COOLDOWN
    return trades


def run():
    ex = make_exchange()
    print(f"منبع: {EXCHANGE} | روز={DAYS} | fee={FEE}")
    until = int(time.time() * 1000) // H1 * H1
    since = until - DAYS * D1

    b1 = fetch_tf(ex, to_ccxt_symbol(ex, BTC) or BTC, "1h", since - 5 * D1, until)
    b4 = fetch_tf(ex, to_ccxt_symbol(ex, BTC) or BTC, "4h", since - 30 * D1, until)
    bd = fetch_tf(ex, to_ccxt_symbol(ex, BTC) or BTC, "1d", since - 120 * D1, until)
    dir_map = btc_direction_map(b1, b4, bd)
    print(f"BTC: {len(b1)} ساعت، جهت هم‌راستا در {sum(1 for v in dir_map.values() if v)} کندل")

    all_trades = []
    for sym in M.SYMBOLS:
        csym = to_ccxt_symbol(ex, sym)
        if csym is None:
            print(f"skip {sym}: در {EXCHANGE} نیست")
            continue
        try:
            h1 = fetch_tf(ex, csym, "1h", since - 5 * D1, until)
        except Exception as e:
            print(f"skip {sym}: {str(e)[:150]}")
            continue
        if len(h1) < 300:
            print(f"skip {sym}: داده‌ی کم")
            continue
        tr = simulate_symbol(h1, dir_map)
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


def stats(trades):
    Rs = [t["R"] for t in trades]
    n = len(Rs)
    if n == 0:
        return None
    mean = sum(Rs) / n
    sd = math.sqrt(sum((x - mean) ** 2 for x in Rs) / (n - 1)) if n > 1 else 0.0
    t_stat = mean / (sd / math.sqrt(n)) if sd > 0 else float("nan")
    return n, mean, t_stat, sum(Rs)


def summary(trades):
    n, mean, t_stat, total = stats(trades)
    med = trades[n // 2]["entry_ms"]
    h1 = [t["R"] for t in trades if t["entry_ms"] < med]
    h2 = [t["R"] for t in trades if t["entry_ms"] >= med]
    wins = sum(1 for t in trades if t["R"] > 0)
    reasons = {r: sum(1 for t in trades if t["reason"] == r) for r in ("TP", "SL", "TIMEOUT")}
    btc = [t for t in trades if t["symbol"] == BTC]
    bs = stats(btc)

    ok_n = n >= 100
    ok_mean = mean > 0
    ok_halves = bool(h1) and bool(h2) and sum(h1) / len(h1) > 0 and sum(h2) / len(h2) > 0
    verdict = "PASS" if (ok_n and ok_mean and ok_halves) else "FAIL"

    lines = [
        f"جهان نمادها — معاملات: {n} | TP={reasons['TP']} SL={reasons['SL']} TIMEOUT={reasons['TIMEOUT']} | برد={wins / n:.1%}",
        f"R کل خالص: {total:+.1f} | میانگین: {mean:+.3f} | t-stat: {t_stat:.2f}",
        f"نیمه‌ی اول: {len(h1)} معامله، میانگین {sum(h1) / max(len(h1), 1):+.3f}  |  "
        f"نیمه‌ی دوم: {len(h2)} معامله، میانگین {sum(h2) / max(len(h2), 1):+.3f}",
    ]
    if bs:
        lines.append(f"فقط BTC (اطلاعاتی): {bs[0]} معامله، میانگین {bs[1]:+.3f}، R کل {bs[3]:+.1f}")
    lines += [
        f"معیار از قبل: n≥100 [{ok_n}] | میانگین>0 [{ok_mean}] | هر دو نیمه>0 [{ok_halves}]",
        f"نتیجه: {verdict}",
    ]
    text = "\n".join(lines)
    print(text)
    with open(OUT_SUMMARY, "w", encoding="utf-8") as fh:
        fh.write(text + "\n")


if __name__ == "__main__":
    run()
