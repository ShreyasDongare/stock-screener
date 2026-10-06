"""
Stage 1: download NSE + BSE end-of-day files (bhavcopy) into ./data/raw/

Setup (once):   pip install requests pandas
First run:      python fetch_bhav.py            (about 14 months of history)
Every evening:  python fetch_bhav.py            (skips days already saved)
Options:        --days 500   --start 2025-06-01   --only nse|bse

Raw files are kept exactly as the exchange publishes them, so a later change
in our cleaning logic never needs a re-download.
"""
import argparse, io, random, sys, time, zipfile
from datetime import date, datetime, timedelta
from pathlib import Path

import requests

RAW = Path("data/raw")

# URL templates, tried in order. {ymd}=20260105  {dmy}=050126
SOURCES = {
    "nse": [
        "https://nsearchives.nseindia.com/content/cm/BhavCopy_NSE_CM_0_0_0_{ymd}_F_0000.csv.zip",
    ],
    "bse": [
        # Newer UDiFF-style name (NOT yet verified, tell me if it fails)
        "https://www.bseindia.com/download/BhavCopy/Equity/BhavCopy_BSE_CM_0_0_0_{ymd}_F_0000.CSV",
        # Older style
        "https://www.bseindia.com/download/BhavCopy/Equity/EQ{dmy}_CSV.zip",
    ],
}
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Accept": "*/*",
    "Accept-Language": "en-US,en;q=0.9",
}


def make_session():
    s = requests.Session()
    s.headers.update(HEADERS)
    for home in ("https://www.nseindia.com", "https://www.bseindia.com"):
        try:  # pick up cookies the sites expect
            s.get(home, timeout=15)
        except requests.RequestException:
            pass
    return s


def to_csv_bytes(content):
    """Return CSV bytes from either a zip or a plain CSV, else None."""
    if content[:2] == b"PK":
        with zipfile.ZipFile(io.BytesIO(content)) as z:
            names = [n for n in z.namelist() if n.lower().endswith(".csv")]
            return z.read(names[0]) if names else None
    if content[:1] == b"<":  # an HTML error page, not data
        return None
    return content


def fetch_day(s, exch, d):
    for tpl in SOURCES[exch]:
        url = tpl.format(ymd=d.strftime("%Y%m%d"), dmy=d.strftime("%d%m%y"))
        for attempt in range(3):
            try:
                r = s.get(url, timeout=30)
            except requests.RequestException:
                time.sleep(2 * (attempt + 1))
                continue
            if r.status_code == 200 and len(r.content) > 500:
                data = to_csv_bytes(r.content)
                if data:
                    return data, url
                break
            if r.status_code in (403, 429):  # being throttled: slow down
                time.sleep(5 * (attempt + 1))
                continue
            break  # 404 etc: not published (holiday) or wrong URL
    return None, None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=420)
    ap.add_argument("--start")
    ap.add_argument("--only", choices=["nse", "bse"])
    a = ap.parse_args()

    end = date.today()
    start = datetime.strptime(a.start, "%Y-%m-%d").date() if a.start else end - timedelta(days=a.days - 1)
    exchanges = [a.only] if a.only else ["nse", "bse"]
    for e in exchanges:
        (RAW / e).mkdir(parents=True, exist_ok=True)

    s = make_session()
    saved = {e: 0 for e in exchanges}
    skipped = {e: 0 for e in exchanges}
    sample = {}
    d = start
    while d <= end:
        if True:  # weekends included on purpose: special sessions happen (e.g. Budget day)
            for e in exchanges:
                f, none = RAW / e / f"{d:%Y%m%d}.csv", RAW / e / f"{d:%Y%m%d}.none"
                if f.exists() or none.exists():
                    continue
                data, url = fetch_day(s, e, d)
                if data:
                    f.write_bytes(data)
                    saved[e] += 1
                    sample.setdefault(e, (f, url))
                    print(f"saved  {e.upper()} {d}")
                elif d < end:  # past day with no file: holiday, don't retry forever
                    none.write_text("no file")
                    skipped[e] += 1
                    print(f"none   {e.upper()} {d}")
                else:
                    print(f"wait   {e.upper()} {d} (today's file not published yet)")
                time.sleep(random.uniform(1.0, 2.0))
        d += timedelta(days=1)

    prune_old_files(end, a.days)

    print("\n--- Summary ---")
    for e in exchanges:
        have = len(list((RAW / e).glob("*.csv")))
        print(f"{e.upper()}: {saved[e]} new, {skipped[e]} holidays/missing, {have} files stored")
    for e, (f, url) in sample.items():
        print(f"\n{e.upper()} sample ({url})")
        print("\n".join(f.read_text(errors="replace").splitlines()[:3]))
    if not any(saved.values()) and not any((RAW / e).glob("*.csv") for e in exchanges):
        print("\nNothing downloaded. Copy this whole output back to me.")
        sys.exit(1)


if __name__ == "__main__":
    main()
