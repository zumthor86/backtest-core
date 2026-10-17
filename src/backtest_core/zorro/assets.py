"""The ``Symbol`` column of Zorro asset lists (``History/Assets*.csv``): the contract a live sleeve trades.

``live_symbol`` builds IB's futures symbol from a bar-store contract row (Hermes spec 004); ``write_symbols`` changes
only that field of the named rows and keeps every other byte, so a stock row or a hand-set cost is never touched.
"""
from __future__ import annotations

from pathlib import Path

# Zorro asset name -> (root in the bar store, contract the sleeves trade, IB exchange). NQF is the noise-area sleeve's
# full-size NQ; the rest are micros.
LIVE_ROWS = {
    "ES": ("ES", "MES", "CME"), "MES": ("ES", "MES", "CME"),
    "NQ": ("NQ", "MNQ", "CME"), "MNQ": ("NQ", "MNQ", "CME"),
    "GC": ("GC", "MGC", "COMEX"), "MGC": ("GC", "MGC", "COMEX"),
    "CL": ("CL", "MCL", "NYMEX"), "MCL": ("CL", "MCL", "NYMEX"),
    "NQF": ("NQ", "NQ", "CME"),
}


def live_symbol(name: str, contract: dict) -> str:
    """IB's symbol for asset ``name`` from a contract row (``store_core.CONTRACT_COLUMNS``)."""
    _root, trade, exch = LIVE_ROWS[name]
    if trade in ("MES", "MNQ", "MGC", "MCL"):
        if contract["micro_expiration"] is None:
            raise ValueError(f"{name}: {contract['raw_symbol']} has no {trade} contract")
        expiry = contract["micro_expiration"]
    else:
        expiry = contract["expiration"]
    return f"{trade}-FUT-{expiry:%Y%m%d}-{trade}-{exch}-USD"


def _rows(text: str) -> tuple[str, list[str]]:
    newline = "\r\n" if "\r\n" in text else "\n"
    return newline, text.split(newline)


def read_symbols(path: Path) -> dict[str, str]:
    _nl, lines = _rows(Path(path).read_bytes().decode("ascii"))
    head = lines[0].split(",")
    i_name, i_sym = head.index("Name"), head.index("Symbol")
    return {f[i_name]: f[i_sym] for f in (x.split(",") for x in lines[1:] if x.strip()) if len(f) > i_sym}


def write_symbols(path: Path, symbols: dict[str, str]) -> dict[str, tuple[str, str]]:
    """Set the ``Symbol`` of each named row. Returns ``{name: (old, new)}`` for the rows that changed. A name with no
    row is an error: the list must already hold the asset's costs, which are set by hand."""
    path = Path(path)
    nl, lines = _rows(path.read_bytes().decode("ascii"))
    head = lines[0].split(",")
    i_name, i_sym = head.index("Name"), head.index("Symbol")
    seen, changed = set(), {}
    for k, line in enumerate(lines[1:], start=1):
        f = line.split(",")
        if len(f) <= i_sym or f[i_name] not in symbols:
            continue
        seen.add(f[i_name])
        if f[i_sym] != symbols[f[i_name]]:
            changed[f[i_name]] = (f[i_sym], symbols[f[i_name]])
            f[i_sym] = symbols[f[i_name]]
            lines[k] = ",".join(f)
    missing = set(symbols) - seen
    if missing:
        raise KeyError(f"{path.name} has no row for {sorted(missing)}")
    if changed:
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_bytes(nl.join(lines).encode("ascii"))
        tmp.replace(path)
    return changed
