"""The records these tests reproduce were made on the volume-roll futures series. Since the weekend-roll cut-over
(Hermes spec 004) that series is store source ``databento_v0`` for the rolled roots, so their reads go there."""
from __future__ import annotations

import pytest

ROLLED = {"ES", "NQ", "GC", "CL"}


@pytest.fixture(autouse=True)
def volume_roll_series(monkeypatch):
    from store_core import BarStore

    scan = BarStore.scan

    def on_record(self, symbol, source, freq="1m"):
        if source == "databento" and freq == "1m" and symbol.upper() in ROLLED:
            source = "databento_v0"
        return scan(self, symbol, source, freq)

    monkeypatch.setattr(BarStore, "scan", on_record)
