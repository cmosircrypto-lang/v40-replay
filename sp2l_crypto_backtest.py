"""
بک‌تست SP2L_CRYPTO طبق PREREG_SP2L_CRYPTO.txt (توبیت، کندل ۱ دقیقه‌ای، ۸۸ ارز).
توصیفی (قبل از ثبت).
"""
import csv
import os
import statistics as st
import time

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MIN_MS = 60000
DAY_MS = 86400000
N_DAYS = 10
FEE_PCT = 0.12
EMA_P = 60
SPIKE_MULT = 1.5
P_GAP = 0.00025
MAX_SL = 0.0025
TP_R = 1.0
STAGE1_K, STAGE2_K, STAGE3_K = 5, 7, 11
STAGE1_TP, STAGE1_SL = 0.4, 0.5
STAGE2_TP = 0.25
MIN_SYM = 5
SYMBOLS = [
    "BTC-SWAP-USDT",
    "ETH-SWAP-USDT",
    "SOL-SWAP-USDT",
    "XRP-SWAP-USDT",
    "BNB-SWAP-USDT",
    "DOGE-SWAP-USDT",
    "ADA-SWAP-USDT",
    "TRX-SWAP-USDT",
    "AVAX-SWAP-USDT",
    "LINK-SWAP-USDT",
    "DOT-SWAP-USDT",
    "LTC-SWAP-USDT",
    "BCH-SWAP-USDT",
    "TON-SWAP-USDT",
    "SUI-SWAP-USDT",
    "NEAR-SWAP-USDT",
    "APT-SWAP-USDT",
    "ARB-SWAP-USDT",
    "OP-SWAP-USDT",
    "ATOM-SWAP-USDT",
    "UNI-SWAP-USDT",
    "AAVE-SWAP-USDT",
    "FIL-SWAP-USDT",
    "INJ-SWAP-USDT",
    "TIA-SWAP-USDT",
    "JUP-SWAP-USDT",
    "ENA-SWAP-USDT",
    "WIF-SWAP-USDT",
    "1000PEPE-SWAP-USDT",
    "1000SHIB-SWAP-USDT",
    "WLD-SWAP-USDT",
    "SEI-SWAP-USDT",
    "RUNE-SWAP-USDT",
    "LDO-SWAP-USDT",
    "STX-SWAP-USDT",
    "IMX-SWAP-USDT",
    "HBAR-SWAP-USDT",
    "ICP-SWAP-USDT",
    "ETC-SWAP-USDT",
    "XLM-SWAP-USDT",
    "CRV-SWAP-USDT",
    "SNX-SWAP-USDT",
    "COMP-SWAP-USDT",
    "SUSHI-SWAP-USDT",
    "1INCH-SWAP-USDT",
    "GRT-SWAP-USDT",
    "DYDX-SWAP-USDT",
    "GMX-SWAP-USDT",
    "PENDLE-SWAP-USDT",
    "ONDO-SWAP-USDT",
    "JTO-SWAP-USDT",
    "PYTH-SWAP-USDT",
    "STRK-SWAP-USDT",
    "MANTA-SWAP-USDT",
    "1000BONK-SWAP-USDT",
    "1000FLOKI-SWAP-USDT",
    "MEME-SWAP-USDT",
    "ORDI-SWAP-USDT",
    "1000SATS-SWAP-USDT",
    "1000RATS-SWAP-USDT",
    "POPCAT-SWAP-USDT",
    "BRETT-SWAP-USDT",
    "TURBO-SWAP-USDT",
    "1000000MOG-SWAP-USDT",
    "DOGS-SWAP-USDT",
    "FET-SWAP-USDT",
    "TAO-SWAP-USDT",
    "AKT-SWAP-USDT",
    "ILV-SWAP-USDT",
    "AXS-SWAP-USDT",
    "SAND-SWAP-USDT",
    "MANA-SWAP-USDT",
    "GALA-SWAP-USDT",
    "ALGO-SWAP-USDT",
    "VET-SWAP-USDT",
    "EGLD-SWAP-USDT",
    "FLOW-SWAP-USDT",
    "KAVA-SWAP-USDT",
    "ROSE-SWAP-USDT",
    "KAS-SWAP-USDT",
    "THETA-SWAP-USDT",
    "CHZ-SWAP-USDT",
    "ENJ-SWAP-USDT",
    "ZIL-SWAP-USDT",
    "ONE-SWAP-USDT",
    "QTUM-SWAP-USDT",
    "IOTA-SWAP-USDT",
    "NEO-SWAP-USDT",
]


def fetch_1m(ex, sym):
    """صفحه‌بندی به عقب با endTime تا N_DAYS روز."""
    now = int(time.time() * 1000) // MIN_MS * MIN_MS
    target = now - N_DAYS * DAY_MS
    store = {}
    end = now
    for _ in range(80):
        batch = ex.fetch_ohlcv(sym, timeframe="1m", limit=1000, params={"endTime": end})
        if not batch:
            break
        new = 0
        for b in batch:
            if b[0] not in store:
                store[b[0]] = b
                new += 1
        earliest = min(b[0] for b in batch)
        if earliest <= target or new == 0:
            break
        end = earliest - MIN_MS
    # کندل جاری را حذف کن
    bars = [store[k] for k in sorted(store) if k < now and k >= target]
    return bars


def ema_series(c, period=EMA_P):
    a = 2 / (period + 1)
    out = [c[0]]
    for x in c[1:]:
        out.append(a * x + (1 - a) * out[-1])
    return out


def run_trade(o, h, l, c, e, s, E, SL0, R):
    """s=+1 خرید، -1 فروش. e = کندل پرشدن (کندل اول معامله)."""
    n = len(c)
    fee_R = (FEE_PCT / 100) * E / R
    SL = SL0
    TP = E + s * TP_R * R
    stage = 0
    idx = e
    reason = None
    pnl = 0.0
    while idx < n:
        k = idx - e
        if k >= STAGE3_K:
            pnl = (o[idx] - E) * s
            reason = "TIME"
            break
        if k >= STAGE2_K and stage < 2:
            SL = E
            TP = E + s * STAGE2_TP * R
            stage = 2
        elif k >= STAGE1_K and stage < 1:
            SL = E - s * STAGE1_SL * R
            TP = E + s * STAGE1_TP * R
            stage = 1
        if s == 1:
            hit_sl = l[idx] <= SL
            hit_tp = h[idx] >= TP
        else:
            hit_sl = h[idx] >= SL
            hit_tp = l[idx] <= TP
        if hit_sl:
            pnl = (SL - E) * s
            reason = "SL"
            break
        if hit_tp:
            pnl = (TP - E) * s
            reason = "TP"
            break
        idx += 1
    if reason is None:
        pnl = (c[-1] - E) * s
        reason = "END"
        idx = n - 1
    return pnl / R - fee_R, idx, reason, pnl / R


def simulate(bars):
    o = [b[1] for b in bars]
    h = [b[2] for b in bars]
    l = [b[3] for b in bars]
    c = [b[4] for b in bars]
    n = len(bars)
    ema = ema_series(c)
    trades = []
    signals = 0
    busy_until = -1
    for t in range(max(EMA_P, 3), n - 1):
        if t <= busy_until:
            continue
        for s in (1, -1):
            if s == 1:
                col = c[t - 2] > o[t - 2] and c[t - 1] > o[t - 1] and c[t] > o[t]
                body_ok = (c[t - 1] - o[t - 1]) > SPIKE_MULT * (c[t] - o[t]) and (c[t - 1] - o[t - 1]) > SPIKE_MULT * (c[t - 2] - o[t - 2])
                struct = c[t] > c[t - 1] and o[t] > o[t - 1] and c[t - 1] > c[t - 2] and o[t - 1] > o[t - 2]
                low_struct = l[t - 1] > l[t - 2] and l[t] > l[t - 1]
                gap = l[t] > h[t - 2] * (1 + P_GAP)
                limit = l[t]
                ema_ok = limit > ema[t]
                SL = l[t - 2]
                R = limit - SL
            else:
                col = c[t - 2] < o[t - 2] and c[t - 1] < o[t - 1] and c[t] < o[t]
                body_ok = (o[t - 1] - c[t - 1]) > SPIKE_MULT * (o[t] - c[t]) and (o[t - 1] - c[t - 1]) > SPIKE_MULT * (o[t - 2] - c[t - 2])
                struct = c[t] < c[t - 1] and o[t] < o[t - 1] and c[t - 1] < c[t - 2] and o[t - 1] < o[t - 2]
                low_struct = h[t - 1] < h[t - 2] and h[t] < h[t - 1]
                gap = h[t] < l[t - 2] * (1 - P_GAP)
                limit = h[t]
                ema_ok = limit < ema[t]
                SL = h[t - 2]
                R = SL - limit
            if not (col and body_ok and struct and low_struct and gap):
                continue
            if not ema_ok:
                continue
            if R <= 0 or R > MAX_SL * limit:
                continue
            signals += 1
            e = t + 1
            filled = (s == 1 and l[e] <= limit) or (s == -1 and h[e] >= limit)
            if not filled:
                continue
            net, exit_idx, reason, gross = run_trade(o, h, l, c, e, s, limit, SL, R)
            trades.append({"t_utc": bars[e][0], "side": "LONG" if s == 1 else "SHORT",
                           "entry": limit, "sl": SL, "R_pct": R / limit * 100,
                           "gross": gross, "net": net, "reason": reason})
            busy_until = exit_idx
            break
    return trades, signals


def summ(rows):
    if not rows:
        return "بدون معامله"
    rows = sorted(rows, key=lambda r: r["t_utc"])
    n = len(rows)
    nets = [r["net"] for r in rows]
    h = n // 2
    f = lambda v: f"{v:+.3f}R"
    reasons = {k: sum(1 for r in rows if r["reason"] == k) for k in ("TP", "SL", "TIME", "END")}
    return (f"n={n:<5} خالص={f(st.mean(nets))} نیمه‌ی اول={f(st.mean(nets[:h])) if h else '-'} "
            f"نیمه‌ی دوم={f(st.mean(nets[h:])) if n - h else '-'} "
            f"TP={reasons['TP']} SL={reasons['SL']} زمان={reasons['TIME']} برد={sum(1 for x in nets if x > 0) / n * 100:.0f}%")


def main():
    import ccxt
    ex = ccxt.toobit({"enableRateLimit": True})
    all_trades, signals_total, skipped = [], 0, []
    per_sym = {}
    for sym in SYMBOLS:
        try:
            bars = fetch_1m(ex, sym)
        except Exception as e:
            skipped.append(f"{sym}: {str(e)[:60]}")
            continue
        if len(bars) < 200:
            skipped.append(f"{sym}: داده کم ({len(bars)})")
            continue
        trades, sig = simulate(bars)
        signals_total += sig
        for tr in trades:
            tr["sym"] = sym
        all_trades += trades
        per_sym[sym] = trades
    fill = len(all_trades) / signals_total * 100 if signals_total else 0.0
    L = ["SP2L_CRYPTO بک‌تست توصیفی (قبل از ثبت؛ پذیرش ندارد) — ۸۸ ارز، توبیت، ۱ دقیقه‌ای، ~۱۰ روز",
         f"ارزهای بدون داده: {len(skipped)}" + (" | " + " ; ".join(skipped[:8]) if skipped else ""),
         f"سیگنال‌های الگو (بعد از فیلترها): {signals_total} | پرشدن لیمیت: {len(all_trades)} ({fill:.1f}%)",
         "",
         "--- کل ---", summ(all_trades),
         "--- خرید ---", summ([x for x in all_trades if x["side"] == "LONG"]),
         "--- فروش ---", summ([x for x in all_trades if x["side"] == "SHORT"]),
         "", "--- به تفکیک ارز (حداقل ۵ معامله) ---"]
    for sym, tr in sorted(per_sym.items(), key=lambda x: -len(x[1])):
        if len(tr) >= MIN_SYM:
            L.append(f"{sym:18} {summ(tr)}")
    text = "\n".join(L)
    print(text)
    with open(os.path.join(BASE_DIR, "sp2l_crypto_summary.txt"), "w", encoding="utf-8") as fh:
        fh.write(text + "\n")
    with open(os.path.join(BASE_DIR, "sp2l_crypto_trades.csv"), "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["sym", "t_utc", "side", "entry", "sl", "R_pct", "gross", "net", "reason"])
        w.writeheader()
        for r in all_trades:
            w.writerow(r)


if __name__ == "__main__":
    main()
