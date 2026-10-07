"""
Stage 1: download NSE + BSE end-of-day files (bhavcopy) into ./data/raw/

Setup (once):   pip install requests pandas
First run:      python fetch_bhav.py            (about 14 months of history)
Every evening:  python fetch_bhav.py            (skips days already saved)
Options:        --days 500   --start 2025-06-01   --only nse|bse
                --wait 60   if today's file is not out yet, retry every 10 min for up to 60 min

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
        # UDiFF-style name (same columns as NSE). The old EQddmmyy_CSV.zip format was removed:
        # it has no ISIN or date column, so build_prices.py could not read it anyway.
        "https://www.bseindia.com/download/BhavCopy/Equity/BhavCopy_BSE_CM_0_0_0_{ymd}_F_0000.CSV",
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
    """Returns (data, url, certain_missing).

    certain_missing is True only when every source answered clearly "no such file"
    (404, or a 200 that is an HTML page). Timeouts, 403/429 throttling and 5xx
    errors are NOT certain: the file may exist, so the caller must not cache them
    as a holiday.
    """
    certain = True
    for tpl in SOURCES[exch]:
        url = tpl.format(ymd=d.strftime("%Y%m%d"), dmy=d.strftime("%d%m%y"))
        outcome = "error"
        for attempt in range(3):
            try:
                r = s.get(url, timeout=30)
            except requests.RequestException:
                time.sleep(2 * (attempt + 1))
                continue
            if r.status_code == 200 and len(r.content) > 500:
                data = to_csv_bytes(r.content)
                if data:
                    return data, url, False
                outcome = "missing"          # HTML page instead of data
                break
            if r.status_code in (403, 429):  # being throttled: slow down, retry
                time.sleep(5 * (attempt + 1))
                continue
            if r.status_code in (200, 404):  # clear "not published" (holiday etc.)
                outcome = "missing"
                break
            time.sleep(2 * (attempt + 1))    # 5xx and anything else: retry
        if outcome != "missing":
            certain = False
    return None, None, certain


def prune_old_files(end, days):
    """Keep only the requested rolling calendar-day window of raw files."""
    cutoff = end - timedelta(days=days - 1)
    removed = 0

    for exch in ("nse", "bse"):
        folder = RAW / exch
        if not folder.exists():
            continue

        for f in folder.iterdir():
            if f.suffix not in (".csv", ".none"):
                continue

            try:
                d = datetime.strptime(f.stem, "%Y%m%d").date()
            except ValueError:
                continue

            if d < cutoff:
                f.unlink()
                removed += 1

    print(f"Pruned {removed} old raw files before {cutoff}.")


GRACE_DAYS = 7   # an uncertain failure is retried for this many days, then treated as a holiday


def run_pass(s, exchanges, start, end, saved, skipped, failed, sample):
    d = start
    while d <= end:
        # weekends: only the recent ones are checked (special sessions happen, e.g. Budget
        # day), older weekends are skipped to save ~240 requests per exchange on a cold cache
        if d.weekday() < 5 or d >= end - timedelta(days=14):
            for e in exchanges:
                f, none = RAW / e / f"{d:%Y%m%d}.csv", RAW / e / f"{d:%Y%m%d}.none"
                if f.exists() or none.exists():
                    continue
                data, url, certain = fetch_day(s, e, d)
                if data:
                    f.write_bytes(data)
                    saved[e] += 1
                    sample.setdefault(e, (f, url))
                    print(f"saved  {e.upper()} {d}")
                elif d >= end:
                    print(f"wait   {e.upper()} {d} (today's file not published yet)")
                elif certain or (end - d).days > GRACE_DAYS:
                    none.write_text("no file")      # holiday, don't retry forever
                    skipped[e] += 1
                    print(f"none   {e.upper()} {d}")
                else:                               # network/throttle error: retry next run
                    failed[e].append(d)
                    print(f"RETRY  {e.upper()} {d} (download failed, will try again next run)")
                time.sleep(random.uniform(1.0, 2.0))
        d += timedelta(days=1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=420)
    ap.add_argument("--start")
    ap.add_argument("--only", choices=["nse", "bse"])
    ap.add_argument("--wait", type=int, default=0,
                    help="minutes to keep retrying if today's file is not published yet")
    a = ap.parse_args()

    end = date.today()
    start = datetime.strptime(a.start, "%Y-%m-%d").date() if a.start else end - timedelta(days=a.days - 1)
    exchanges = [a.only] if a.only else ["nse", "bse"]
    for e in exchanges:
        (RAW / e).mkdir(parents=True, exist_ok=True)

    s = make_session()
    saved = {e: 0 for e in exchanges}
    skipped = {e: 0 for e in exchanges}
    failed = {e: [] for e in exchanges}
    sample = {}
    run_pass(s, exchanges, start, end, saved, skipped, failed, sample)

    # today's file is often published late in the evening: keep checking for a while
    waited = 0
    while (a.wait and waited < a.wait and end.weekday() < 5
           and any(not (RAW / e / f"{end:%Y%m%d}.csv").exists() for e in exchanges)):
        print(f"\nToday's file not out yet, checking again in 10 minutes ({waited}/{a.wait} min used)")
        time.sleep(600)
        waited += 10
        failed = {e: [] for e in exchanges}
        run_pass(s, exchanges, end, end, saved, skipped, failed, sample)

    prune_old_files(end, a.days)

    print("\n--- Summary ---")
    for e in exchanges:
        have = len(list((RAW / e).glob("*.csv")))
        print(f"{e.upper()}: {saved[e]} new, {skipped[e]} holidays/missing, {have} files stored")
        if failed[e]:
            print(f"  WARNING: {len(failed[e])} day(s) failed to download and will be retried next run: "
                  + ", ".join(str(x) for x in failed[e][:10]))
    for e, (f, url) in sample.items():
        print(f"\n{e.upper()} sample ({url})")
        print("\n".join(f.read_text(errors="replace").splitlines()[:3]))
    if not any(saved.values()) and not any((RAW / e).glob("*.csv") for e in exchanges):
        print("\nNothing downloaded. Copy this whole output back to me.")
        sys.exit(1)
    if any(failed.values()):
        # shows up as a yellow warning on the GitHub Actions run page
        print("::warning::Some bhavcopy downloads failed and will be retried on the next run")


if __name__ == "__main__":
    main()
