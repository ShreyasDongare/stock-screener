"""Run with:  pip install -r requirements-dev.txt && pytest -q"""
import sys
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import build_prices as bp
import fetch_bhav as fb
import run_scans as rs


# ---------- helpers ----------
COLS = ["TradDt", "ISIN", "TckrSymb", "SctySrs", "FinInstrmNm", "OpnPric", "HghPric",
        "LwPric", "ClsPric", "PrvsClsgPric", "TtlTradgVol", "TtlTrfVal"]


def write_day(folder, d, rows):
    folder.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows, columns=COLS).to_csv(folder / f"{d:%Y%m%d}.csv", index=False)


def row(d, isin, sym, close, prev, series="EQ", vol=1_000_000):
    return [d.isoformat(), isin, sym, series, sym, close, close * 1.01, close * 0.99,
            close, prev, vol, close * vol]


def trading_days(n, start=date(2026, 1, 5)):
    out, d = [], start
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d)
        d += timedelta(days=1)
    return out


@pytest.fixture
def workdir(tmp_path, monkeypatch):
    monkeypatch.setattr(bp, "RAW", tmp_path / "raw")
    monkeypatch.setattr(bp, "OUT", tmp_path)
    return tmp_path


# ---------- snap ----------
def test_snap_finds_clean_ratios():
    assert bp.snap(0.5) == pytest.approx(0.5)
    assert bp.snap(0.101) == pytest.approx(0.1)
    assert bp.snap(10.1) == 10


def test_snap_does_not_treat_a_crash_as_a_bonus():
    # -24% in one day used to snap to 3:4; it must now be left for manual review
    assert np.isnan(bp.snap(0.76))


# ---------- price building ----------
def test_split_is_adjusted_using_exchange_prev_close(workdir):
    days = trading_days(30)
    for k, d in enumerate(days):
        if k < 20:
            r = row(d, "INE000A01010", "AAA", 200.0, 200.0)
        else:  # 1:2 split on day 20: price halves, exchange prev close already adjusted
            r = row(d, "INE000A01010", "AAA", 100.0, 100.0)
        write_day(workdir / "raw" / "nse", d, [r])
        write_day(workdir / "raw" / "bse", d, [row(d, "INE999Z01010", "ZZZ", 50.0, 50.0, series="A")])
    bp.main.__globals__["argparse"].ArgumentParser.parse_args = lambda self: type("A", (), {"show": None})()
    bp.main()
    px = pd.read_csv(workdir / "prices.csv.gz")
    aaa = px[px["symbol"] == "AAA"].sort_values("date")
    assert aaa["close"].round(2).nunique() == 1          # continuous after adjustment
    assert aaa["raw_close"].iloc[0] == 200.0
    ev = pd.read_csv(workdir / "events.csv")
    assert ev.loc[ev["key"] == "NSE:AAA", "method"].tolist() == ["exchange"]


def test_bse_history_is_stitched_to_nse_when_stock_migrates(workdir):
    days = trading_days(30)
    for k, d in enumerate(days):
        if k < 15:   # first 15 days: BSE only
            write_day(workdir / "raw" / "bse", d, [row(d, "INE111B01010", "BSESYM", 100.0, 100.0, series="A")])
            write_day(workdir / "raw" / "nse", d, [row(d, "INE000A01010", "AAA", 10.0, 10.0)])
        else:        # then it lists on NSE under a different symbol
            write_day(workdir / "raw" / "nse", d, [row(d, "INE000A01010", "AAA", 10.0, 10.0),
                                                   row(d, "INE111B01010", "NSESYM", 100.0, 100.0)])
            write_day(workdir / "raw" / "bse", d, [row(d, "INE111B01010", "BSESYM", 100.0, 100.0, series="A")])
    bp.main.__globals__["argparse"].ArgumentParser.parse_args = lambda self: type("A", (), {"show": None})()
    bp.main()
    px = pd.read_csv(workdir / "prices.csv.gz")
    migrated = px[px["isin"] == "INE111B01010"]
    assert migrated["key"].nunique() == 1 and migrated["key"].iloc[0] == "NSE:NSESYM"
    assert len(migrated) == 30


# ---------- downloads ----------
class FakeResp:
    def __init__(self, code, content=b""):
        self.status_code, self.content = code, content


class FakeSession:
    def __init__(self, resp):
        self.resp = resp

    def get(self, url, timeout=0):
        if isinstance(self.resp, Exception):
            raise self.resp
        return self.resp


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    monkeypatch.setattr(fb.time, "sleep", lambda *_: None)


def test_404_is_a_certain_holiday():
    data, url, certain = fb.fetch_day(FakeSession(FakeResp(404)), "nse", date(2026, 1, 26))
    assert data is None and certain is True


def test_throttling_and_network_errors_are_not_cached_as_holidays():
    for resp in (FakeResp(403), FakeResp(429), FakeResp(503), fb.requests.ConnectionError()):
        data, url, certain = fb.fetch_day(FakeSession(resp), "nse", date(2026, 1, 26))
        assert data is None and certain is False


def test_valid_csv_is_returned():
    body = b"a,b\n" + b"1,2\n" * 300
    data, url, certain = fb.fetch_day(FakeSession(FakeResp(200, body)), "nse", date(2026, 1, 5))
    assert data == body


# ---------- scan guard ----------
def test_scan_aborts_when_latest_day_is_incomplete(tmp_path, monkeypatch):
    monkeypatch.setattr(rs, "DATA", tmp_path)
    days = [d.isoformat() for d in trading_days(10)]
    recs = []
    for k in range(100):                       # 100 stocks, but only 10 trade on the last day
        for d in days if k < 10 else days[:-1]:
            recs.append(dict(key=f"NSE:S{k}", exch="NSE", symbol=f"S{k}", isin="INE", name="x", date=d,
                             open=1, high=1, low=1, close=1, volume=1, value=1, raw_close=1))
    pd.DataFrame(recs).to_csv(tmp_path / "prices.csv.gz", index=False)
    pd.DataFrame(columns=["key", "date", "method"]).to_csv(tmp_path / "events.csv", index=False)
    with pytest.raises(SystemExit) as e:
        rs.main()
    assert "ABORT" in str(e.value)
    assert not (tmp_path / "results.json").exists()
