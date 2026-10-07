"""
Stage 3 (v3): three scans on the adjusted prices from build_prices.py.

  1. Breakout         : stock closing near / above its recent flag high (Setup / Triggered)
  2. Pullback         : close within +/-2% of EMA11 / EMA21 / SMA50
  3. High tight flag  : big flagpole, flag, and price sitting within +/-2% of EMA11 / EMA21 / SMA50

Every scan only looks at STAGE 2 stocks (SMA150/200 template, 30% above the 52-week low, within 25% of
the 52-week high, relative strength rank 70+) that also show a real PRIOR MOVE (rally) in the last 6 months.
On top of that: ADR above 3%, enough liquidity, and the trend stack EMA11 > EMA21 > SMA50.
The scans only pick the stocks. The chart pattern itself is for you to judge.

Run:  python run_scans.py
Out:  data/results.json   (the dashboard reads this)
All settings are in CFG below.
"""
import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

DATA = Path("data")

# ------------------------- settings -------------------------
CFG = {
    "min_bars": 80,                 # minimum history for any scan
    "min_adr_pct": 3.0,             # 20-day average daily range %, applies to ALL scans
    "min_avg_value_cr": 1.0,        # 20-day avg traded value in rupees crore, applies to ALL scans
    "max_risk_pct": None,           # e.g. 10 drops setups with stop wider than 10%
    "min_traded_ratio": 0.6,        # abort (keep old results.json) if fewer stocks than this traded on the latest day
    "prior_move": {                 # applies to ALL scans: a real rally must have happened before
        "enabled": True,
        "days": 126,                # look back this many trading days (about 6 months)
        "min_pct": 50,              # best low-to-high closing rally inside that window, in %
    },
    "stage2": {                     # Stage 2 is a REQUIREMENT for every scan (no separate Stage 2 tab)
        "required": True,           # needs 253+ bars (SMA200 + 52-week range + 12-month RS)
        "slope_days": 22,           # 200-day average must be higher than this many days ago
        "min_above_low_pct": 30,    # close at least 30% above the 52-week low
        "max_below_high_pct": 25,   # close within 25% of the 52-week high
        "min_rs": 70,               # relative strength rank 1-99 among liquid stocks
    },
    "breakout": {
        "enabled": True,
        "lookback_days": 30,        # flag high must be within this many days
        "flag_min_days": 5,         # flag at least a week old
        "max_depth_pct": 25,        # flag may not dip more than this from its high
        "max_below_pct": 7,         # Setup: close within this % under the flag high
        "break_vol_ratio": 1.5,     # Triggered: today's volume >= 1.5 x its 20-day average
        "max_extended_pct": 8,      # Triggered: skip if the close is already >8% over the flag high
        "max_risk_adr": 2.0,        # skip if the stop is wider than 2 x ADR
        "min_rank": 0,              # 0 = off. Momentum rank 1-99 (best of 1M/3M/6M); e.g. 80 = top performers only
    },
    "pullback": {"tight_pct": 2.0, "levels": ["EMA11", "EMA21", "SMA50"]},
    "momentum": {                   # optional extra filter on returns (off). close now vs close N days ago
        "enabled": False,
        "match": "any",
        "apply_to": ["pullback"],
        "days": {"1m": 21, "3m": 63, "6m": 126},
        "min_pct": {"1m": 30, "3m": 50, "6m": 100},
    },
    "ema_then": {                   # pullback only: stock must also have closed above its EMA 21 back then
        "enabled": True,
        "days_ago": 21,             # 21 trading days is about 30 calendar days
        "apply_to": ["pullback"],
    },
    "htf": {"flagpole_days": 40, "min_gain_pct": 70, "flag_min_days": 15,
            "flag_max_days": 25, "max_pullback_pct": 25,
            "tight_pct": 2.0},      # close must be within +/-2% of EMA11, EMA21 or SMA50
}
# ------------------------------------------------------------


def num(x, d=2):
    return round(float(x), d) if np.isfinite(x) else None


def analyse(key, g, review_keys, recent_keys):
    """Returns (info, hits). info feeds the RS ranking, hits are scan results."""
    n = len(g)
    info = {"key": key, "rs_raw": None, "perf": None}
    if n < CFG["min_bars"]:
        return info, {}
    c, h, v = (g[k].to_numpy(float) for k in ("close", "high", "volume"))
    o = g["open"].to_numpy(float)
    l = g["low"].to_numpy(float)
    l = np.where(l > 0, l, c)
    val = g["value"].to_numpy(float)
    i = n - 1

    M = CFG["momentum"]
    mom = None
    if n > max(M["days"].values()):
        mom = {k: (c[i] / c[i - d] - 1) * 100 for k, d in M["days"].items()}
    pick = any if M["match"] == "any" else all
    mom_ok = mom is not None and pick(mom[k] >= M["min_pct"][k] for k in M["min_pct"])
    gate = {nm: (mom_ok if (M["enabled"] and nm in M["apply_to"]) else True)
            for nm in ("stage2", "pullback", "htf")}

    adr = (((h[-20:] - l[-20:]) / c[-20:]) * 100).mean()
    avg_val_cr = val[-20:].mean() / 1e7
    liquid = avg_val_cr >= CFG["min_avg_value_cr"]
    if liquid and n >= 253:             # IBD-style weighted 3/6/9/12 month return
        r = lambda d: c[i] / c[i - d] - 1
        info["rs_raw"] = 0.4 * r(63) + 0.2 * r(126) + 0.2 * r(189) + 0.2 * r(252)
    if liquid and n > max(M["days"].values()):    # 1M / 3M / 6M returns, ranked later in main()
        info["perf"] = {k: c[i] / c[i - d] - 1 for k, d in M["days"].items()}
    if not liquid or adr < CFG["min_adr_pct"]:
        return info, {}

    s = pd.Series(c)
    ema11 = s.ewm(span=11, adjust=False).mean().to_numpy()
    ema21 = s.ewm(span=21, adjust=False).mean().to_numpy()
    sma50 = s.rolling(50).mean().to_numpy()

    # ---- prior move: the best low-to-high closing rally in the window (applies to ALL scans) ----
    PM = CFG["prior_move"]
    w0 = max(0, i - PM["days"])
    rally = ((c[w0:i + 1] / np.minimum.accumulate(c[w0:i + 1])).max() - 1) * 100
    if PM["enabled"] and rally < PM["min_pct"]:
        return info, {}

    # ---- Stage 2 template (required for every scan; the RS rank part is applied later in main) ----
    S2 = CFG["stage2"]
    stage2_ok, off_high, above_low = False, None, None
    if n >= 253:
        sma150 = s.rolling(150).mean().to_numpy()
        sma200 = s.rolling(200).mean().to_numpy()
        hi52, lo52 = h[-252:].max(), l[-252:].min()
        off_high, above_low = num((1 - c[i] / hi52) * 100, 1), num((c[i] / lo52 - 1) * 100, 0)
        stage2_ok = bool(c[i] > sma150[i] and c[i] > sma200[i] and sma150[i] > sma200[i]
                         and sma50[i] > sma150[i] and sma50[i] > sma200[i] and c[i] > sma50[i]
                         and sma200[i] > sma200[i - S2["slope_days"]]
                         and c[i] >= lo52 * (1 + S2["min_above_low_pct"] / 100)
                         and c[i] >= hi52 * (1 - S2["max_below_high_pct"] / 100))
    if S2["required"] and not stage2_ok:
        return info, {}

    T = CFG["ema_then"]
    j = i - T["days_ago"]
    then_ok = bool(c[j] > ema21[j])

    def passes(name):               # momentum gate AND the EMA 21 'then' check, where they apply
        return gate[name] and (then_ok or not (T["enabled"] and name in T["apply_to"]))

    row0 = g.iloc[-1]
    note = []
    if key in review_keys:
        note.append("unadjusted corporate action in history, check chart")
    if key in recent_keys:
        note.append("split/bonus adjusted in last 60 days")
    base = dict(
        key=key, symbol=row0["symbol"], exch=row0["exch"], name=str(row0["name"]) if pd.notna(row0["name"]) else "",
        close=num(c[i]), chg=num((c[i] / c[i - 1] - 1) * 100), adr=num(adr, 1),
        value_cr=num(avg_val_cr, 1), ema11=num(ema11[i]), ema21=num(ema21[i]),
        sma50=num(sma50[i]), prior_move=num(rally, 0), off_high=off_high, above_low=above_low, spark=[num(x) for x in c[-40:]], note="; ".join(note),
        **{f"ret{k}": (num(mom[k], 0) if mom else None) for k in ("1m", "3m", "6m")},
    )
    out = {}

    def finish(name, entry, stop, **extra):
        if entry <= stop:
            return
        risk = (entry - stop) / entry * 100
        if CFG["max_risk_pct"] and risk > CFG["max_risk_pct"]:
            return
        out[name] = {**base, "entry": num(entry), "stop": num(stop), "risk": num(risk, 1), **extra}

    # every scan below needs the short-term trend stack
    if not (ema11[i] > ema21[i] > sma50[i] and c[i] > sma50[i]):
        return info, out

    # ---- 1. breakout: closing near the flag high (Setup) or above it on volume (Triggered) ----
    B = CFG["breakout"]
    if B["enabled"] and c[i] > ema21[i]:
        wb = B["lookback_days"]
        pk = i - wb + int(np.argmax(h[i - wb:i]))          # flag high, before today
        top, flag_len = h[pk], i - pk
        depth = (top - l[pk + 1:i + 1].min()) / top * 100

        def brk(state, stop, vr):
            risk = (top - stop) / top * 100
            if risk / adr > B["max_risk_adr"]:
                return
            finish("breakout", top, stop, state=state, flag_days=int(flag_len), depth=num(depth, 1),
                   vol_ratio=num(vr, 1), risk_adr=num(risk / adr, 2),
                   signal="Closed above flag high on volume" if state == "Triggered"
                   else "Near flag high, trigger above it")

        if flag_len >= B["flag_min_days"] and depth <= B["max_depth_pct"]:
            if c[i] <= top:                                    # still under the flag high
                if c[i] >= top * (1 - B["max_below_pct"] / 100):
                    base_v = v[-55:-5].mean()                  # info only: last 5 days vs the 50 before
                    brk("Setup", l[-3:].min(), v[-5:].mean() / base_v if base_v > 0 else 0)
            else:                                              # closed above the flag high today
                avg_v = v[i - 20:i].mean()
                vr = v[i] / avg_v if avg_v > 0 else 0
                pos = (c[i] - l[i]) / (h[i] - l[i]) if h[i] > l[i] else 1.0
                if (vr >= B["break_vol_ratio"] and pos >= 0.5
                        and c[i] <= top * (1 + B["max_extended_pct"] / 100)):
                    brk("Triggered", l[i], vr)

    # ---- 2. pullback: tightness only, close within +/-X% of a moving average ----
    p = CFG["pullback"]
    levels = {"EMA11": ema11[i], "EMA21": ema21[i], "SMA50": sma50[i]}
    best = min(((abs(c[i] / levels[k] - 1) * 100, k) for k in p["levels"]), key=lambda t: t[0])
    if best[0] <= p["tight_pct"] and passes("pullback"):
        k = best[1]
        finish("pullback", h[i], l[-5:].min(), level=k, dist=num((c[i] / levels[k] - 1) * 100, 2),
               signal=f"Within {p['tight_pct']:g}% of {k}")

    # ---- 3. high tight flag: flagpole + flag, price must sit within +/-2% of EMA11 / EMA21 / SMA50 ----
    f = CFG["htf"]
    fmax = f["flag_max_days"]
    pk = i - fmax + int(np.argmax(h[i - fmax:i]))      # flag peak, before today
    flag_len = i - pk
    near_d, near_k = min((abs(c[i] / lv - 1) * 100, k) for k, lv in levels.items())
    if f["flag_min_days"] <= flag_len <= fmax and passes("htf") and near_d <= f["tight_pct"]:
        top = h[pk]
        gain = (top / l[max(0, pk - f["flagpole_days"]):pk + 1].min() - 1) * 100
        flag_low = l[pk + 1:i + 1].min()
        pb = (top - flag_low) / top * 100
        extra = dict(level=near_k, dist=num((c[i] / levels[near_k] - 1) * 100, 2))
        if gain >= f["min_gain_pct"] and pb <= f["max_pullback_pct"]:
            if c[i] > top:
                finish("htf", h[i], flag_low, state="Triggered", gain=num(gain, 0),
                       flag_days=int(flag_len), pullback=num(pb, 1), signal="Broke flag high", **extra)
            elif c[i] >= top * (1 - f["max_pullback_pct"] / 100):
                finish("htf", top, flag_low, state="Forming", gain=num(gain, 0),
                       flag_days=int(flag_len), pullback=num(pb, 1), signal="In flag, trigger above high", **extra)
    return info, out

def main():
    df = pd.read_csv(DATA / "prices.csv.gz").sort_values(["key", "date"])
    ev = pd.read_csv(DATA / "events.csv")
    dates = sorted(df["date"].unique())
    last = dates[-1]
    review_keys = set(ev.loc[ev["method"] == "review", "key"])
    recent_keys = set(ev.loc[(ev["method"] != "review") & (ev["date"] >= dates[max(0, len(dates) - 60)]), "key"])

    # sanity checks: refuse to publish results built from a half-downloaded latest day
    exch_last = df.groupby("exch")["date"].max()
    if exch_last.nunique() > 1:
        raise SystemExit(f"ABORT: exchanges disagree on the latest date ({exch_last.to_dict()}). "
                         "One exchange's file for the latest day is missing; results would be partial.")
    latest = df.loc[df["date"] == last, "key"].nunique()
    known = df["key"].nunique()
    if latest / known < CFG["min_traded_ratio"]:
        raise SystemExit(f"ABORT: only {latest:,} of {known:,} stocks traded on {last}. "
                         "The latest day looks incomplete. results.json was NOT updated.")

    hits = {"breakout": [], "pullback": [], "htf": []}
    rs_raw, perf_raw = {}, {}
    total = traded = 0
    for key, g in df.groupby("key", sort=False):
        total += 1
        if g["date"].iloc[-1] != last:      # not traded on the latest day: stale or suspended
            continue
        traded += 1
        info, res = analyse(key, g, review_keys, recent_keys)
        if info["rs_raw"] is not None:
            rs_raw[key] = info["rs_raw"]
        if info["perf"] is not None:
            perf_raw[key] = info["perf"]
        for name, row in res.items():
            hits[name].append(row)

    # relative strength rank 1-99 among liquid stocks with a full year of history
    rank = (pd.Series(rs_raw).rank(pct=True) * 98 + 1).round().astype(int)
    for name in hits:                      # Stage 2 also needs a relative strength rank of min_rs or better
        keep = []
        for r in hits[name]:
            r["rs"] = int(rank.get(r["key"], 0))
            if not CFG["stage2"]["required"] or r["rs"] >= CFG["stage2"]["min_rs"]:
                keep.append(r)
        hits[name] = keep
    # momentum rank for the breakout scan: rank 1M, 3M and 6M returns separately among liquid
    # stocks, a stock's rank is its best of the three (it only has to be a top performer once)
    mrank = (pd.DataFrame(perf_raw).T.rank(pct=True) * 98 + 1).max(axis=1).round().astype(int) \
        if perf_raw else pd.Series(dtype=int)
    keep = []
    for r in hits["breakout"]:
        r["rank"] = int(mrank.get(r["key"], 0))
        if r["rank"] >= CFG["breakout"]["min_rank"]:
            keep.append(r)
    hits["breakout"] = sorted(keep, key=lambda r: (r["state"] != "Triggered", -r["rank"]))
    hits["pullback"].sort(key=lambda r: abs(r["dist"]))
    hits["htf"].sort(key=lambda r: (r["state"] != "Triggered", -r["gain"]))

    passed = len({r["key"] for rows in hits.values() for r in rows})
    out = {"asof": last, "generated": datetime.now(ZoneInfo("Asia/Kolkata")).replace(tzinfo=None).isoformat(timespec="seconds"),
           "config": CFG, "stats": {"stocks": total, "traded_last_day": traded,
                                    "ranked_for_rs": len(rs_raw), "with_a_signal": passed},
           "scans": hits}
    (DATA / "results.json").write_text(json.dumps(out))

    print(f"As of {last}.  Stocks: {total:,}   traded on last day: {traded:,}   ranked for RS: {len(rs_raw):,}")
    for name, rows in hits.items():
        print(f"\n== {name.upper()}: {len(rows)} hits")
        for r in rows[:10]:
            flag = "  [!]" if r["note"] else ""
            tag = r.get("state") or f"{r['level']} {r['dist']:+}%"
            print(f"  {r['exch']}:{r['symbol']:<12} close {r['close']:>9}  RS {r['rs']:>2}  prior move {r['prior_move']}%  "
                  f"entry {r['entry']:>9}  stop {r['stop']:>9}  risk {r['risk']}%  {tag}{flag}")


if __name__ == "__main__":
    main()
