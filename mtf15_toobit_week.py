"""
اجرای بازه‌ی اخیر (۷ روز) با قواعد ثابت mtf15 روی داده‌ی Toobit (همان ccxt.toobit ربات) و نمادهای فهرست ربات.
"""
import bisect
import csv
import math
import os
import time
from datetime import datetime, timezone

import ccxt

EXCHANGE = os.environ.get("MTF15_EXCHANGE", "toobit")
DAYS = int(os.environ.get("MTF15_DAYS", "7"))
FEE = float(os.environ.get("BT_FEE", "0.0006"))
M15, H1, H4, D1 = 900000, 3600000, 14400000, 86400000
WARM = 60 * D1
BASES = [
    "BTC",
    "ETH",
    "SOL",
    "XRP",
    "BNB",
    "DOGE",
    "ADA",
    "TRX",
    "AVAX",
    "LINK",
    "DOT",
    "LTC",
    "BCH",
    "TON",
    "SUI",
    "NEAR",
    "APT",
    "ARB",
    "OP",
    "ATOM",
    "UNI",
    "AAVE",
    "FIL",
    "INJ",
    "TIA",
    "JUP",
    "ENA",
    "WIF",
    "1000PEPE",
    "1000SHIB",
    "WLD",
    "SEI",
    "RUNE",
    "LDO",
    "STX",
    "IMX",
    "HBAR",
    "ICP",
    "ETC",
    "XLM",
    "CRV",
    "SNX",
    "COMP",
    "SUSHI",
    "1INCH",
    "GRT",
    "DYDX",
    "GMX",
    "PENDLE",
    "ONDO",
    "JTO",
    "PYTH",
    "STRK",
    "MANTA",
    "1000BONK",
    "1000FLOKI",
    "MEME",
    "ORDI",
    "1000SATS",
    "1000RATS",
    "POPCAT",
    "BRETT",
    "TURBO",
    "1000000MOG",
    "DOGS",
    "FET",
    "TAO",
    "AKT",
    "ILV",
    "AXS",
    "SAND",
    "MANA",
    "GALA",
    "ALGO",
    "VET",
    "EGLD",
    "FLOW",
    "KAVA",
    "ROSE",
    "KAS",
    "THETA",
    "CHZ",
    "ENJ",
    "ZIL",
    "ONE",
    "QTUM",
    "IOTA",
    "NEO",
]
SYMBOLS = [f"{b}-SWAP-USDT" for b in BASES]
EMA_F, EMA_S = 20, 50
RSI_N, ATR_N, VOL_N = 14, 14, 20
VOL_MULT = 1.5
SL_ATR, TP_ATR, MAX_HOLD = 1.5, 3.0, 16
OUT_TRADES = os.environ.get("MTF15_OUT", "mtf15_toobit_week_trades.csv")
OUT_SUMMARY = os.environ.get("MTF15_SUMMARY", "mtf15_toobit_week_summary.txt")


def fetch(ex, sym, tf, step, since, until):
    rows = {}
    cur = since
    while cur < until:
        batch = ex.fetch_ohlcv(sym, timeframe=tf, since=cur, limit=100)
        if not batch:
            break
        for b in batch:
            t = int(b[0])
            if since <= t < until:
                rows[t] = (t, float(b[1]), float(b[2]), float(b[3]), float(b[4]), float(b[5]))
        nxt = int(batch[-1][0]) + step
        if nxt <= cur:
            break
        cur = nxt
    return [rows[k] for k in sorted(rows)]


def ema_list(vals, n):
    out = [None] * len(vals)
    if len(vals) < n:
        return out
    k = 2 / (n + 1)
    e = vals[0]
    for i, v in enumerate(vals):
        e = v if i == 0 else e + k * (v - e)
        if i >= n - 1:
            out[i] = e
    return out


def rsi_list(closes, n):
    out = [None] * len(closes)
    if len(closes) <= n:
        return out
    g = l = 0.0
    for i in range(1, n + 1):
        d = closes[i] - closes[i - 1]
        g += max(d, 0)
        l += max(-d, 0)
    ag, al = g / n, l / n
    out[n] = 100.0 if al == 0 else 100 - 100 / (1 + ag / al)
    for i in range(n + 1, len(closes)):
        d = closes[i] - closes[i - 1]
        ag = (ag * (n - 1) + max(d, 0)) / n
        al = (al * (n - 1) + max(-d, 0)) / n
        out[i] = 100.0 if al == 0 else 100 - 100 / (1 + ag / al)
    return out


def atr_list(rows, n):
    tr = [0.0] * len(rows)
    for i, r in enumerate(rows):
        h, l = r[2], r[3]
        tr[i] = h - l if i == 0 else max(h - l, abs(h - rows[i - 1][4]), abs(l - rows[i - 1][4]))
    out = [None] * len(rows)
    for i in range(n, len(rows)):
        out[i] = sum(tr[i - n + 1:i + 1]) / n
    return out


def trend_series(rows):
    """بازه‌ی پایان هر کندل و مقدار روند (+1/−1/None)."""
    closes = [r[4] for r in rows]
    e1, e2 = ema_list(closes, EMA_F), ema_list(closes, EMA_S)
    ends, vals = [], []
    for i, r in enumerate(rows):
        ends.append(r[0] + (rows[1][0] - rows[0][0] if len(rows) > 1 else 0))
        if e1[i] is None or e2[i] is None:
            vals.append(None)
        else:
            vals.append(1 if e1[i] > e2[i] else (-1 if e1[i] < e2[i] else 0))
    return ends, vals


def trend_at(ends, vals, t_dec):
    j = bisect.bisect_right(ends, t_dec) - 1
    return vals[j] if j >= 0 else None


def simulate(m5, d1, h4, h1, start_ms):
    closes = [r[4] for r in m5]
    rsi = rsi_list(closes, RSI_N)
    atr = atr_list(m5, ATR_N)
    vols = [r[5] for r in m5]
    tr_d = trend_series(d1)
    tr_h4 = trend_series(h4)
    tr_h1 = trend_series(h1)

    trades = []
    next_ok = 0
    for k in range(VOL_N + 1, len(m5)):
        t = m5[k][0]
        if t < start_ms or k < next_ok:
            continue
        if rsi[k] is None or rsi[k - 1] is None or atr[k] is None:
            continue
        t_dec = t + M15
        td = trend_at(*tr_d, t_dec)
        th4 = trend_at(*tr_h4, t_dec)
        th1 = trend_at(*tr_h1, t_dec)
        if td is None or th4 is None or th1 is None:
            continue
        if td == th4 == th1 == 1:
            direction = "LONG"
            trig = rsi[k - 1] <= 50 < rsi[k]
        elif td == th4 == th1 == -1:
            direction = "SHORT"
            trig = rsi[k - 1] >= 50 > rsi[k]
        else:
            continue
        if not trig:
            continue
        sma = sum(vols[k - VOL_N:k]) / VOL_N
        if sma <= 0 or vols[k] < VOL_MULT * sma:
            continue

        entry = closes[k]
        a = atr[k]
        risk = SL_ATR * a
        if direction == "LONG":
            sl, tp = entry - risk, entry + TP_ATR * a
        else:
            sl, tp = entry + risk, entry - TP_ATR * a

        exit_idx, reason, exit_px = None, None, None
        last = min(k + MAX_HOLD, len(m5) - 1)
        for j in range(k + 1, last + 1):
            _, _, hj, lj, _ = m5[j][0], m5[j][1], m5[j][2], m5[j][3], m5[j][4]
            if direction == "LONG":
                if lj <= sl:
                    reason, exit_px, exit_idx = "SL", sl, j
                    break
                if hj >= tp:
                    reason, exit_px, exit_idx = "TP", tp, j
                    break
            else:
                if hj >= sl:
                    reason, exit_px, exit_idx = "SL", sl, j
                    break
                if lj <= tp:
                    reason, exit_px, exit_idx = "TP", tp, j
                    break
        if exit_idx is None:
            reason, exit_px, exit_idx = "TIMEOUT", closes[last], last
        gross = (exit_px - entry) / risk if direction == "LONG" else (entry - exit_px) / risk
        net = gross - 2 * FEE * entry / risk
        trades.append({"dir": direction, "entry_ms": t, "entry": entry, "reason": reason,
                       "bars": exit_idx - k, "R_gross": round(gross, 4), "R_net": round(net, 4)})
        next_ok = exit_idx + 1
    return trades


def iso(ms):
    return datetime.fromtimestamp(ms / 1000, timezone.utc).strftime("%Y-%m-%d %H:%M")


def run():
    ex = getattr(ccxt, EXCHANGE)({"enableRateLimit": True})
    ex.load_markets()
    now = int(time.time() * 1000)
    start_ms = now - DAYS * D1
    since = start_ms - WARM
    all_trades = []
    for sym in SYMBOLS:
        if sym not in ex.markets:
            print(f"skip {sym}: نیست", flush=True)
            continue
        d1 = fetch(ex, sym, "1d", D1, since, now)
        h4 = fetch(ex, sym, "4h", H4, since, now)
        h1 = fetch(ex, sym, "1h", H1, since, now)
        m5 = fetch(ex, sym, "15m", M15, since, now)
        depth = iso(m5[0][0]) if m5 else "-"
        print(f"{sym}: 15m={len(m5)} (از {depth}) | 1h={len(h1)} | 4h={len(h4)} | 1d={len(d1)}", flush=True)
        if len(m5) < 500:
            print(f"skip {sym}: داده‌ی ۵ دقیقه کم", flush=True)
            continue
        tr = simulate(m5, d1, h4, h1, start_ms)
        for t in tr:
            t["symbol"] = sym
            t["entry_time"] = iso(t["entry_ms"])
        all_trades.extend(tr)
        print(f"  {len(tr)} معامله", flush=True)

    if not all_trades:
        print("هیچ معامله‌ای ساخته نشد.")
        with open(OUT_SUMMARY, "w", encoding="utf-8") as fh:
            fh.write("هیچ معامله‌ای ساخته نشد.\n")
        return
    all_trades.sort(key=lambda x: x["entry_ms"])
    keys = ["symbol", "entry_time", "dir", "entry", "reason", "bars", "R_gross", "R_net"]
    with open(OUT_TRADES, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=keys, extrasaction="ignore")
        w.writeheader()
        w.writerows(all_trades)
    summary(all_trades)


def _stats(xs):
    n = len(xs)
    if n == 0:
        return "n=0"
    m = sum(xs) / n
    return f"n={n} میانگین={m:+.3f} برد={sum(1 for x in xs if x > 0) / n:.1%}"


def summary(trades):
    G = [t["R_gross"] for t in trades]
    N = [t["R_net"] for t in trades]
    n = len(G)
    mean = sum(G) / n
    sd = math.sqrt(sum((x - mean) ** 2 for x in G) / (n - 1)) if n > 1 else 0.0
    t_stat = mean / (sd / math.sqrt(n)) if sd > 0 else float("nan")
    med = trades[n // 2]["entry_ms"]
    h1g = [t["R_gross"] for t in trades if t["entry_ms"] < med]
    h2g = [t["R_gross"] for t in trades if t["entry_ms"] >= med]
    reasons = {r: sum(1 for t in trades if t["reason"] == r) for r in ("TP", "SL", "TIMEOUT")}
    ok_n = n >= 100
    ok_mean = mean > 0
    ok_halves = bool(h1g) and bool(h2g) and sum(h1g) / len(h1g) > 0 and sum(h2g) / len(h2g) > 0
    verdict = "PASS" if (ok_n and ok_mean and ok_halves) else "FAIL"
    lines = [
        f"معاملات: {n} | TP={reasons['TP']} SL={reasons['SL']} TIMEOUT={reasons['TIMEOUT']}",
        f"[ناخالص] میانگین R={mean:+.3f} | t-stat={t_stat:.2f} | مجموع={sum(G):+.1f}",
        f"[ناخالص] نیمه‌ی اول: {len(h1g)} معامله، میانگین {sum(h1g) / max(len(h1g), 1):+.3f} | "
        f"نیمه‌ی دوم: {len(h2g)} معامله، میانگین {sum(h2g) / max(len(h2g), 1):+.3f}",
        f"[ناخالص] LONG: {_stats([t['R_gross'] for t in trades if t['dir'] == 'LONG'])} | "
        f"SHORT: {_stats([t['R_gross'] for t in trades if t['dir'] == 'SHORT'])}",
        f"[اطلاعاتی، خالص] میانگین R خالص={sum(N) / n:+.3f}",
        f"معیار از قبل (ناخالص): n≥100 [{ok_n}] | میانگین>0 [{ok_mean}] | هر دو نیمه>0 [{ok_halves}]",
        f"نتیجه: {verdict}",
    ]
    text = "\n".join(lines)
    print(text)
    with open(OUT_SUMMARY, "w", encoding="utf-8") as fh:
        fh.write(text + "\n")


if __name__ == "__main__":
    run()
