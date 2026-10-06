"""
Stage 3 (v2): three scans on the adjusted prices from build_prices.py.

  1. Strong Stage 2   : Minervini-style trend template + relative strength rank
  2. Pullback         : close within +/-2% of EMA11 / EMA21 / SMA50 (tightness only)
  3. High tight flag  : big run-up, then a tight flag (forming or triggered)

Run:  python run_scans.py
Out:  data/results.json   (the dashboard reads this)
All settings are in CFG below.
"""
import json
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

DATA = Path("data")

# ------------------------- settings -------------------------
CFG = {
    "min_bars": 80,                 # minimum history for any scan
    "min_adr_pct": 3.0,             # 20-day average daily range %, applies to ALL scans
    "min_avg_value_cr": 1.0,        # 20-day avg traded value in rupees crore, applies to ALL scans
    "max_risk_pct": None,           # pullback / flag only: e.g. 10 drops setups with stop wider than 10%
    "stage2": {                     # needs 253+ bars (SMA200 + 52-week range + 12-month RS)
        "slope_days": 22,           # 200-day average must be higher than this many days ago
        "min_above_low_pct": 30,    # close at least 30% above the 52-week low
        "max_below_high_pct": 25,   # close within 25% of the 52-week high
        "min_rs": 70,               # relative strength rank 1-99 among liquid stocks
    },
    "pullback": {"tight_pct": 2.0, "levels": ["EMA11", "EMA21", "SMA50"]},
    "momentum": {                   # close now vs close N trading days ago
        "enabled": False,                       # off: set True to require the returns below
        "match": "any",                         # "any" = one of the three is enough, "all" = every one
        "apply_to": ["stage2", "pullback"],     # the flag scan has its own run-up rule
        "days": {"1m": 21, "3m": 63, "6m": 126},
        "min_pct": {"1m": 30, "3m": 50, "6m": 100},
    },
    "ema_then": {                   # stock must also have closed above its EMA 21 back then
        "enabled": True,
        "days_ago": 21,             # 21 trading days is about 30 calendar days
        "apply_to": ["stage2", "pullback"],
    },
    "htf": {"flagpole_days": 40, "min_gain_pct": 70, "flag_min_days": 15,
            "flag_max_days": 25, "max_pullback_pct": 25},
}
# ------------------------------------------------------------


def num(x, d=2):
    return round(float(x), d) if np.isfinite(x) else None


def analyse(key, g, review_keys, recent_keys):
    """Returns (info, hits). info feeds the RS ranking, hits are scan results."""
    n = len(g)
    info = {"key": key, "rs_raw": None}
    if n < CFG["min_bars"]:
        return info, {}
    c, h, v = (g[k].to_numpy(float) for k in ("close", "high", "volume"))
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
    if not liquid or adr < CFG["min_adr_pct"]:
        return info, {}

    s = pd.Series(c)
    ema11 = s.ewm(span=11, adjust=False).mean().to_numpy()
    ema21 = s.ewm(span=21, adjust=False).mean().to_numpy()
    sma50 = s.rolling(50).mean().to_numpy()

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
        key=key, symbol=row0["symbol"], exch=row0["exch"], name=row0["name"],
        close=num(c[i]), chg=num((c[i] / c[i - 1] - 1) * 100), adr=num(adr, 1),
        value_cr=num(avg_val_cr, 1), ema11=num(ema11[i]), ema21=num(ema21[i]),
        sma50=num(sma50[i]), spark=[num(x) for x in c[-40:]], note="; ".join(note),
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

    # ---- 1. strong Stage 2 (rank filter is applied after all stocks are scored) ----
    if n >= 253 and passes("stage2"):
        st = CFG["stage2"]
        sma150 = s.rolling(150).mean().to_numpy()
        sma200 = s.rolling(200).mean().to_numpy()
        hi52, lo52 = h[-252:].max(), l[-252:].min()
        if (c[i] > sma150[i] and c[i] > sma200[i] and sma150[i] > sma200[i]
                and sma50[i] > sma150[i] and sma50[i] > sma200[i] and c[i] > sma50[i]
                and sma200[i] > sma200[i - st["slope_days"]]
                and c[i] >= lo52 * (1 + st["min_above_low_pct"] / 100)
                and c[i] >= hi52 * (1 - st["max_below_high_pct"] / 100)):
            out["stage2"] = {**base, "off_high": num((1 - c[i] / hi52) * 100, 1),
                             "above_low": num((c[i] / lo52 - 1) * 100, 0),
                             "sma200_slope": num((sma200[i] / sma200[i - st["slope_days"]] - 1) * 100, 1),
                             "signal": "Stage 2 uptrend"}

    # pullback and flag also need the short-term trend stack
    if not (ema11[i] > ema21[i] > sma50[i] and c[i] > sma50[i]):
        return info, out

    # ---- 2. pullback: tightness only, close within +/-X% of a moving average ----
    p = CFG["pullback"]
    levels = {"EMA11": ema11[i], "EMA21": ema21[i], "SMA50": sma50[i]}
    best = min(((abs(c[i] / levels[k] - 1) * 100, k) for k in p["levels"]), key=lambda t: t[0])
    if best[0] <= p["tight_pct"] and passes("pullback"):
        k = best[1]
        finish("pullback", h[i], l[-5:].min(), level=k, dist=num((c[i] / levels[k] - 1) * 100, 2),
               signal=f"Within {p['tight_pct']:g}% of {k}")

    # ---- 3. high tight flag (relaxed) ----
    f = CFG["htf"]
    fmax = f["flag_max_days"]
    pk = i - fmax + int(np.argmax(h[i - fmax:i]))      # flag peak, before today
    flag_len = i - pk
    if f["flag_min_days"] <= flag_len <= fmax and passes("htf"):
        top = h[pk]
        gain = (top / l[max(0, pk - f["flagpole_days"]):pk + 1].min() - 1) * 100
        flag_low = l[pk + 1:i + 1].min()
        pb = (top - flag_low) / top * 100
        if gain >= f["min_gain_pct"] and pb <= f["max_pullback_pct"]:
            if c[i] > top:
                finish("htf", h[i], flag_low, state="Triggered", gain=num(gain, 0),
                       flag_days=int(flag_len), pullback=num(pb, 1), signal="Broke flag high")
            elif c[i] >= top * (1 - f["max_pullback_pct"] / 100):
                finish("htf", top, flag_low, state="Forming", gain=num(gain, 0),
                       flag_days=int(flag_len), pullback=num(pb, 1), signal="In flag, trigger above high")
    return info, out


def main():
    df = pd.read_csv(DATA / "prices.csv.gz").sort_values(["key", "date"])
    ev = pd.read_csv(DATA / "events.csv")
    dates = sorted(df["date"].unique())
    last = dates[-1]
    review_keys = set(ev.loc[ev["method"] == "review", "key"])
    recent_keys = set(ev.loc[(ev["method"] != "review") & (ev["date"] >= dates[-60]), "key"])

    hits = {"stage2": [], "pullback": [], "htf": []}
    rs_raw = {}
    total = traded = 0
    for key, g in df.groupby("key", sort=False):
        total += 1
        if g["date"].iloc[-1] != last:      # not traded on the latest day: stale or suspended
            continue
        traded += 1
        info, res = analyse(key, g, review_keys, recent_keys)
        if info["rs_raw"] is not None:
            rs_raw[key] = info["rs_raw"]
        for name, row in res.items():
            hits[name].append(row)

    # relative strength rank 1-99 among liquid stocks with a full year of history
    rank = (pd.Series(rs_raw).rank(pct=True) * 98 + 1).round().astype(int)
    keep = []
    for r in hits["stage2"]:
        r["rs"] = int(rank.get(r["key"], 0))
        if r["rs"] >= CFG["stage2"]["min_rs"]:
            keep.append(r)
    hits["stage2"] = sorted(keep, key=lambda r: -r["rs"])
    hits["pullback"].sort(key=lambda r: abs(r["dist"]))
    hits["htf"].sort(key=lambda r: (r["state"] != "Triggered", -r["gain"]))

    passed = len({r["key"] for rows in hits.values() for r in rows})
    out = {"asof": last, "generated": datetime.now().isoformat(timespec="seconds"),
           "config": CFG, "stats": {"stocks": total, "traded_last_day": traded,
                                    "ranked_for_rs": len(rs_raw), "with_a_signal": passed},
           "scans": hits}
    (DATA / "results.json").write_text(json.dumps(out))

    print(f"As of {last}.  Stocks: {total:,}   traded on last day: {traded:,}   ranked for RS: {len(rs_raw):,}")
    for name, rows in hits.items():
        print(f"\n== {name.upper()}: {len(rows)} hits")
        for r in rows[:10]:
            flag = "  [!]" if r["note"] else ""
            if name == "stage2":
                print(f"  {r['exch']}:{r['symbol']:<12} close {r['close']:>9}  RS {r['rs']:>2}  "
                      f"1M {r['ret1m']}%  3M {r['ret3m']}%  6M {r['ret6m']}%  off high {r['off_high']}%{flag}")
            else:
                tag = r.get("state") or f"{r['level']} {r['dist']:+}%"
                print(f"  {r['exch']}:{r['symbol']:<12} close {r['close']:>9}  entry {r['entry']:>9}  "
                      f"stop {r['stop']:>9}  risk {r['risk']}%  ADR {r['adr']}%  {tag}{flag}")


if __name__ == "__main__":
    main()
