"""Build full-history chart data for stocks currently found by the scanner."""
import concurrent.futures
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

import numpy as np
import requests

DATA = Path("data")
RESULTS = DATA / "results.json"
OUT = DATA / "chart_data.json"
HEADERS = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/154 Safari/537.36"}

def yahoo_symbol(key):
    exch, symbol = key.split(":", 1)
    return f"{symbol}.NS" if exch.upper() == "NSE" else f"{symbol}.BO"

def fetch_one(key):
    ticker = yahoo_symbol(key)
    url = ("https://query1.finance.yahoo.com/v8/finance/chart/" + quote(ticker, safe="") +
           "?period1=0&period2=" + str(int(datetime.now(timezone.utc).timestamp())) +
           "&interval=1d&events=div%2Csplits&includeAdjustedClose=true")
    last_err = ""
    for attempt in range(4):
        try:
            r = requests.get(url, headers=HEADERS, timeout=30)
            if r.status_code == 200:
                result = ((r.json().get("chart") or {}).get("result") or [None])[0]
                if not result:
                    return key, None, "no data"
                ts = result.get("timestamp") or []
                q = (result.get("indicators") or {}).get("quote", [{}])[0]
                adj = ((result.get("indicators") or {}).get("adjclose") or [{}])[0].get("adjclose") or []
                if not ts:
                    return key, None, "empty history"
                rows = []
                for i, epoch in enumerate(ts):
                    vals = [q.get(k, [None] * len(ts))[i] if i < len(q.get(k, [])) else None
                            for k in ("open","high","low","close","volume")]
                    if any(v is None for v in vals[:4]):
                        continue
                    raw_close = float(vals[3])
                    if raw_close <= 0:
                        continue
                    ac = adj[i] if i < len(adj) else None
                    factor = float(ac) / raw_close if ac not in (None, 0) else 1.0
                    rows.append({
                        "date": datetime.fromtimestamp(epoch, timezone.utc).date().isoformat(),
                        "open": round(float(vals[0]) * factor, 4),
                        "high": round(float(vals[1]) * factor, 4),
                        "low": round(float(vals[2]) * factor, 4),
                        "close": round(float(ac) if ac not in (None, 0) else raw_close, 4),
                        "volume": int(vals[4] or 0)
                    })
                if not rows:
                    return key, None, "no usable rows"
                close = np.array([x["close"] for x in rows], dtype=float)
                def ema(span):
                    a = 2 / (span + 1); prev = close[0]; out = []
                    for x in close:
                        prev = a*x + (1-a)*prev; out.append(round(float(prev),4))
                    return out
                def sma(n):
                    return [round(float(np.mean(close[max(0,i-n+1):i+1])),4) if i >= n-1 else None
                            for i in range(len(close))]
                return key, {
                    "symbol": ticker.rsplit(".",1)[0], "exch": key.split(":",1)[0],
                    "dates":[x["date"] for x in rows], "open":[x["open"] for x in rows],
                    "high":[x["high"] for x in rows], "low":[x["low"] for x in rows],
                    "close":[x["close"] for x in rows], "volume":[x["volume"] for x in rows],
                    "ema11":ema(11), "ema21":ema(21), "sma50":sma(50)
                }, None
            last_err = f"HTTP {r.status_code}"
        except Exception as e:
            last_err = str(e)
        time.sleep(1.5*(attempt+1))
    return key, None, last_err

def main():
    payload = json.loads(RESULTS.read_text())
    keys = sorted({r["key"] for rows in payload["scans"].values() for r in rows})
    print(f"Building full chart history for {len(keys)} scanned stocks...")
    chart, failures = {}, []
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        futures = [pool.submit(fetch_one, key) for key in keys]
        for i, f in enumerate(concurrent.futures.as_completed(futures), 1):
            key, data, err = f.result()
            if data:
                chart[key] = data
                print(f"[{i}/{len(keys)}] {key}: {len(data['dates'])} sessions")
            else:
                failures.append((key,err)); print(f"[{i}/{len(keys)}] {key}: FAILED - {err}")
    OUT.write_text(json.dumps(chart, separators=(",",":")))
    print(f"Saved {len(chart)} histories to {OUT}. Failures: {len(failures)}")

if __name__ == "__main__":
    main()
