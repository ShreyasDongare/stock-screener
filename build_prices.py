"""
Stage 2 (v2): turn data/raw/* into one clean, split/bonus-adjusted price table.

Run:   python build_prices.py
Check: python build_prices.py --show TATAINVEST   (events + prices around the last event)

Corporate-action detection, in order:
  1. exchange  : the file's "previous close" no longer matches the last real close
  2. snapped   : one-day move beyond what price bands allow AND the ratio sits close to a
                 clean split/bonus/consolidation ratio (1:2, 1:5, 1:10 ...)
  3. review    : big one-day move that is NOT a clean ratio (demergers, capital reductions,
                 relistings). Logged, NOT adjusted. Add the ones you trust to
                 data/overrides.csv  with columns:  key,date,ratio
  4. override  : your own rows from data/overrides.csv
Outputs: data/prices.csv.gz and data/events.csv
"""
import argparse
from pathlib import Path

import numpy as np
import pandas as pd

RAW, OUT = Path("data/raw"), Path("data")

# ---- settings you can change ----
NSE_SERIES = {"EQ", "BE"}
BSE_SERIES = {"A", "B", "T", "X", "XT"}
EVENT_THRESHOLD = 0.05      # detector 1: previous-close mismatch above 5%
DROP_BELOW, JUMP_ABOVE = 0.78, 1.28   # detector 2: moves price bands can't produce
SNAP_TOLERANCE = 0.04       # how close (in log terms, ~4%) to a clean ratio to adjust. Kept tight so a
                            # genuine one-day crash in a no-price-band stock is not mistaken for a split
CLEAN_DOWN = [1 / n for n in range(2, 51)] + [2/5, 3/5, 2/3]   # splits and bonuses (3/4 removed: 4:3 is
                                                              # almost never seen, but -25% crashes are)
CLEAN_UP = list(range(2, 21))                                        # consolidations
# ---------------------------------

USE = ["TradDt", "ISIN", "TckrSymb", "SctySrs", "FinInstrmNm", "OpnPric", "HghPric",
       "LwPric", "ClsPric", "PrvsClsgPric", "TtlTradgVol", "TtlTrfVal"]
NAMES = {"TradDt": "date", "ISIN": "isin", "TckrSymb": "symbol", "SctySrs": "series",
         "FinInstrmNm": "name", "OpnPric": "open", "HghPric": "high", "LwPric": "low",
         "ClsPric": "close", "PrvsClsgPric": "prev_close_file", "TtlTradgVol": "volume",
         "TtlTrfVal": "value"}


def load(exch, keep_series):
    frames = []
    for f in sorted((RAW / exch).glob("*.csv")):
        try:
            frames.append(pd.read_csv(f, usecols=USE))
        except Exception as e:
            print(f"skipping unreadable file {f.name}: {e}")
    if not frames:
        raise SystemExit(f"No readable files in {RAW / exch}. Run fetch_bhav.py first.")
    df = pd.concat(frames, ignore_index=True).rename(columns=NAMES)
    df["exch"] = exch.upper()
    for c in ("series", "isin", "symbol"):
        df[c] = df[c].astype(str).str.strip()
    df = df[df["series"].isin(keep_series) & df["isin"].str.startswith("INE")]
    # rights entitlements / partly paid shares trade as separate "stocks" (e.g. ABC-RE)
    df = df[~df["symbol"].str.contains(r"-(?:RE|PP)\d*$", regex=True)]
    df = df[(df["close"] > 0) & (df["open"] > 0) & df["prev_close_file"].gt(0)]
    return df.sort_values(["symbol", "date", "volume"]).drop_duplicates(["symbol", "date"], keep="last")


def snap(r):
    """Nearest clean split/bonus ratio, or NaN if r is not close to any."""
    cands = CLEAN_DOWN if r < 1 else CLEAN_UP
    c = min(cands, key=lambda x: abs(np.log(r / x)))
    return c if abs(np.log(r / c)) <= SNAP_TOLERANCE else np.nan


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--show")
    a = ap.parse_args()
    if a.show:
        return show(a.show.upper())

    nse, bse = load("nse", NSE_SERIES), load("bse", BSE_SERIES)
    # Stocks listed on both: use NSE. If a stock migrated from BSE to NSE inside our window, its
    # earlier BSE bars are relabelled to the NSE symbol so the history is one continuous series.
    first_nse = nse.groupby("isin")["date"].min()
    nse_symbol = nse.sort_values("date").groupby("isin")["symbol"].last()
    both = bse[bse["isin"].isin(first_nse.index)]
    older = both[both["date"] < both["isin"].map(first_nse)].copy()
    older["symbol"] = older["isin"].map(nse_symbol)
    older["exch"] = "NSE"
    bse = bse[~bse["isin"].isin(set(nse["isin"]))]       # BSE-exclusive stocks only
    df = pd.concat([nse, older, bse], ignore_index=True)
    df["key"] = df["exch"] + ":" + df["symbol"]           # symbol, not ISIN: ISINs change at splits
    df = df.sort_values(["key", "date"]).reset_index(drop=True)
    df["prev_actual"] = df.groupby("key")["close"].shift(1)

    # detector 1: exchange-adjusted previous close
    r1 = df["prev_close_file"] / df["prev_actual"]
    e1 = r1.notna() & ((r1 < 1 - EVENT_THRESHOLD) | (r1 > 1 + EVENT_THRESHOLD))
    df["observed"] = r1.where(e1)
    df["factor"] = r1.where(e1, 1.0)
    df["method"] = np.where(e1, "exchange", "")

    # detector 2: impossible-for-price-bands moves that sit on a clean ratio
    raw = df["close"] / df["prev_actual"]
    cand = ~e1 & raw.notna() & ((raw < DROP_BELOW) | (raw > JUMP_ABOVE))
    df.loc[cand, "observed"] = raw[cand]
    sn = raw[cand].apply(snap)
    df.loc[cand, "factor"] = sn.fillna(1.0)
    df.loc[cand, "method"] = np.where(sn.isna(), "review", "snapped")

    # your manual overrides
    ov = OUT / "overrides.csv"
    if ov.exists():
        for o in pd.read_csv(ov).itertuples():
            m = (df["key"] == o.key) & (df["date"] == o.date)
            df.loc[m, "factor"] = o.ratio
            df.loc[m, "method"] = "override"
            if df.loc[m, "observed"].isna().all():
                df.loc[m, "observed"] = (df["close"] / df["prev_actual"])[m]

    ev = df.loc[df["method"] != "", ["key", "date", "name", "prev_actual", "close",
                                     "observed", "factor", "method"]].copy()
    ev[["observed", "factor"]] = ev[["observed", "factor"]].round(4)
    ev.to_csv(OUT / "events.csv", index=False)

    # each bar is scaled by the product of all factors that happen AFTER it
    after = lambda s: s[::-1].cumprod()[::-1] / s
    df["adj"] = df.groupby("key")["factor"].transform(after)
    df["raw_close"] = df["close"]
    for c in ["open", "high", "low", "close"]:
        df[c] = df[c] * df["adj"]
    df["volume"] = df["volume"] / df["adj"]

    cols = ["key", "exch", "symbol", "isin", "name", "date", "open", "high", "low",
            "close", "volume", "value", "raw_close"]
    df[cols].to_csv(OUT / "prices.csv.gz", index=False)

    print(f"Rows: {len(df):,}   Stocks: {df['key'].nunique():,}   Last date: {df['date'].max()}")
    print(df.groupby("exch")["key"].nunique().to_string())
    print("\nEvents by method:\n" + ev["method"].value_counts().to_string())
    rv = ev[ev["method"] == "review"].sort_values("date")
    print(f"\nNot adjusted, need your eyes ({len(rv)}), latest 25:")
    print(rv.tail(25)[["key", "date", "prev_actual", "close", "observed"]].to_string(index=False))


def show(sym):
    px = pd.read_csv(OUT / "prices.csv.gz")
    ev = pd.read_csv(OUT / "events.csv")
    px = px[px["symbol"] == sym].sort_values("date").reset_index(drop=True)
    if px.empty:
        print("symbol not found")
        return
    e = ev[ev["key"] == px["key"].iloc[0]]
    print("events:", e.to_string(index=False) if len(e) else "none")
    if len(e):  # show the days around the last event, adjusted vs raw
        pos = px.index[px["date"] == e["date"].iloc[-1]]
        if len(pos):
            p = pos[0]
            print(px.iloc[max(0, p - 3):p + 3][["date", "close", "raw_close", "volume"]].round(2).to_string(index=False))
    else:
        print(px[["date", "close", "raw_close", "volume"]].tail(5).round(2).to_string(index=False))


if __name__ == "__main__":
    main()
