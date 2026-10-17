"""zorro.paper's replay rows and zorro.live.write_factors's destination, on made-up data. Zorro does not run."""
from datetime import datetime

import numpy as np
import polars as pl
import pytest

from backtest_core.zorro import live, paper


def _trd(rows):
    return pl.DataFrame(rows, schema=["Name", "ID", "Type", "Asset", "Lots", "Open", "Close", "Entry", "Exit", "ExitType"],
                        orient="row")


def test_adjusted_prices_go_back_to_the_traded_scale_across_a_roll():
    bars_utc = pl.DataFrame({"close_utc": [datetime(2026, 9, 20, 14, 0), datetime(2026, 9, 25, 14, 0)],
                             "factor": [0.98, 1.0]})                      # a roll between the two bars
    trd = _trd([("BreakGC", 1, "Long", "GC", 1, "2026-09-22 14:30", "2026-09-26 15:00", 1960.0, 2010.0, "Stop")])
    (row,) = paper.trade_rows("BreakGC", trd, datetime(2026, 10, 1), "adjusted", bars_utc).iter_rows(named=True)
    assert row["entry_raw"] == pytest.approx(2000.0)                     # 1960 / 0.98: the old contract's price
    assert row["exit_raw"] == pytest.approx(2010.0)                      # after the roll, adjusted = raw
    assert (row["side"], row["open_at_end"]) == (1, False)


def test_a_trade_closed_by_the_end_of_the_history_is_still_open():
    trd = _trd([("NoiseAreaNQ", 1, "Short", "NQF", 1, "2026-10-14 19:00", "2026-10-14 19:59", 600.0, 601.0, "Exit")])
    (row,) = paper.trade_rows("NoiseAreaNQ", trd, datetime(2026, 10, 14, 20, 0), "raw", None).iter_rows(named=True)
    assert row["side"] == -1 and row["open_at_end"] is True
    assert row["exit_utc"] is None and row["exit_raw"] is None
    assert row["entry_raw"] == 600.0                                     # a raw history is not converted


def test_the_replay_refuses_the_live_zorro_folder(monkeypatch):
    monkeypatch.setattr(paper.paths, "ZORRO_DIR", paper.LIVE_ZORRO)
    with pytest.raises(SystemExit, match="live Zorro folder"):
        paper.setup()


def test_write_factors_writes_where_it_is_told(tmp_path, monkeypatch):
    monkeypatch.setattr(live.export, "factor_block", lambda r: f"// {r}\n")
    live.write_factors(tmp_path)
    assert (tmp_path / "ZZFactors.h").read_text(encoding="ascii").count("//") >= len(live.ROOTS)


def test_times_parse_whether_the_reader_parsed_them_or_not(tmp_path):
    f = tmp_path / "x_trd.csv"
    f.write_text("Name,ID,Type,Asset,Lots,Open,Close,Entry,Exit,ExitType\n"
                 "DipBuyNQ,1,Long,NQ,1,2026-02-25 23:00,2026-03-02 23:00,100,101,Sold\n", encoding="utf-8")
    from backtest_core.zorro import report
    parsed = report.trades_csv(f)                                      # try_parse_dates: already datetimes
    text = pl.read_csv(f)                                              # plain text
    for trd in (parsed, text):
        (row,) = paper.trade_rows("DipBuyNQ", trd, datetime(2026, 10, 1), "raw", None).iter_rows(named=True)
        assert row["entry_utc"] == datetime(2026, 2, 25, 23, 0)


def test_setup_copies_the_program_and_asset_lists_but_no_accounts(tmp_path, monkeypatch):
    live_dir, copy = tmp_path / "Zorro", tmp_path / "ZorroReplay"
    for d in ("History", "Log", "Data", "include"):
        (live_dir / d).mkdir(parents=True)
    (live_dir / "Zorro.exe").write_bytes(b"exe")
    (live_dir / "include" / "default.c").write_text("x")
    (live_dir / "Log" / "demotrades.csv").write_text("trades")
    (live_dir / "History" / "AssetsLive.csv").write_text("assets")
    (live_dir / "History" / "Accounts.csv").write_text("secret login")
    monkeypatch.setattr(paper, "LIVE_ZORRO", live_dir)
    monkeypatch.setattr(paper.paths, "ZORRO_DIR", copy)
    paper.setup()
    assert (copy / "Zorro.exe").exists() and (copy / "include" / "default.c").exists()
    assert (copy / "History" / "AssetsLive.csv").exists()
    assert not (copy / "History" / "Accounts.csv").exists()
    assert not (copy / "Log" / "demotrades.csv").exists()


def test_replay_one_reads_the_fresh_trade_list(tmp_path, monkeypatch):
    monkeypatch.setattr(paper.paths, "ZORRO_DIR", tmp_path)
    (tmp_path / "Log").mkdir()
    calls = []

    def fake_run(script, *ints, defines=(), **kw):
        calls.append((script, ints, tuple(defines), kw.get("low_priority")))
        (tmp_path / "Log" / f"{script}_trd.csv").write_text(
            "Name,ID,Type,Asset,Lots,Open,Close,Entry,Exit,ExitType\n"
            "NoiseAreaNQ,1,Long,NQF,1,2026-10-14 14:01,2026-10-14 19:59,600,601,Exit\n", encoding="utf-8")

    monkeypatch.setattr(paper.run, "run", fake_run)
    monkeypatch.setattr(paper, "_close_utc", lambda sym, src: pl.DataFrame(
        {"close_utc": [datetime(2026, 10, 15, 20, 0)], "factor": [1.0]}))
    rows = paper.replay_one("NoiseAreaNQ", datetime(2026, 10, 16).date())
    assert calls == [("NoiseAreaNQ", (0, 20261016), ("LIVETEST",), True)]
    assert rows.height == 1 and rows["open_at_end"].to_list() == [False]


def test_replay_writes_a_status_and_reports_a_failed_sleeve(tmp_path, monkeypatch):
    monkeypatch.setattr(paper.paths, "ZORRO_DIR", tmp_path / "copy")
    monkeypatch.setattr(paper, "refresh_history", lambda: None)

    def fake_one(script, end):
        if script == "BreakES":
            raise RuntimeError("compile error")
        return paper.trade_rows(script, _trd([(script, 1, "Long", "NQF", 1, "2026-10-14 14:01", "2026-10-14 15:00",
                                               1.0, 2.0, "Exit")]), datetime(2026, 10, 15), "raw", None)

    monkeypatch.setattr(paper, "replay_one", fake_one)
    code = paper.replay(tmp_path / "out", ["NoiseAreaNQ", "BreakES"], datetime(2026, 10, 16).date())
    import json
    status = json.loads((tmp_path / "out" / "replay_status.json").read_text(encoding="utf-8"))
    assert code == 1 and status["sleeves"]["NoiseAreaNQ"]["trades"] == 1
    assert "compile error" in status["sleeves"]["BreakES"]["error"]
    assert (tmp_path / "out" / "replay_NoiseAreaNQ.csv").exists()


def _qqq_bars(sessions, minutes=390, factor=1.0):
    from datetime import timedelta
    rows = []
    for s in sessions:
        for m in range(minutes):
            t = datetime(s.year, s.month, s.day, 9, 30) + timedelta(minutes=m)
            rows.append((t, s, 100.0, 101.0, 99.0, 100.0 + m * 0.01, 10.0, factor))
    return pl.DataFrame(rows, schema=["start", "session", "open", "high", "low", "close", "volume", "factor"], orient="row")


def test_noise_area_export_writes_history_factors_and_assets(tmp_path):
    from datetime import date
    from backtest_core.zorro import export
    sessions = [date(2026, 10, 13), date(2026, 10, 14)]
    b = pl.concat([_qqq_bars(sessions[:1], factor=0.99), _qqq_bars(sessions[1:])])
    assert export.noise_area_sessions(b) == sessions
    g = export.noise_area_frame(b, sessions)
    assert g.height == 2 * export.NA_BARS
    n = export.write_noise_area(g, tmp_path, tmp_path / "NAFactors.h")
    assert n == g.height and (tmp_path / "QQQ_2026.t6").stat().st_size == export.T6.itemsize * g.height
    assert "#define QQQ_NF 2" in (tmp_path / "NAFactors.h").read_text(encoding="ascii")
    assert (tmp_path / "AssetsNoiseArea.csv").read_text(encoding="ascii").startswith("Name,Price")


def test_a_short_session_is_not_a_noise_area_session():
    from datetime import date
    from backtest_core.zorro import export
    assert export.noise_area_sessions(pl.concat([_qqq_bars([date(2026, 10, 13)], minutes=200),
                                                 _qqq_bars([date(2026, 10, 14)])])) == [date(2026, 10, 14)]


def test_main_needs_the_bar_store_for_a_replay(monkeypatch):
    monkeypatch.delenv("BARS_DIR", raising=False)
    with pytest.raises(SystemExit, match="BARS_DIR"):
        paper.main(["replay", "--out", "x"])


def test_noise_area_nq_export_writes_raw_prices_snapped_to_the_tick(tmp_path, monkeypatch):
    from backtest_core.zorro import export
    adj = pl.DataFrame({"start": [datetime(2026, 9, 15, 9, 30), datetime(2026, 9, 16, 9, 30)],
                        "session": [datetime(2026, 9, 15).date(), datetime(2026, 9, 16).date()],
                        "open": [25000.25 * 1.01, 25100.0], "high": [25010.5 * 1.01, 25110.0],
                        "low": [24990.0 * 1.01, 25090.0], "close": [25005.75 * 1.01, 25105.25],
                        "volume": [12.0, 34.0], "factor": [1.01, 1.0]})
    monkeypatch.setattr(export.bars, "intraday", lambda *a, **k: adj)
    assert export.write_noise_area_nq(tmp_path) == {2026: 2}
    rec = np.fromfile(tmp_path / "NQF_2026.t6", dtype=export.T6)[::-1]       # newest first on disk
    assert rec["c"].tolist() == [25005.75, 25105.25] and rec["v"].tolist() == pytest.approx([1.01, 1.0])
    assert rec["vol"].tolist() == [12.0, 34.0]
    assert (tmp_path / "AssetsNoiseAreaNQ.csv").read_text(encoding="ascii").splitlines()[1].startswith("NQF,")
