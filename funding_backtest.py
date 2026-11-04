"""
بک‌تست «فاندینگ حدی (معکوس)» — طبق PREREG.txt
"""
import csv
import math
import os
import time
from datetime import datetime, timezone

import main as M

EXCHANGE = os.environ.get("FUND_EXCHANGE", "okx").strip()
DAYS = int(os.environ.get("FUND_DAYS", "365"))
FEE = float(os.environ.get("BT_FEE", "0.0006"))
H1 = 3600000
FUND_MS = 8 * H1
D1 = 24 * H1
ATR_N = 14
WIN = 90
MIN_WIN = 30
Z_TH = 2.0
SL_ATR = 2.0
TP_ATR = 3.0
MAX_HOLD = 72
OUT_TRADES = os.environ.get("FUND_OUT", "funding_trades.csv")
OUT_SUMMARY = os.environ.get("FUND_SUMMARY", "funding_summary.txt")


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


def fetch_tf(ex, csym, since, until):
    got = {}
    cur = since
    while cur < until:
        batch = ex.fetch_ohlcv(csym, timeframe="1h", since=cur, limit=300)
        if not batch:
            break
        for b in batch:
            if since <= b[0] < until:
                got[int(b[0])] = (int(b[0]), float(b[1]), float(b[2]), float(b[3]), float(b[4]))
        nxt = int(batch[-1][0]) + H1
        if nxt <= cur:
            break
        cur = nxt
    return [got[k] for k in sorted(got)]


def fetch_funding(ex, csym, since, until):
    got = {}
    cur = since
    while cur < until:
        batch = ex.fetch_funding_rate_history(csym, since=cur, limit=100)
        if not batch:
            break
        for r in batch:
            ts = int(r["timestamp"])
            if since <= ts < until and r.get("fundingRate") is not None:
                got[ts] = float(r["fundingRate"])
        nxt = int(batch[-1]["timestamp"]) + 1
        if nxt <= cur:
            break
        cur = nxt
    return sorted(got.items())


def iso(ms):
    return datetime.fromtimestamp(ms / 1000, timezone.utc).strftime("%Y-%m-%d %H:%M")


def simulate_symbol(h1, funding):
    n = len(h1)
    idx = {r[0]: i for i, r in enumerate(h1)}
    tr = [0.0] * n
    for i in range(n):
        _, o, h, l, c = h1[i]
        tr[i] = h - l if i == 0 else max(h - l, abs(h - h1[i - 1][4]), abs(l - h1[i - 1][4]))
    atr = [None] * n
    for i in range(ATR_N, n):
        atr[i] = sum(tr[i - ATR_N + 1:i + 1]) / ATR_N

    trades = []
    next_ok = 0
    rates = []
    for ts, rate in funding:
        prev = rates[-WIN:]
        rates.append(rate)
        if len(prev) < MIN_WIN:
            continue
        mu = sum(prev) / len(prev)
        sd = math.sqrt(sum((x - mu) ** 2 for x in prev) / (len(prev) - 1))
        if sd <= 0:
            continue
        z = (rate - mu) / sd
        if z >= Z_TH:
            direction = "SHORT"
        elif z <= -Z_TH:
            direction = "LONG"
        else:
            continue
        k = idx.get(ts)
        if k is None or k < ATR_N or atr[k] is None or k >= n - 1 or ts < next_ok:
            continue

        entry = h1[k][4]
        a_k = atr[k]
        if direction == "LONG":
            sl, tp = entry - SL_ATR * a_k, entry + TP_ATR * a_k
        else:
            sl, tp = entry + SL_ATR * a_k, entry - TP_ATR * a_k
        risk = abs(entry - sl)

        exit_idx = None
        reason = None
        exit_px = None
        last = min(k + MAX_HOLD, n - 1)
        for m in range(k + 1, last + 1):
            _, _, hi, lo, _ = h1[m]
            if direction == "LONG":
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
        gross = (exit_px - entry) / risk if direction == "LONG" else (entry - exit_px) / risk
        net = gross - 2 * FEE * entry / risk
        trades.append({"dir": direction, "entry_ms": ts, "entry": entry, "sl": sl, "tp": tp,
                       "rr": round(TP_ATR / SL_ATR, 3), "reason": reason, "z": round(z, 2),
                       "bars": exit_idx - k, "R": round(net, 4)})
        next_ok = h1[exit_idx][0] + H1 * 6
    return trades


def run():
    ex = make_exchange()
    print(f"منبع: {EXCHANGE} | روز={DAYS} | fee={FEE}")
    until = int(time.time() * 1000) // FUND_MS * FUND_MS
    since = until - DAYS * D1
    all_trades = []
    span_report = []
    for sym in M.SYMBOLS:
        csym = to_ccxt_symbol(ex, sym)
        if csym is None:
            print(f"skip {sym}: در {EXCHANGE} نیست")
            continue
        try:
            funding = fetch_funding(ex, csym, since - WIN * FUND_MS, until)
            h1 = fetch_tf(ex, csym, since - 2 * D1, until)
        except Exception as e:
            print(f"skip {sym}: {str(e)[:150]}")
            continue
        if len(funding) < MIN_WIN + 10 or len(h1) < 300:
            print(f"skip {sym}: داده‌ی کم (فاندینگ {len(funding)})")
            continue
        span_report.append((funding[0][0], funding[-1][0]))
        tr = simulate_symbol(h1, funding)
        for t in tr:
            t["symbol"] = sym
            t["entry_time"] = iso(t["entry_ms"])
        all_trades.extend(tr)
        print(f"{sym}: فاندینگ {len(funding)} | {len(tr)} معامله")

    if not all_trades:
        print("هیچ معامله‌ای ساخته نشد.")
        return
    all_trades.sort(key=lambda x: x["entry_ms"])
    keys = ["symbol", "entry_time", "dir", "entry", "sl", "tp", "rr", "z", "reason", "bars", "R"]
    with open(OUT_TRADES, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=keys, extrasaction="ignore")
        w.writeheader()
        w.writerows(all_trades)
    summary(all_trades, span_report)


def summary(trades, spans):
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
    first = min(s[0] for s in spans)
    last = max(s[1] for s in spans)

    ok_n = n >= 100
    ok_mean = mean > 0
    ok_halves = bool(h1) and bool(h2) and sum(h1) / len(h1) > 0 and sum(h2) / len(h2) > 0
    verdict = "PASS" if (ok_n and ok_mean and ok_halves) else "FAIL"

    lines = [
        f"بازه‌ی فاندینگ واقعی: {iso(first)} تا {iso(last)}",
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
