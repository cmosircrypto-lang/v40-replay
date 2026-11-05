"""
بک‌تست «بازگشت بعد از حرکت شدید روزانه» — طبق PREREG.txt
"""
import csv
import math
import os
import time
from datetime import datetime, timezone

EXCHANGE = os.environ.get("MR_EXCHANGE", "okx")
DAYS = int(os.environ.get("MR_DAYS", "365"))
FEE = float(os.environ.get("BT_FEE", "0.0006"))
D1 = 86400000
ATR_N = 14
Z_TH = 2.0
HOLD = 3
OUT_TRADES = os.environ.get("MR_OUT", "mr_trades.csv")
OUT_SUMMARY = os.environ.get("MR_SUMMARY", "mr_summary.txt")

SYMBOLS = [
    "BTC-SWAP-USDT", "ETH-SWAP-USDT", "SOL-SWAP-USDT", "XRP-SWAP-USDT",
    "BNB-SWAP-USDT", "DOGE-SWAP-USDT", "ADA-SWAP-USDT", "TRX-SWAP-USDT",
    "AVAX-SWAP-USDT", "LINK-SWAP-USDT", "DOT-SWAP-USDT", "LTC-SWAP-USDT",
    "BCH-SWAP-USDT", "TON-SWAP-USDT", "SUI-SWAP-USDT", "NEAR-SWAP-USDT",
    "APT-SWAP-USDT", "ARB-SWAP-USDT", "OP-SWAP-USDT", "ATOM-SWAP-USDT",
    "UNI-SWAP-USDT", "AAVE-SWAP-USDT", "FIL-SWAP-USDT", "INJ-SWAP-USDT",
    "TIA-SWAP-USDT", "JUP-SWAP-USDT", "ENA-SWAP-USDT", "WIF-SWAP-USDT",
    "1000PEPE-SWAP-USDT", "1000SHIB-SWAP-USDT", "WLD-SWAP-USDT", "SEI-SWAP-USDT",
    "RUNE-SWAP-USDT", "LDO-SWAP-USDT", "STX-SWAP-USDT", "IMX-SWAP-USDT",
    "HBAR-SWAP-USDT", "ICP-SWAP-USDT", "ETC-SWAP-USDT", "XLM-SWAP-USDT",
    "CRV-SWAP-USDT", "SNX-SWAP-USDT",
    "COMP-SWAP-USDT", "SUSHI-SWAP-USDT", "1INCH-SWAP-USDT", "GRT-SWAP-USDT",
    "DYDX-SWAP-USDT", "GMX-SWAP-USDT", "PENDLE-SWAP-USDT", "ONDO-SWAP-USDT",
    "JTO-SWAP-USDT", "PYTH-SWAP-USDT", "STRK-SWAP-USDT", "MANTA-SWAP-USDT",
    "1000BONK-SWAP-USDT", "1000FLOKI-SWAP-USDT", "MEME-SWAP-USDT", "ORDI-SWAP-USDT",
    "1000SATS-SWAP-USDT", "1000RATS-SWAP-USDT", "POPCAT-SWAP-USDT",
    "BRETT-SWAP-USDT", "TURBO-SWAP-USDT", "1000000MOG-SWAP-USDT", "DOGS-SWAP-USDT",
    "FET-SWAP-USDT", "TAO-SWAP-USDT",
    "AKT-SWAP-USDT", "ILV-SWAP-USDT",
    "AXS-SWAP-USDT", "SAND-SWAP-USDT", "MANA-SWAP-USDT", "GALA-SWAP-USDT",
    "ALGO-SWAP-USDT", "VET-SWAP-USDT", "EGLD-SWAP-USDT", "FLOW-SWAP-USDT",
    "KAVA-SWAP-USDT", "ROSE-SWAP-USDT", "KAS-SWAP-USDT",
    "THETA-SWAP-USDT", "CHZ-SWAP-USDT", "ENJ-SWAP-USDT", "ZIL-SWAP-USDT",
    "ONE-SWAP-USDT", "QTUM-SWAP-USDT", "IOTA-SWAP-USDT", "NEO-SWAP-USDT",
]


def make_exchange():
    import ccxt
    ex = getattr(ccxt, EXCHANGE)({"enableRateLimit": True})
    ex.load_markets()
    return ex


def to_ccxt_symbol(ex, sym):
    cand = f"{sym.split('-')[0]}/USDT:USDT"
    return cand if cand in ex.markets else None


def fetch_daily(ex, csym, since, until):
    got = {}
    cur = since
    while cur < until:
        batch = ex.fetch_ohlcv(csym, timeframe="1d", since=cur, limit=300)
        if not batch:
            break
        for b in batch:
            if since <= b[0] < until:
                got[int(b[0])] = (int(b[0]), float(b[1]), float(b[2]), float(b[3]), float(b[4]))
        nxt = int(batch[-1][0]) + D1
        if nxt <= cur:
            break
        cur = nxt
    return [got[k] for k in sorted(got)]


def iso(ms):
    return datetime.fromtimestamp(ms / 1000, timezone.utc).strftime("%Y-%m-%d")


def simulate_symbol(d):
    n = len(d)
    tr = [0.0] * n
    for i in range(n):
        _, o, h, l, c = d[i]
        tr[i] = h - l if i == 0 else max(h - l, abs(h - d[i - 1][4]), abs(l - d[i - 1][4]))
    atr = [None] * n
    for i in range(ATR_N, n):
        atr[i] = sum(tr[i - ATR_N + 1:i + 1]) / ATR_N

    trades = []
    next_ok = 0
    for i in range(ATR_N + 1, n):
        if i < next_ok or atr[i - 1] is None or atr[i] is None:
            continue
        c_prev, c = d[i - 1][4], d[i][4]
        z = (c - c_prev) / atr[i - 1]
        if z >= Z_TH:
            direction = "SHORT"
        elif z <= -Z_TH:
            direction = "LONG"
        else:
            continue
        exit_idx = min(i + HOLD, n - 1)
        if exit_idx <= i:
            continue
        entry = c
        exit_px = d[exit_idx][4]
        unit = atr[i]
        gross = (exit_px - entry) / unit if direction == "LONG" else (entry - exit_px) / unit
        net = gross - 2 * FEE * entry / unit
        trades.append({"dir": direction, "entry_ms": d[i][0], "entry": entry, "exit": exit_px,
                       "z": round(z, 3), "bars": exit_idx - i, "R": round(net, 4)})
        next_ok = exit_idx
    return trades


def run():
    ex = make_exchange()
    print(f"منبع: {EXCHANGE} | روز={DAYS} | fee={FEE} | z≥{Z_TH} | نگه‌داری={HOLD} روز")
    until = int(time.time() * 1000) // D1 * D1
    since = until - DAYS * D1
    all_trades = []
    for sym in SYMBOLS:
        csym = to_ccxt_symbol(ex, sym)
        if csym is None:
            print(f"skip {sym}: در {EXCHANGE} نیست")
            continue
        try:
            d = fetch_daily(ex, csym, since - 30 * D1, until)
        except Exception as e:
            print(f"skip {sym}: {str(e)[:150]}")
            continue
        if len(d) < 60:
            print(f"skip {sym}: کندل کم ({len(d)})")
            continue
        tr = simulate_symbol(d)
        for t in tr:
            t["symbol"] = sym
            t["entry_time"] = iso(t["entry_ms"])
        all_trades.extend(tr)
        print(f"{sym}: {len(d)} کندل | {len(tr)} معامله")

    if not all_trades:
        print("هیچ معامله‌ای ساخته نشد.")
        return
    all_trades.sort(key=lambda x: x["entry_ms"])
    keys = ["symbol", "entry_time", "dir", "entry", "exit", "z", "bars", "R"]
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
    lg = [t["R"] for t in trades if t["dir"] == "LONG"]
    sh = [t["R"] for t in trades if t["dir"] == "SHORT"]
    ok_n = n >= 100
    ok_mean = mean > 0
    ok_halves = bool(h1) and bool(h2) and sum(h1) / len(h1) > 0 and sum(h2) / len(h2) > 0
    verdict = "PASS" if (ok_n and ok_mean and ok_halves) else "FAIL"
    lines = [
        f"معاملات: {n} | برد={wins / n:.1%}",
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
