"""Zorro asset-list Symbol rows (Hermes spec 004): byte-preserving writes, IB symbols, the open-trade hold-back."""
from __future__ import annotations

from datetime import date, datetime, timezone

import polars as pl
import pytest

from backtest_core.zorro import assets, live

HEAD = "Name,Price,Spread,RollLong,RollShort,PIP,PIPCost,MarginCost,Market,Multiplier,Commission,Symbol"
LIVE = "\r\n".join([HEAD, "CL,90,0.01,0,0,0.01,1,-100,0,1,0.5,MCL-FUT-20261019-MCL-NYMEX-USD",
                    "QQQ,500,0.01,0,0,0.01,1,-100,0,1,0.005,QQQ-STK-SMART-USD", ""])


def contract(**kw) -> dict:
    row = {"instrument_id": 447685, "root": "CL", "raw_symbol": "CLZ6", "expiration": date(2026, 11, 20),
           "micro_raw_symbol": "MCLZ6", "micro_expiration": date(2026, 11, 19), "first_notice": None,
           "cut_off": date(2026, 11, 19)}
    return {**row, **kw}


def test_ib_symbols_for_micros_and_the_full_size_nq():
    assert assets.live_symbol("CL", contract()) == "MCL-FUT-20261119-MCL-NYMEX-USD"
    nq = contract(raw_symbol="NQZ6", expiration=date(2026, 12, 18), micro_expiration=date(2026, 12, 18))
    assert assets.live_symbol("NQF", nq) == "NQ-FUT-20261218-NQ-CME-USD"
    with pytest.raises(ValueError, match="no MCL"):
        assets.live_symbol("CL", contract(micro_expiration=None))


def test_only_the_symbol_field_changes_and_crlf_is_kept(tmp_path):
    f = tmp_path / "AssetsLive.csv"
    f.write_bytes(LIVE.encode("ascii"))
    changed = assets.write_symbols(f, {"CL": "MCL-FUT-20261119-MCL-NYMEX-USD"})
    assert changed == {"CL": ("MCL-FUT-20261019-MCL-NYMEX-USD", "MCL-FUT-20261119-MCL-NYMEX-USD")}
    assert f.read_bytes() == LIVE.replace("20261019", "20261119").encode("ascii")
    assert assets.write_symbols(f, {"CL": "MCL-FUT-20261119-MCL-NYMEX-USD"}) == {}


def test_a_name_with_no_row_is_an_error(tmp_path):
    f = tmp_path / "AssetsLive.csv"
    f.write_bytes(LIVE.encode("ascii"))
    with pytest.raises(KeyError, match="GC"):
        assets.write_symbols(f, {"GC": "MGC-FUT-20261229-MGC-COMEX-USD"})


def test_an_open_sleeve_trade_holds_its_root_back(tmp_path):
    state = ("asof_ole_utc,script,asset,layer,pending,side,lots,entry_limit,fill,stop,target,opened_ole_utc\n"
             "46311.8,ZigZagCL,CL,1,0,1,1,0,92.61,88.1,97.3,46307.4\n#end,1\n")
    (tmp_path / "State_ZigZagCL.csv").write_text(state)
    (tmp_path / "State_BreakGC.csv").write_text(state.replace("ZigZagCL,CL,1,0", "BreakGC,GC,1,1"))   # pending only
    (tmp_path / "State_NoiseAreaNQ.csv").write_text(state.replace("ZigZagCL,CL,1", "NoiseAreaNQ,NQF,2"))  # pool row
    assert live.open_roots(tmp_path) == {"CL": "ZigZagCL"}


def test_write_asset_rows_skips_a_series_without_a_contract_table(tmp_path, monkeypatch):
    class NoTables:
        def __init__(self, *_a):
            pass

        def read_contracts(self, *_a):
            raise LookupError("none")

    monkeypatch.setenv("BARS_DIR", str(tmp_path))
    monkeypatch.setattr("store_core.BarStore", NoTables)
    f = tmp_path / "AssetsLive.csv"
    f.write_bytes(LIVE.encode("ascii"))
    assert live.write_asset_rows("databento", history=tmp_path, log_dir=tmp_path) == {}
    assert f.read_bytes() == LIVE.encode("ascii")


def test_write_asset_rows_points_rows_at_the_last_bar_and_honours_the_hold_back(tmp_path, monkeypatch):
    table = pl.DataFrame([contract()]).with_columns(pl.col("instrument_id").cast(pl.UInt32))

    class Store:
        def __init__(self, *_a):
            pass

        def read_contracts(self, *_a):
            return table

        def read_rolls(self, *_a):
            raise LookupError("none")

    monkeypatch.setenv("BARS_DIR", str(tmp_path))
    monkeypatch.setattr("store_core.BarStore", Store)
    monkeypatch.setattr(live, "ROOTS", ("CL",))
    monkeypatch.setattr(live.bars, "intraday", lambda *a, **k: pl.DataFrame(
        {"start": [datetime(2026, 10, 16, 16, 59)], "instrument_id": [447685]}))
    (tmp_path / "AssetsLive.csv").write_bytes(LIVE.encode("ascii"))
    (tmp_path / "AssetsIBPaper.csv").write_bytes(LIVE.replace("\r\nCL,", "\r\nMCL,").encode("ascii"))
    report = live.write_asset_rows("databento", history=tmp_path, log_dir=tmp_path)
    assert report["AssetsLive.csv"]["CL"][1] == "MCL-FUT-20261119-MCL-NYMEX-USD"
    (tmp_path / "State_ZigZagCL.csv").write_text(
        "h\n46311.8,ZigZagCL,CL,1,0,1,1,0,92.61,88.1,97.3,46307.4\n#end,1\n")
    (tmp_path / "AssetsLive.csv").write_bytes(LIVE.encode("ascii"))
    report = live.write_asset_rows("databento", history=tmp_path, log_dir=tmp_path)
    assert report["AssetsLive.csv"]["CL"] == "held back by ZigZagCL"


def test_a_roll_at_the_close_after_the_last_bar_moves_the_row_to_the_new_contract(monkeypatch):
    rolls = pl.DataFrame({"roll_at": [datetime(2026, 9, 18, 21, 0, tzinfo=timezone.utc),
                                      datetime(2026, 10, 16, 21, 0, tzinfo=timezone.utc)],
                          "old_id": [716552, 301334], "new_id": [301334, 447685]})

    class Store:
        def read_rolls(self, *_a):
            return rolls

    def last_bar(start):
        return lambda *a, **k: pl.DataFrame({"start": [start], "instrument_id": [301334]})

    monkeypatch.setattr(live.bars, "intraday", last_bar(datetime(2026, 10, 16, 16, 59)))   # Friday 16:59 New York
    assert live.traded_id(Store(), "CL", "databento") == 447685
    monkeypatch.setattr(live.bars, "intraday", last_bar(datetime(2026, 10, 14, 16, 59)))   # mid-week: rolls on Friday
    rolls = rolls.head(1)
    assert live.traded_id(Store(), "CL", "databento") == 301334


def test_the_factor_table_ends_with_factor_1_at_a_roll_after_the_last_bar(monkeypatch):
    from backtest_core.zorro import export
    b = pl.DataFrame({"start": [datetime(2026, 9, 18, 16, 59), datetime(2026, 9, 20, 18, 0), datetime(2026, 10, 16, 16, 59)],
                      "factor": [0.95, 0.99, 0.99]})
    rolls = pl.DataFrame({"roll_at": [datetime(2026, 9, 18, 21, 0, tzinfo=timezone.utc),
                                      datetime(2026, 10, 16, 21, 0, tzinfo=timezone.utc)]})

    class Store:
        def read_rolls(self, *_a):
            return rolls

    monkeypatch.setattr(export.bars, "intraday", lambda *a, **k: b)
    monkeypatch.setattr(export.bars, "_store", lambda _d: Store())
    text = export.factor_block("CL")
    assert "#define CL_NF 3" in text
    assert text.rstrip().endswith("0.95, 0.99, 1 };")
    rolls = rolls.head(1)                                           # mid-week: no roll after the last bar
    assert "#define CL_NF 2" in export.factor_block("CL")
