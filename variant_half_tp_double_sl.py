"""
مقایسه‌ی سطوح فعلی ربات با TP نصف و SL دو برابر (نسبت به ورود) روی همان سیگنال‌ها.
قوانین در PREREG_HALF_TP_DOUBLE_SL.txt.
"""
import os
import statistics as st
import time

from path60 import load_trades, find_file, fetch_window, VERSIONS, BASE_DIR, MIN_MS
from life import path_of, resolve, HORIZON_MIN, FEE_PCT


def main():
    import ccxt
    ex = ccxt.toobit({"enableRateLimit": True})
    now_ms = int(time.time() * 1000)
    trades = []
    for name, pat in VERSIONS:
        trades += load_trades(find_file(pat), name)
    trades = [t for t in trades if t["t"] + HORIZON_MIN * MIN_MS < now_ms - 2 * MIN_MS]
    uniq = {}
    for t in trades:
        uniq.setdefault((t["sym"], t["t"], t["dir"]), t)
    items = list(uniq.values())
    state, cache, rows = {"mode": None}, {}, []
    dropped = 0
    for tr in items:
        E = tr["e"]
        tp_cur = abs(tr["tp"] - E) / E * 100
        sl_cur = abs(tr["sl"] - E) / E * 100
        if max(tp_cur, sl_cur) > 20:
            dropped += 1
            continue
        key = (tr["sym"], tr["t"])
        if key not in cache:
            cache[key] = fetch_window(ex, tr["sym"], tr["t"], tr["t"] + HORIZON_MIN * MIN_MS, state)
        bars = cache[key][0]
        P = path_of(tr, bars) if bars else None
        if P is None:
            continue
        o_cur, p_cur, _, _ = resolve(P, tp_cur, sl_cur)
        tp_new, sl_new = tp_cur * 0.5, sl_cur * 2
        o_new, p_new, _, _ = resolve(P, tp_new, sl_new)
        rows.append({"version": tr["version"], "t": tr["t"], "cur": o_cur, "p_cur": p_cur - FEE_PCT,
                     "new": o_new, "p_new": p_new - FEE_PCT, "tp_cur": tp_cur, "sl_cur": sl_cur})
    n = len(rows)
    L = [f"مقایسه: TP نصف و SL دو برابر | روش داده: {state['mode']} | سیگنال یکتای کامل: {n} | حذف (فاصله‌ی غیرعادی): {dropped}"]
    if n:
        def block(label, key_o, key_p):
            pv = [r[key_p] for r in rows]
            mid = n // 2
            tp = sum(1 for r in rows if r[key_o] == "TP") / n * 100
            sl = sum(1 for r in rows if r[key_o] == "SL") / n * 100
            none = sum(1 for r in rows if r[key_o] == "NONE") / n * 100
            L.append(f"{label}: TP={tp:.1f}% | SL={sl:.1f}% | بدون برخورد={none:.1f}% | "
                     f"انتظار خالص={st.mean(pv):+.3f}% | نیمه‌ی اول={st.mean(pv[:mid]):+.3f}% | نیمه‌ی دوم={st.mean(pv[mid:]):+.3f}%")
        block("سطوح فعلی ربات", "cur", "p_cur")
        block("TP نصف، SL دو برابر", "new", "p_new")
        L.append("")
        L.append("به تفکیک نسخه (انتظار خالص: فعلی → جدید):")
        for name, _ in VERSIONS:
            rs = [r for r in rows if r["version"] == name]
            if rs:
                L.append(f"  {name:6} n={len(rs):<4} {st.mean(r['p_cur'] for r in rs):+.3f}% → {st.mean(r['p_new'] for r in rs):+.3f}%")
    text = "\n".join(L)
    print(text)
    with open(os.path.join(BASE_DIR, "variant_half_tp_double_sl_summary.txt"), "w", encoding="utf-8") as fh:
        fh.write(text + "\n")


if __name__ == "__main__":
    main()
