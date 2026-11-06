"""
مسیر کامل هر معامله (تا ۳ روز یا تعیین تکلیف) روی کندل ۵ دقیقه‌ای توبیت.
همه‌ی اندازه‌ها بر حسب درصد از نقطه‌ی ورود.
سه پرسش:
 ۱) قبل از نتیجه‌ی نهایی، معامله حداکثر چند درصد به سمت TP رفته؟ (برای همه‌ی ارزها)
 ۲) معامله‌های SL‌شده: بعد از SL، ادامه‌ی روند بوده یا برگشته و آیا به TP رسیده؟
 ۳) شبکه‌ی فاصله‌ی TP و SL بر حسب درصد: احتمال خوردن SL قبل از TP و انتظار سود خالص (با کارمزد).
قواعد: ورود = قیمت سیگنال؛ کندل‌های کامل بعد از سیگنال؛ اگر TP و SL در یک کندل باشند، SL اول.
"""
import csv
import os
import time
import statistics as st
import numpy as np

from path60 import load_trades, find_file, fetch_window, VERSIONS, BAR_MS, MIN_MS, BASE_DIR

HORIZON_MIN = 3 * 24 * 60
FEE_PCT = 0.12  # رفت و برگشت، درصد از ورود
MAX_DIST_PCT = 20.0
TP_GRID = [0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 4.0]
SL_GRID = [0.25, 0.5, 0.75, 1.0, 1.5, 2.0, 2.5, 3.0, 4.0]
FINE_TP = sorted(set([round(x, 2) for x in np.arange(0.2, 6.01, 0.2)] + TP_GRID))
FINE_SL = sorted(set([round(x, 2) for x in np.arange(0.1, 6.01, 0.1)] + SL_GRID))
MIN_SYM_N = 5


def ceil_bar(t):
    return ((t + BAR_MS - 1) // BAR_MS) * BAR_MS


def path_of(tr, bars):
    t0, E, d = tr["t"], tr["e"], tr["dir"]
    t_start, t_end = ceil_bar(t0), t0 + HORIZON_MIN * MIN_MS
    win = [b for b in bars if t_start <= b[0] < t_end]
    if not win:
        return None
    h = np.array([b[2] for b in win], dtype=float)
    l = np.array([b[3] for b in win], dtype=float)
    c = np.array([b[4] for b in win], dtype=float)
    mins = np.array([(b[0] - t0) / MIN_MS for b in win], dtype=float)
    if d == "LONG":
        fav = (h - E) / E * 100
        adv = (E - l) / E * 100
        close = (c - E) / E * 100
    else:
        fav = (E - l) / E * 100
        adv = (h - E) / E * 100
        close = (E - c) / E * 100
    return {"fav": fav, "adv": adv, "fav_cum": np.maximum.accumulate(fav),
            "adv_cum": np.maximum.accumulate(adv), "close": close, "mins": mins}


def first_idx(cum, level):
    if level is None or len(cum) == 0:
        return None
    hit = cum >= level
    if not hit.any():
        return None
    return int(np.argmax(hit))


def resolve(P, tp_pct, sl_pct):
    """خروجی با TP و SL داده‌شده (درصد از ورود). SL اولویت دارد در کندل مشترک."""
    it = first_idx(P["fav_cum"], tp_pct)
    isl = first_idx(P["adv_cum"], sl_pct)
    if it is None and isl is None:
        return "NONE", float(P["close"][-1]), None, None
    if isl is not None and (it is None or isl <= it):
        return "SL", -sl_pct, it, isl
    return "TP", tp_pct, it, isl


def main():
    import ccxt
    ex = ccxt.toobit({"enableRateLimit": True})
    trades, dropped, incomplete = [], [], 0
    now_ms = int(time.time() * 1000)
    for name, pat in VERSIONS:
        for tr in load_trades(find_file(pat), name):
            if tr["t"] + HORIZON_MIN * MIN_MS > now_ms - 2 * MIN_MS:
                incomplete += 1
                continue
            dist_sl = abs(tr["sl"] - tr["e"]) / tr["e"] * 100
            dist_tp = abs(tr["tp"] - tr["e"]) / tr["e"] * 100
            if dist_sl > MAX_DIST_PCT or dist_tp > MAX_DIST_PCT:
                dropped.append(f"{tr['version']} {tr['sym']} ورود={tr['e']} SL={tr['sl']} TP={tr['tp']}")
                continue
            tr["sl_pct"], tr["tp_pct"] = dist_sl, dist_tp
            trades.append(tr)
    state = {"mode": None}
    cache, paths, nodata = {}, [], {}
    for tr in trades:
        key = (tr["sym"], tr["t"])
        if key not in cache:
            cache[key] = fetch_window(ex, tr["sym"], tr["t"], tr["t"] + HORIZON_MIN * MIN_MS, state)
            if cache[key][0] is None:
                nodata[tr["sym"]] = cache[key][1]
        bars = cache[key][0]
        P = path_of(tr, bars) if bars else None
        if P is None:
            continue
        paths.append((tr, P))
    print(f"mode={state['mode']} trades={len(trades)} with_path={len(paths)} dropped={len(dropped)} incomplete={incomplete}", flush=True)

    # ----- معیارهای هر معامله با سطوح خود ربات -----
    rows = []
    for tr, P in paths:
        out, pnl, it, isl = resolve(P, tr["tp_pct"], tr["sl_pct"])
        n = len(P["fav"])
        exit_idx = min([x for x in (it, isl) if x is not None], default=n - 1)
        max_fav_before = float(P["fav_cum"][exit_idx])
        row = {"version": tr["version"], "sym": tr["sym"], "base": tr["base"], "t_utc": tr["t"],
               "dir": tr["dir"], "entry": tr["e"], "sl_pct": tr["sl_pct"], "tp_pct": tr["tp_pct"],
               "excel": tr["excel"], "bot_outcome": out,
               "tp_touched": it is not None, "tp_min": (P["mins"][it] if it is not None else ""),
               "sl_min": (P["mins"][isl] if isl is not None else ""),
               "max_fav_before_exit_pct": max_fav_before,
               "max_fav_before_exit_frac_tp": max_fav_before / tr["tp_pct"],
               "max_fav_full_pct": float(P["fav_cum"][-1]),
               "max_adv_before_tp_pct": float(P["adv_cum"][it if it is not None else n - 1])}
        if out == "SL":
            post = P["fav"][isl + 1:]
            post_adv = P["adv"][isl + 1:]
            pf = float(post.max()) if len(post) else 0.0
            pa = float(post_adv.max()) if len(post_adv) else 0.0
            row.update({"post_fav_pct": pf, "post_adv_pct": pa,
                        "post_tp_reached": pf >= tr["tp_pct"],
                        "post_returned_entry": pf >= 0,
                        "post_continued": pa >= 0.5 * tr["sl_pct"]})
        rows.append(row)

    # ----- شبکه‌ی TP/SL ثابت (درصد)، روی همه‌ی معاملات -----
    def expectancy(x, d):
        cnt = {"TP": 0, "SL": 0, "NONE": 0}
        pnl = []
        for tr, P in paths:
            o, p, _, _ = resolve(P, x, d)
            cnt[o] += 1
            pnl.append(p - FEE_PCT)
        n = len(paths)
        return cnt["TP"] / n * 100, cnt["SL"] / n * 100, cnt["NONE"] / n * 100, st.mean(pnl)

    grid_rows = []
    for x in FINE_TP:
        for d in FINE_SL:
            ptp, psl, pno, ex_ = expectancy(x, d)
            grid_rows.append({"tp_pct": x, "sl_pct": d, "p_tp_first": ptp, "p_sl_first": psl,
                              "p_none": pno, "expect_net_pct": ex_})

    L = []
    L.append("مسیر کامل معاملات (تا ۳ روز یا تعیین تکلیف) — همه‌ی اعداد بر حسب درصد از ورود")
    L.append(f"روش داده: {state['mode']} | معاملات: {len(trades)} | با مسیر کامل: {len(paths)} | حذف‌شده (فاصله‌ی غیرعادی): {len(dropped)} | افق ۳ روزه هنوز کامل نشده (کنار گذاشته شد): {incomplete}")
    if dropped:
        L.append("ردیف‌های حذف‌شده: " + " ; ".join(dropped[:10]))
    if nodata:
        L.append("بدون داده: " + " ; ".join(f"{k}: {v[:80]}" for k, v in list(nodata.items())[:5]))
    L.append("")

    # پرسش ۱
    L.append("=== ۱) قبل از نتیجه‌ی نهایی، معامله حداکثر چند درصد به سمت TP رفته ===")
    fr = [r["max_fav_before_exit_frac_tp"] for r in rows]
    pc = [r["max_fav_before_exit_pct"] for r in rows]
    def q(v, p):
        return float(np.percentile(v, p))
    L.append(f"همه (n={len(rows)}): درصد حرکت به سمت TP قبل از خروج — میانه={st.median(fr)*100:.0f}% | p25={q(fr,25)*100:.0f}% | p75={q(fr,75)*100:.0f}% | "
             f"حرکت درصدی میانه={st.median(pc):.2f}%")
    for label in ["TP", "SL"]:
        sub = [r for r in rows if r["bot_outcome"] == label]
        if sub:
            f = [r["max_fav_before_exit_frac_tp"] for r in sub]
            L.append(f"  نتیجه‌ی ربات {label} (n={len(sub)}): میانه={st.median(f)*100:.0f}% از فاصله‌ی TP | p75={q(f,75)*100:.0f}%")
    L.append(f"  سهم معاملات که قبل از خروج حداقل ۵۰٪ فاصله‌ی TP را رفته‌اند: {sum(1 for x in fr if x>=0.5)/len(fr)*100:.1f}%")
    L.append(f"  سهم معاملات که حداقل ۱۰۰٪ (یعنی TP) را رفته‌اند: {sum(1 for x in fr if x>=1)/len(fr)*100:.1f}%")
    L.append("به تفکیک ارز (حداقل ۵ معامله): میانه‌ی درصد پیشروی به سمت TP قبل از خروج")
    bases = {}
    for r in rows:
        bases.setdefault(r["base"], []).append(r)
    med_by = []
    for b, rs in sorted(bases.items(), key=lambda x: -len(x[1])):
        if len(rs) >= MIN_SYM_N:
            m = st.median(r["max_fav_before_exit_frac_tp"] for r in rs) * 100
            med_by.append(m)
            L.append(f"  {b:10} n={len(rs):<4} میانه={m:5.0f}%  TP-خورده={sum(1 for r in rs if r['bot_outcome']=='TP')/len(rs)*100:4.0f}%")
    if med_by:
        L.append(f"  پراکندگی بین ارزها: کمترین={min(med_by):.0f}% بیشترین={max(med_by):.0f}%")
    L.append("")

    # پرسش ۲
    L.append("=== ۲) معاملات SL‌شده: بعد از SL چه شد؟ ===")
    sl_rows = [r for r in rows if r["bot_outcome"] == "SL"]
    if sl_rows:
        n = len(sl_rows)
        L.append(f"تعداد SL در مسیر (n={n}) | بعد از SL، حداقل نیم فاصله‌ی SL به نفع معامله برگشته (از ورود گذشته): "
                 f"{sum(1 for r in sl_rows if r['post_returned_entry'])/n*100:.1f}%")
        L.append(f"  بعد از SL، حداقل ۵۰٪ فاصله‌ی SL در جهت ضد معامله ادامه داده (ادامه‌ی روند): {sum(1 for r in sl_rows if r['post_continued'])/n*100:.1f}%")
        L.append(f"  بعد از SL، TP (فرضی) هم لمس شده: {sum(1 for r in sl_rows if r['post_tp_reached'])/n*100:.1f}%")
        L.append(f"  میانه‌ی بیشترین حرکت مطلوب بعد از SL = {st.median(r['post_fav_pct'] for r in sl_rows):.2f}% | "
                 f"میانه‌ی بیشترین حرکت نامطلوب بعد از SL = {st.median(r['post_adv_pct'] for r in sl_rows):.2f}%")
        L.append(f"  میانه‌ی فاصله‌ی SL = {st.median(r['sl_pct'] for r in sl_rows):.2f}% | میانه‌ی فاصله‌ی TP = {st.median(r['tp_pct'] for r in sl_rows):.2f}%")
    L.append("")

    # پرسش ۳
    L.append("=== ۳) شبکه‌ی TP و SL ثابت (درصد از ورود) — همه‌ی معاملات ===")
    L.append("برای هر TP: بهترین SL از نظر انتظار سود خالص (با کارمزد ۰.۱۲٪) و احتمال‌ها")
    for x in TP_GRID:
        cand = [g for g in grid_rows if g["tp_pct"] == x]
        best = max(cand, key=lambda g: g["expect_net_pct"])
        L.append(f"TP={x:.1f}%: بهترین SL={best['sl_pct']:.2f}% | P(TP اول)={best['p_tp_first']:.1f}% | "
                 f"P(SL اول)={best['p_sl_first']:.1f}% | بدون برخورد={best['p_none']:.1f}% | انتظار خالص={best['expect_net_pct']:+.3f}%")
    L.append("")
    L.append("جدول P(SL اول) برای TP و SL انتخابی (SL بزرگ‌تر = احتمال خوردن SL کمتر):")
    L.append("TP\\SL " + " ".join(f"{s:>6}" for s in SL_GRID))
    for x in TP_GRID:
        vals = []
        for s in SL_GRID:
            g = next(g for g in grid_rows if g["tp_pct"] == x and g["sl_pct"] == s)
            vals.append(f"{g['p_sl_first']:6.1f}")
        L.append(f"{x:5.1f} " + " ".join(vals))
    L.append("")
    L.append("جدول P(TP اول) برای همان ترکیب‌ها:")
    for x in TP_GRID:
        vals = []
        for s in SL_GRID:
            g = next(g for g in grid_rows if g["tp_pct"] == x and g["sl_pct"] == s)
            vals.append(f"{g['p_tp_first']:6.1f}")
        L.append(f"{x:5.1f} " + " ".join(vals))
    text = "\n".join(L)
    print(text)
    with open(os.path.join(BASE_DIR, "life_summary.txt"), "w", encoding="utf-8") as fh:
        fh.write(text + "\n")
    cols = ["version", "sym", "t_utc", "dir", "entry", "sl_pct", "tp_pct", "excel", "bot_outcome", "tp_touched",
            "tp_min", "sl_min", "max_fav_before_exit_pct", "max_fav_before_exit_frac_tp", "max_fav_full_pct",
            "max_adv_before_tp_pct", "post_fav_pct", "post_adv_pct", "post_tp_reached",
            "post_returned_entry", "post_continued"]
    with open(os.path.join(BASE_DIR, "life_signals.csv"), "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(r)
    with open(os.path.join(BASE_DIR, "life_grid.csv"), "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(grid_rows[0].keys()))
        w.writeheader()
        w.writerows(grid_rows)


if __name__ == "__main__":
    main()
