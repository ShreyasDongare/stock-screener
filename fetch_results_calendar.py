#!/usr/bin/env python3
"""Fetch NSE corporate board meetings and financial-result announcements.

Writes data/results_calendar.json for the dashboard. Dates are India-local.
This uses NSE's public corporate-filings JSON endpoints and intentionally keeps
scheduled meetings separate from already-filed result announcements.
"""
import json
import re
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import requests

OUT = Path("data/results_calendar.json")
BASE = "https://www.nseindia.com"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/130.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": BASE + "/companies-listing/corporate-filings-board-meetings",
}
DATE_KEYS = ("meeting_date", "bm_date", "meetingDate", "date", "broadcast_date", "an_dt", "sort_date")
SYMBOL_KEYS = ("symbol", "sm_symbol", "ticker", "company_symbol")
NAME_KEYS = ("company_name", "company", "sm_name", "issuer_name")
PURPOSE_KEYS = ("purpose", "bm_purpose", "subject", "desc", "details")
URL_KEYS = ("attchmntFile", "attachment", "attachment_url", "url", "link", "bm_attachment")

def first(row, keys):
    for key in keys:
        val = row.get(key)
        if val not in (None, ""):
            return val
    return ""

def parse_date(value):
    if not value:
        return ""
    s = str(value).strip()
    for fmt in ("%d-%b-%Y", "%d-%m-%Y", "%d/%m/%Y", "%Y-%m-%d", "%d-%b-%y", "%d/%m/%y"):
        try:
            return datetime.strptime(s[:11], fmt).date().isoformat()
        except ValueError:
            pass
    m = re.search(r"(\d{4}-\d{2}-\d{2})", s)
    return m.group(1) if m else ""

def get_rows(session, endpoint, start, end):
    params = {"index": "equities", "from_date": start.strftime("%d-%m-%Y"), "to_date": end.strftime("%d-%m-%Y")}
    url = BASE + "/api/" + endpoint
    try:
        response = session.get(url, params=params, timeout=35)
        if response.status_code != 200:
            print(f"{endpoint}: HTTP {response.status_code}", file=sys.stderr)
            return []
        payload = response.json()
    except (requests.RequestException, ValueError) as exc:
        print(f"{endpoint}: {exc}", file=sys.stderr)
        return []
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for key in ("data", "records", "results", "rows"):
            if isinstance(payload.get(key), list):
                return payload[key]
    print(f"{endpoint}: unexpected JSON structure", file=sys.stderr)
    return []

def main():
    today = date.today()
    start, end = today - timedelta(days=14), today + timedelta(days=14)
    session = requests.Session()
    session.headers.update(HEADERS)
    try:
        session.get(BASE, timeout=15)
    except requests.RequestException:
        pass

    meetings = get_rows(session, "corporate-board-meetings", start, end)
    announcements = get_rows(session, "corporate-announcements", start, end)
    out = {}
    for row in meetings:
        purpose = str(first(row, PURPOSE_KEYS)).strip()
        if "result" not in purpose.lower() and "financial" not in purpose.lower():
            continue
        symbol = str(first(row, SYMBOL_KEYS)).strip().upper()
        meeting_date = parse_date(first(row, ("meeting_date", "bm_date", "meetingDate", "date")))
        if not symbol or not meeting_date:
            continue
        url = str(first(row, URL_KEYS)).strip()
        if url and url.startswith("/"):
            url = BASE + url
        key = ("scheduled", symbol, meeting_date, purpose)
        out[key] = {
            "symbol": symbol,
            "company_name": str(first(row, NAME_KEYS)).strip(),
            "date": meeting_date,
            "purpose": purpose or "Financial Results",
            "status": "Scheduled",
            "official_url": url or "https://www.nseindia.com/companies-listing/corporate-filings-board-meetings",
            "source": "NSE Board Meetings",
        }

    for row in announcements:
        purpose = str(first(row, PURPOSE_KEYS)).strip()
        if "result" not in purpose.lower() and "financial" not in purpose.lower():
            continue
        symbol = str(first(row, SYMBOL_KEYS)).strip().upper()
        announced = parse_date(first(row, ("broadcast_date", "an_dt", "date", "sort_date", "meeting_date")))
        if not symbol or not announced:
            continue
        url = str(first(row, URL_KEYS)).strip()
        if url and url.startswith("/"):
            url = BASE + url
        key = ("declared", symbol, announced, purpose)
        out[key] = {
            "symbol": symbol,
            "company_name": str(first(row, NAME_KEYS)).strip(),
            "date": announced,
            "purpose": purpose or "Financial Results",
            "status": "Declared",
            "official_url": url or "https://www.nseindia.com/companies-listing/corporate-filings-financial-results",
            "source": "NSE Financial Results / Announcements",
        }

    data = {
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "holidays": [],
        "results": sorted(out.values(), key=lambda r: (r["date"], r["symbol"], r["status"])),
        "sources": [
            "https://www.nseindia.com/companies-listing/corporate-filings-board-meetings",
            "https://www.nseindia.com/companies-listing/corporate-filings-financial-results",
        ],
        "warning": "Exchange data may change; confirm the original filing before trading.",
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {len(data['results'])} result calendar rows to {OUT}")
    if not meetings and not announcements:
        print("Warning: NSE endpoints returned no data; file contains an empty list.", file=sys.stderr)

if __name__ == "__main__":
    main()
