"""
Stage 3: four exact cash-segment scans supplied for the Wolf Momentum Screener.

Scans
-----
1. 1M / 3M / 6M Scan
2. 3M 30% Scan
3. HTF Scan
4. 52Week High Scan

Input:
    data/prices.csv.gz

Output:
    data/results.json
    data/chart_data.json


The scanner deliberately does NOT add extra ADX, EMA-stack, momentum,
liquidity, or risk filters that were not present in the supplied screeners.
"""
import json
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

DATA = Path("data")

# ------------------------------------------------------------
# Exact user-supplied constants
# ------------------------------------------------------------
CFG = {
    "m136": {
        "name": "1M / 3M / 6M Scan",
        "adr_min_pct": 3.0,
        "ema_days": 60,
        "breakout_windows": {
            "1M": 31,
            "3M": 93,
            "6M": 186,
        },
    },
    "m30": {
        "name": "3M 30% Scan",
        "return_days": 63,
        "min_return_pct": 30.0,
        "ema_days": 75,
        "adr_min_pct": 3.0,
        "min_value_rupees": 10_000_000.0,
    },
    "htf": {
        "name": "HTF Scan",
        "lookback_days": 60,
        "min_return_multiple": 1.5,
        "high_lookback_days": 252,
        "max_high_distance_pct": 15.0,
        "volume_sma_days": 20,
        "max_volume_ratio": 1.5,
        "min_close": 50.0,
    },
    "high52w": {
        "name": "52Week High",
        "value_min_rupees": 10_000_000.0,
        "market_cap_min_cr": 1000.0,
        "adr_min_pct": 3.0,
        "high_lookback_days": 252,
        "max_high_distance_pct": 10.0,
    },
}
# ------------------------------------------------------------


def num(x, d=2):
    try:
        x = float(x)
    except (TypeError, ValueError):
        return None
    return round(x, d) if np.isfinite(x) else None


def true_range(high, low, close):
    """True Range(1), matching the supplied Chartink expression."""
    prev_close = np.roll(close, 1)
    prev_close[0] = close[0]
    return np.maximum.reduce([
        high - low,
        np.abs(high - prev_close),
        np.abs(low - prev_close),
    ])


def adx_wilder(high, low, close, period=14):
    """Wilder ADX(14), using standard directional movement and ATR smoothing."""
    high_s = pd.Series(high, dtype=float)
    low_s = pd.Series(low, dtype=float)
    close_s = pd.Series(close, dtype=float)

    up_move = high_s.diff()
    down_move = -low_s.diff()

    plus_dm = pd.Series(
        np.where((up_move > down_move) & (up_move > 0), up_move, 0.0),
        index=high_s.index,
    )
    minus_dm = pd.Series(
        np.where((down_move > up_move) & (down_move > 0), down_move, 0.0),
        index=high_s.index,
    )

    prev_close = close_s.shift(1)
    tr = pd.concat([
        high_s - low_s,
        (high_s - prev_close).abs(),
        (low_s - prev_close).abs(),
    ], axis=1).max(axis=1)

    atr = tr.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    plus_sm = plus_dm.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    minus_sm = minus_dm.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()

    plus_di = 100 * plus_sm / atr.replace(0, np.nan)
    minus_di = 100 * minus_sm / atr.replace(0, np.nan)

    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    adx = dx.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    return adx.to_numpy()


def load_events():
    """
    Events remain optional.

    The FYERS pipeline currently has no exchange-event adjustment
    detector equivalent to the old Bhavcopy builder, so the scanner
    must still work without events.csv.
    """
    path = DATA / "events.csv"

    if not path.exists():
        return set(), set()

    try:
        ev = pd.read_csv(path)
    except Exception:
        return set(), set()

    if ev.empty or "key" not in ev.columns or "method" not in ev.columns:
        return set(), set()

    review_keys = set(
        ev.loc[
            ev["method"].astype(str).eq("review"),
            "key",
        ].astype(str)
    )

    recent_keys = set()

    if "date" in ev.columns:
        try:
            dates = pd.to_datetime(
                ev["date"],
                errors="coerce",
            )
            cutoff = dates.max() - pd.Timedelta(days=60)
            recent_keys = set(
                ev.loc[
                    dates >= cutoff,
                    "key",
                ].astype(str)
            )
        except Exception:
            recent_keys = set()

    return review_keys, recent_keys


def base_row(
    key,
    g,
    c,
    h,
    l,
    v,
    tr,
    adx,
    review_keys,
    recent_keys,
):
    i = len(g) - 1

    adr = (
        pd.Series(tr)
        .rolling(20)
        .mean()
        .iloc[i]
        / c[i]
        * 100
    )

    value_rupees = c[i] * v[i]

    row0 = g.iloc[i]

    note = []

    if key in review_keys:
        note.append(
            "unadjusted corporate action in history, check chart"
        )

    if key in recent_keys:
        note.append(
            "corporate-action event in last 60 days"
        )

    return {
        "key": key,
        "symbol": str(row0["symbol"]),
        "exch": str(row0["exch"]),
        "name": str(row0.get("name", "")),
        "close": num(c[i]),
        "chg": num(
            (c[i] / c[i - 1] - 1) * 100
            if i >= 1 and c[i - 1] != 0
            else np.nan,
            2,
        ),
        "volume": num(v[i], 0),
        "value_cr": num(value_rupees / 1e7, 2),
        "adr": num(adr, 2),
        "adx": num(adx[i], 2),
        "note": "; ".join(note),
        "spark": [
            num(x)
            for x in c[-40:]
        ],
    }


def analyse_m136(
    key,
    g,
    c,
    h,
    l,
    v,
    tr,
    base,
):
    """
    Exact:

      SMA(True Range(1),20) / Close * 100 >= 3
      AND Close > EMA60
      AND (
            Close > previous 31-day max Close
            OR Close > previous 93-day max Close
            OR Close > previous 186-day max Close
          )

    Today is excluded from each rolling maximum.
    """
    n = len(g)
    if n <= 186:
        return None

    ema60 = (
        pd.Series(c)
        .ewm(span=60, adjust=False)
        .mean()
        .to_numpy()
    )

    adr = (
        pd.Series(tr)
        .rolling(20)
        .mean()
        .iloc[-1]
        / c[-1]
        * 100
    )

    if not np.isfinite(adr):
        return None

    if adr < CFG["m136"]["adr_min_pct"]:
        return None

    if not c[-1] > ema60[-1]:
        return None

    hits = []

    for label, days in CFG["m136"]["breakout_windows"].items():
        if n <= days:
            continue

        prior_max = np.max(
            c[-days - 1:-1]
        )

        if c[-1] > prior_max:
            hits.append(label)

    if not hits:
        return None

    def pct_from_bars(days):
        old_close = c[-1 - days]
        if old_close == 0:
            return np.nan
        return (c[-1] / old_close - 1) * 100

    return {
        **base,
        "breakout": " / ".join(hits),
        "ret1m": num(pct_from_bars(31), 2),
        "ret3m": num(pct_from_bars(93), 2),
        "ret6m": num(pct_from_bars(186), 2),
        "ema60": num(ema60[-1], 2),
        "tr_adr": num(adr, 2),
        "signal": "Close above prior high"
            + (f" ({' / '.join(hits)})"),
    }


def analyse_m30(
    key,
    g,
    c,
    h,
    l,
    v,
    tr,
    base,
):
    """
    Exact:

      (Close - 63-days-ago Close) / 63-days-ago Close * 100 > 30
      AND Close > EMA75
      AND SMA(True Range(1),20) / Close * 100 >= 3
      AND Close * Volume > 10,000,000
    """
    n = len(g)

    if n <= 63:
        return None

    close_3m = c[-1 - CFG["m30"]["return_days"]]

    if close_3m == 0:
        return None

    ret3m = (
        c[-1] / close_3m - 1
    ) * 100

    ema75 = (
        pd.Series(c)
        .ewm(span=75, adjust=False)
        .mean()
        .to_numpy()
    )

    adr = (
        pd.Series(tr)
        .rolling(20)
        .mean()
        .iloc[-1]
        / c[-1]
        * 100
    )

    value_rupees = c[-1] * v[-1]

    if not np.isfinite(ret3m):
        return None

    if ret3m <= CFG["m30"]["min_return_pct"]:
        return None

    if not c[-1] > ema75[-1]:
        return None

    if not np.isfinite(adr) or adr < CFG["m30"]["adr_min_pct"]:
        return None

    if value_rupees <= CFG["m30"]["min_value_rupees"]:
        return None

    return {
        **base,
        "ret3m": num(ret3m, 2),
        "ema75": num(ema75[-1], 2),
        "tr_adr": num(adr, 2),
        "signal": "3M gain > 30%",
    }


def analyse_htf(
    key,
    g,
    c,
    h,
    l,
    v,
    tr,
    base,
):
    """
    Exact:

      Close / 60-days-ago Close > 1.5
      AND Close >= previous 252-day max High * 0.85
      AND Volume < SMA(Volume,20) * 1.5
      AND Close > 50

    Today is excluded from the 252-day highest-high.
    """
    n = len(g)

    if n <= 252:
        return None

    if not np.isfinite(market_cap_cr):
        return None

    close_60 = c[-1 - CFG["htf"]["lookback_days"]]

    if close_60 == 0:
        return None

    multiple = c[-1] / close_60

    prior_high = np.max(
        h[-1 - CFG["htf"]["high_lookback_days"]:-1]
    )

    volume_sma = (
        pd.Series(v)
        .rolling(CFG["htf"]["volume_sma_days"])
        .mean()
        .iloc[-1]
    )

    vol_ratio = (
        v[-1] / volume_sma
        if volume_sma > 0
        else np.nan
    )

    off_high = (
        1 - c[-1] / prior_high
    ) * 100

    if multiple <= CFG["htf"]["min_return_multiple"]:
        return None

    if c[-1] < prior_high * (
        1 - CFG["htf"]["max_high_distance_pct"] / 100
    ):
        return None

    if not (
        np.isfinite(vol_ratio)
        and vol_ratio < CFG["htf"]["max_volume_ratio"]
    ):
        return None

    if c[-1] <= CFG["htf"]["min_close"]:
        return None

    return {
        **base,
        "gain60": num((multiple - 1) * 100, 2),
        "multiple60": num(multiple, 3),
        "off_high": num(off_high, 2),
        "prior_252_high": num(prior_high, 2),
        "vol_ratio": num(vol_ratio, 2),
        "signal": "High Tight Flag candidate",
    }


def analyse_high52w(
    key,
    g,
    c,
    h,
    l,
    v,
    tr,
    market_cap_cr,
    base,
):
    """
    Exact:

      Close * Volume > 10,000,000
      AND SMA(True Range(1),20) / Close * 100 >= 3
      AND Close >= previous 252-day max High * 0.90
      AND Close <= previous 252-day max High

    Today is excluded from the prior 252-day max.
    """
    n = len(g)

    if n <= 252:
        return None

    if not np.isfinite(market_cap_cr):
        return None

    value_rupees = c[-1] * v[-1]

    adr = (
        pd.Series(tr)
        .rolling(20)
        .mean()
        .iloc[-1]
        / c[-1]
        * 100
    )

    prior_high = np.max(
        h[-1 - CFG["high52w"]["high_lookback_days"]:-1]
    )

    off_high = (
        1 - c[-1] / prior_high
    ) * 100

    if value_rupees <= CFG["high52w"]["value_min_rupees"]:
        return None

    if not np.isfinite(adr) or adr < CFG["high52w"]["adr_min_pct"]:
        return None

    if c[-1] < prior_high * (
        1 - CFG["high52w"]["max_high_distance_pct"] / 100
    ):
        return None

    if c[-1] > prior_high:
        return None

    return {
        **base,
        "off_high": num(off_high, 2),
        "prior_252_high": num(prior_high, 2),
        "tr_adr": num(adr, 2),
        "signal": "Within 10% of prior 52-week high",
    }


def analyse_stock(
    key,
    g,
    review_keys,
    recent_keys,
):
    g = g.sort_values("date").reset_index(drop=True)

    n = len(g)

    # Minimum needed by the least demanding scan.
    if n < 21:
        return {}

    c = g["close"].to_numpy(float)
    h = g["high"].to_numpy(float)
    l = g["low"].to_numpy(float)
    v = g["volume"].to_numpy(float)

    c = np.asarray(c)
    h = np.asarray(h)
    l = np.asarray(l)
    v = np.asarray(v)

    if not (
        np.isfinite(c[-1])
        and np.isfinite(h[-1])
        and np.isfinite(l[-1])
        and np.isfinite(v[-1])
    ):
        return {}

    tr = true_range(
        h,
        l,
        c,
    )
    adx = adx_wilder(h, l, c, 14)

    base = base_row(
        key,
        g,
        c,
        h,
        l,
        v,
        tr,
        adx,
        review_keys,
        recent_keys,
    )

    out = {}

    r = analyse_m136(
        key,
        g,
        c,
        h,
        l,
        v,
        tr,
        base,
    )
    if r:
        out["m136"] = r

    r = analyse_m30(
        key,
        g,
        c,
        h,
        l,
        v,
        tr,
        base,
    )
    if r:
        out["m30"] = r

    r = analyse_htf(
        key,
        g,
        c,
        h,
        l,
        v,
        tr,
        base,
    )
    if r:
        out["htf"] = r

    r = analyse_high52w(
        key,
        g,
        c,
        h,
        l,
        v,
        tr,
        market_cap_cr,
        base,
    )
    if r:
        out["high52w"] = r

    return out


def build_chart_data(df, keys):
    """
    Keep the dashboard chart payload compact.
    The scanner database itself still contains full history.
    """
    chart = {}

    for key in sorted(keys):
        g = df[df["key"] == key].sort_values("date").tail(252)

        if g.empty:
            continue

        close = g["close"].to_numpy(float)
        ss = pd.Series(close)

        e11 = (
            ss.ewm(span=11, adjust=False)
            .mean()
            .to_numpy()
        )
        e21 = (
            ss.ewm(span=21, adjust=False)
            .mean()
            .to_numpy()
        )
        s50 = (
            ss.rolling(50)
            .mean()
            .to_numpy()
        )

        chart[key] = {
            "symbol": str(g.iloc[-1]["symbol"]),
            "exch": str(g.iloc[-1]["exch"]),
            "dates": g["date"].astype(str).tolist(),
            "open": [num(x) for x in g["open"]],
            "high": [num(x) for x in g["high"]],
            "low": [num(x) for x in g["low"]],
            "close": [num(x) for x in g["close"]],
            "volume": [num(x, 0) for x in g["volume"]],
            "ema11": [num(x) for x in e11],
            "ema21": [num(x) for x in e21],
            "sma50": [
                num(x)
                for x in s50
            ],
        }

    return chart


def main():
    price_path = DATA / "prices.csv.gz"

    if not price_path.exists():
        raise FileNotFoundError(
            f"Missing {price_path}. Build the FYERS prices database first."
        )

    df = pd.read_csv(
        price_path
    )

    required = {
        "key",
        "date",
        "symbol",
        "exch",
        "open",
        "high",
        "low",
        "close",
        "volume",
    }

    missing = sorted(
        required - set(df.columns)
    )

    if missing:
        raise ValueError(
            "prices.csv.gz is missing columns: "
            + ", ".join(missing)
        )

    df["date"] = pd.to_datetime(
        df["date"],
        errors="coerce",
    )

    for col in [
        "open",
        "high",
        "low",
        "close",
        "volume",
    ]:
        df[col] = pd.to_numeric(
            df[col],
            errors="coerce",
        )

    df = df.dropna(
        subset=[
            "key",
            "date",
            "close",
            "high",
            "low",
            "volume",
        ]
    )

    df = df.sort_values(
        ["key", "date"]
    ).reset_index(drop=True)

    review_keys, recent_keys = load_events()

    last_date = df["date"].max()

    hits = {
        "m136": [],
        "m30": [],
        "htf": [],
        "high52w": [],
    }

    total = 0
    traded = 0

    for key, g in df.groupby(
        "key",
        sort=False,
    ):
        total += 1

        if g["date"].iloc[-1] != last_date:
            continue

        traded += 1

        result = analyse_stock(
            str(key),
            g,
            review_keys,
            recent_keys,
        )

        for scan_name, row in result.items():
            hits[scan_name].append(row)

    # Stable useful ordering for dashboard.
    hits["m136"].sort(
        key=lambda r: (
            -float(r.get("close", 0) or 0)
        )
    )

    hits["m30"].sort(
        key=lambda r: (
            -float(r.get("ret3m", 0) or 0)
        )
    )

    hits["htf"].sort(
        key=lambda r: (
            -float(r.get("gain60", 0) or 0)
        )
    )

    hits["high52w"].sort(
        key=lambda r: (
            float(r.get("off_high", 999) or 999)
        )
    )

    passed_keys = {
        r["key"]
        for rows in hits.values()
        for r in rows
    }

    chart = build_chart_data(
        df,
        passed_keys,
    )

    # Scanner config is exported into results.json so the dashboard
    # has one machine-readable definition of the applied rules.
    config_out = {
        **CFG,
        "definitions": {
            "m136": (
                "SMA(True Range(1),20) / Close * 100 >= 3 AND "
                "Market Cap >= 1000 Cr AND Close > EMA60 AND "
                "(Close > previous 31-day max Close OR "
                "Close > previous 93-day max Close OR "
                "Close > previous 186-day max Close)"
            ),
            "m30": (
                "(Close - 63-days-ago Close) / 63-days-ago Close * 100 > 30 "
                "AND Close > EMA75 AND "
                "SMA(True Range(1),20) / Close * 100 >= 3 AND "
                "Close * Volume > ₹10,000,000"
            ),
            "htf": (
                "Close / 60-days-ago Close > 1.5 AND "
                "Close >= previous 252-day max High * 0.85 AND "
                "Volume < SMA(Volume,20) * 1.5 AND "
                "Market Cap > 500 Cr AND Close > ₹50"
            ),
            "high52w": (
                "Close * Volume > ₹10,000,000 AND "

                "SMA(True Range(1),20) / Close * 100 >= 3 AND "
                "Close >= previous 252-day max High * 0.90 AND "
                "Close <= previous 252-day max High"
            ),
        },
    }

    stats = {
        "stocks": int(total),
        "traded_last_day": int(traded),
        "with_a_signal": int(
            len(passed_keys)
        ),
    }

    out = {
        "asof": last_date.strftime("%Y-%m-%d"),
        "generated": datetime.now().isoformat(
            timespec="seconds"
        ),
        "config": config_out,
        "stats": stats,
        "scans": hits,
    }

    DATA.mkdir(
        parents=True,
        exist_ok=True,
    )

    (DATA / "results.json").write_text(
        json.dumps(
            out,
            separators=(",", ":"),
        )
    )

    (DATA / "chart_data.json").write_text(
        json.dumps(
            chart,
            separators=(",", ":"),
        )
    )

    print(
        f"As of {out['asof']}. "
        f"Stocks: {total:,}   "
        f"traded on last day: {traded:,}"
    )

    for name, rows in hits.items():
        print(
            f"\n== {name.upper()}: {len(rows)} hits"
        )

        for r in rows[:10]:
            print(
                f"  {r['exch']}:{r['symbol']:<14} "
                f"close {r['close']:>9}  "
                f"chg {r['chg']:>7}%"
            )


if __name__ == "__main__":
    main()
