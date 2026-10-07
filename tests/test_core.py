"""Run with:  pip install -r requirements-dev.txt && pytest -q"""
import json
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


# ---------- the 3 scans (synthetic charts) ----------
def chart(closes, vols, rng_pct, opens=None):
    """Build a price frame like prices.csv.gz gives to analyse()."""
    n = len(closes)
    c = np.array(closes, float)
    o = np.array(opens, float) if opens is not None else np.r_[c[0], c[:-1]]
    rp = np.array(rng_pct, float) / 100
    return pd.DataFrame(dict(
        key="NSE:T", exch="NSE", symbol="T", name="T", date=[f"d{k:03d}" for k in range(n)],
        open=o, high=np.maximum(o, c) * (1 + rp / 2), low=np.minimum(o, c) * (1 - rp / 2),
        close=c, volume=np.array(vols, float), value=c * np.array(vols, float)))


def run(closes, vols=None, rng=None, opens=None, history=True, ramp=(50, 100)):
    """Run the scans. By default a 200-bar steady uptrend is put in front of the pattern, so the
    stock has the 253+ bars and the rising 150/200-day averages that a Stage 2 stock needs."""
    vols = list(vols) if vols is not None else [1e6] * len(closes)
    rng = list(rng) if rng is not None else [4.0] * len(closes)
    closes = list(closes)
    if history:
        pre = list(np.linspace(*ramp, 200))
        if opens is not None:
            opens = list(np.r_[pre[0], pre[:-1]]) + list(opens)
        closes, vols, rng = pre + closes, [1e6] * 200 + vols, [3.0] * 200 + rng
    return rs.analyse("NSE:T", chart(closes, vols, rng, opens), set(), set())[1]


def leader_flag():
    """60 quiet bars, a 60% run-up in 20 bars, then a 12-bar flag."""
    closes = [100.0] * 60 + list(np.linspace(100, 160, 20)) + [158, 156, 154, 152, 151, 152, 153, 154, 155, 156, 157, 157.5]
    return closes, [1e6] * 60 + [1.5e6] * 20 + [0.5e6] * 12, [3.0] * 60 + [7.0] * 20 + [3.5] * 12


def test_breakout_setup_near_flag_high():
    closes, vols, rng = leader_flag()
    b = run(closes, vols, rng)["breakout"]
    assert b["state"] == "Setup"
    assert b["entry"] > b["close"] > b["stop"]
    assert b["prior_move"] >= 50 and b["risk_adr"] <= 2.0


def test_breakout_triggers_on_volume_and_not_without_it():
    closes, vols, rng = leader_flag()
    o = list(np.r_[closes[0], closes[:-1]]) + [158.0]
    assert run(closes + [168.0], vols + [3e6], rng + [6.5], o)["breakout"]["state"] == "Triggered"
    assert "breakout" not in run(closes + [168.0], vols + [0.6e6], rng + [6.5], o)   # weak volume


def test_prior_move_is_required_for_every_scan(monkeypatch):
    # same kind of flag but the stock only rallied about 10% in the last months
    closes = [100.0] * 60 + list(np.linspace(100, 110, 20)) + [109, 108, 107, 106, 106, 107, 107, 108, 108, 109, 109, 109.5]
    monkeypatch.setitem(rs.CFG["stage2"], "required", False)          # isolate the prior-move gate
    assert run(closes, rng=[4.0] * 92, history=False) == {}
    monkeypatch.setitem(rs.CFG["prior_move"], "enabled", False)       # proves the gate is what blocked it
    assert "breakout" in run(closes, rng=[4.0] * 92, history=False)


def test_stage2_is_required_for_every_scan(monkeypatch):
    closes, vols, rng = leader_flag()
    assert "breakout" in run(closes, vols, rng)                        # Stage 2 shape: found
    assert run(closes, vols, rng, history=False) == {}                 # under 253 bars: no Stage 2
    assert run(closes, vols, rng, ramp=(150, 100)) == {}               # long downtrend before: not Stage 2
    monkeypatch.setitem(rs.CFG["stage2"], "required", False)           # proves the gate is what blocked it
    assert "breakout" in run(closes, vols, rng, history=False)


def test_adr_below_3_is_rejected():
    closes, vols, rng = leader_flag()
    assert run(closes, vols, [1.5] * len(closes)) == {}


def pullback_chart(last):
    """100 -> 160 rally (60%), a steady grind higher, then a last close of `last`."""
    return [100.0] * 60 + list(np.linspace(100, 160, 25)) + [161, 162, 163, 164, 165, 165, 166, 166, 167, 167, 168, 168, 169, 169, 170] + [last]


def test_pullback_needs_close_within_2pct_of_a_moving_average():
    c = pullback_chart(0)
    ema11 = pd.Series(c[:-1]).ewm(span=11, adjust=False).mean().iloc[-1]
    near = run(pullback_chart(ema11 * 1.01))
    assert near["pullback"]["level"] in ("EMA11", "EMA21", "SMA50")
    assert abs(near["pullback"]["dist"]) <= 2.0
    assert "pullback" not in run(pullback_chart(ema11 * 1.12))      # far above every average


def test_pullback_rejects_stock_without_prior_move():
    closes = [100.0] * 60 + list(np.linspace(100, 112, 40))        # steady, only +12%
    assert "pullback" not in run(closes, ramp=(100, 100.01))


def htf_chart(last):
    """flat, a 100% flagpole in 30 bars, then a 19-bar flag that dips and recovers, then `last`."""
    pole = list(np.linspace(100, 200, 30))
    flag = [198, 195, 192, 190, 189, 188, 188, 189, 190, 191, 192, 193, 194, 195, 195, 196, 196, 197, 197]
    return [100.0] * 60 + pole + flag + [last]


def test_htf_only_when_close_is_within_2pct_of_ema11_ema21_or_sma50():
    c = htf_chart(0)
    ema11 = pd.Series(c[:-1]).ewm(span=11, adjust=False).mean().iloc[-1]
    good = run(htf_chart(ema11 * 1.005))
    assert good["htf"]["state"] == "Forming" and abs(good["htf"]["dist"]) <= 2.0
    assert good["htf"]["level"] in ("EMA11", "EMA21", "SMA50")
    assert "htf" not in run(htf_chart(ema11 * 1.04))               # 4% above: not tight


def test_scan_output_has_only_the_three_scans():
    closes, vols, rng = leader_flag()
    assert set(run(closes, vols, rng)) <= {"breakout", "pullback", "htf"}


def test_main_applies_rs_rank_and_returns_only_the_three_scans(tmp_path, monkeypatch):
    monkeypatch.setattr(rs, "DATA", tmp_path)
    rng = np.random.default_rng(3)
    closes, vols, rp = leader_flag()
    lead = chart(list(np.linspace(50, 100, 200)) + closes, [1e6] * 200 + vols, [3.0] * 200 + rp)
    n = len(lead)
    frames = [lead]
    for k in range(60):                                  # 60 random-walk stocks that go nowhere
        c = 100 * np.cumprod(1 + rng.normal(0, 0.02, n))
        f = chart(c, [1e6] * n, [3.5] * n)
        f["key"], f["symbol"] = f"NSE:R{k}", f"R{k}"
        frames.append(f)
    df = pd.concat(frames)
    df["isin"] = "INE"
    df["raw_close"] = df["close"]
    start = date(2025, 1, 1)
    df["date"] = df["date"].map(lambda d: (start + timedelta(days=int(d[1:]))).isoformat())
    df.to_csv(tmp_path / "prices.csv.gz", index=False)
    pd.DataFrame(columns=["key", "date", "method"]).to_csv(tmp_path / "events.csv", index=False)
    rs.main()
    out = json.load(open(tmp_path / "results.json"))
    assert set(out["scans"]) == {"breakout", "pullback", "htf"}
    rows = [r for v in out["scans"].values() for r in v]
    assert rows and all(r["rs"] >= 70 and r["prior_move"] >= 50 and r["adr"] >= 3 for r in rows)
    assert any(r["symbol"] == "T" for r in out["scans"]["breakout"])


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
