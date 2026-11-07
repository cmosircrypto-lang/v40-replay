"""
بک‌تست SP2L طبق PREREG_SP2L.txt، ۸۸ ارز، توبیت ۱۵ دقیقه‌ای. توصیفی (قبل از ثبت).
"""
import os
import statistics as st

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FEE_PCT = 0.12
HORIZON = 24
BODY_N = 10
BODY_MULT = 2.0
PULL_WIN = 5
TP_R = 1.0
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


def body(b):
    return abs(b[4] - b[1])


def find_signals(bars, side, gap_required):
    """برمی‌گرداند لیست (idx_entry, E, SL, R)"""
    out = []
    n = len(bars)
    for i in range(BODY_N + 1, n - PULL_WIN - 2):
        c1, c2, c3 = bars[i], bars[i + 1], bars[i + 2]
        if side == "LONG":
            if not (c1[4] > c1[1] and c2[4] > c2[1]):
                continue
        else:
            if not (c1[4] < c1[1] and c2[4] < c2[1]):
                continue
        avg = sum(body(bars[k]) for k in range(i - BODY_N, i)) / BODY_N
        if avg <= 0 or body(c2) < BODY_MULT * avg:
            continue
        if gap_required:
            if side == "LONG" and not (c3[3] > c1[2]):
                continue
            if side == "SHORT" and not (c3[2] < c1[3]):
                continue
        SL = c1[3] if side == "LONG" else c1[2]
        j_found = None
        for j in range(i + 2, i + 2 + PULL_WIN):
            b = bars[j]
            if side == "LONG":
                if b[3] <= SL:
                    break
                if b[4] < b[1]:
                    j_found = j
                    break
            else:
                if b[2] >= SL:
                    break
                if b[4] > b[1]:
                    j_found = j
                    break
        if j_found is None:
            continue
        E = bars[j_found][4]
        R = (E - SL) if side == "LONG" else (SL - E)
        if R <= 0:
            continue
        out.append((j_found, E, SL, R, side))
    return out


def simulate(bars, sig):
    j, E, SL, R, side = sig
    TP = E + TP_R * R if side == "LONG" else E - TP_R * R
    pnl = None
    k = j
    for k in range(j + 1, min(j + 1 + HORIZON, len(bars))):
        _, _o, h, l, _c = bars[k][:5]
        if side == "LONG":
            if l <= SL:
                pnl = -R
                break
            if h >= TP:
                pnl = TP_R * R
                break
        else:
            if h >= SL:
                pnl = -R
                break
            if l <= TP:
                pnl = TP_R * R
                break
    if pnl is None:
        last = bars[min(j + HORIZON, len(bars) - 1)][4]
        pnl = (last - E) if side == "LONG" else (E - last)
    exit_k = k
    fee_R = (FEE_PCT / 100) * E / R
    return pnl / R - fee_R, exit_k


def run_all(bars_by_sym, gap_required):
    res = []
    for sym, bars in bars_by_sym.items():
        busy_until = -1
        for side in ("LONG", "SHORT"):
            for sig in find_signals(bars, side, gap_required):
                if sig[0] <= busy_until:
                    continue
                net, exit_k = simulate(bars, sig)
                busy_until = exit_k
                res.append((sym, bars[sig[0]][0], side, net, sig[0] < 0))
    res.sort(key=lambda x: x[1])
    return res


def summ(rows):
    if not rows:
        return "بدون معامله"
    n = len(rows)
    nets = [r[3] for r in rows]
    h = n // 2
    f = lambda v: f"{v:+.3f}R"
    return (f"n={n:<4} خالص={f(st.mean(nets))} نیمه‌ی اول={f(st.mean(nets[:h])) if h else '-'} "
            f"نیمه‌ی دوم={f(st.mean(nets[h:])) if n-h else '-'} برد(TP)={sum(1 for x in nets if x>0)/n*100:.0f}%")


def main():
    import ccxt
    ex = ccxt.toobit({"enableRateLimit": True})
    bars_by_sym, skipped = {}, []
    for sym in SYMBOLS:
        try:
            b = ex.fetch_ohlcv(sym, timeframe="15m", limit=1000)
            if b and len(b) > 100:
                bars_by_sym[sym] = b
            else:
                skipped.append(sym)
        except Exception as e:
            skipped.append(f"{sym}")
    main_rows = run_all(bars_by_sym, gap_required=True)
    ctrl_rows = run_all(bars_by_sym, gap_required=False)
    L = ["SP2L بک‌تست توصیفی (قبل از ثبت؛ پذیرش ندارد) — ۸۸ ارز، توبیت ۱۵ دقیقه‌ای",
         f"ارزهای بدون داده: {len(skipped)}", "",
         "--- فرضیه (با P-Gap) ---", summ(main_rows),
         "--- کنترل (بدون P-Gap) ---", summ(ctrl_rows), "",
         "--- به تفکیک جهت ---"]
    for side in ("LONG", "SHORT"):
        L.append(f"{side:6} فرضیه: {summ([r for r in main_rows if r[2]==side])}")
        L.append(f"{side:6} کنترل: {summ([r for r in ctrl_rows if r[2]==side])}")
    L.append("")
    L.append("--- به تفکیک ارز (فقط با معامله) ---")
    by = {}
    for r in main_rows:
        by.setdefault(r[0], []).append(r)
    for sym, rs in sorted(by.items(), key=lambda x: -len(x[1])):
        L.append(f"{sym:18} {summ(rs)}")
    text = "\n".join(L)
    print(text)
    with open(os.path.join(BASE_DIR, "sp2l_backtest_summary.txt"), "w", encoding="utf-8") as fh:
        fh.write(text + "\n")


if __name__ == "__main__":
    main()
