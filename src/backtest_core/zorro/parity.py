"""Trade-by-trade (or bar-by-bar) comparison of a Zorro log with its Python mirror.

Parity is the gate between the Python quick test and the Zorro robustness checks: every row must match on its
keys, and every value within ``tol``. A mismatch is not rounded away; it is explained in writing or fixed.
"""
from __future__ import annotations

from dataclasses import dataclass

import polars as pl


@dataclass
class Parity:
    n_zorro: int
    n_python: int
    matched: int
    only_zorro: pl.DataFrame
    only_python: pl.DataFrame
    value_mismatches: pl.DataFrame
    max_diff: dict[str, float]

    @property
    def exact(self) -> bool:
        return (self.n_zorro == self.n_python == self.matched and self.only_zorro.is_empty()
                and self.only_python.is_empty() and self.value_mismatches.is_empty())

    def line(self) -> str:
        diffs = ", ".join(f"{k} {v:.2e}" for k, v in self.max_diff.items())
        return (f"{'EXACT' if self.exact else 'DIFFERS'}: Zorro {self.n_zorro}, Python {self.n_python}, matched "
                f"{self.matched}, only Zorro {self.only_zorro.height}, only Python {self.only_python.height}, "
                f"value mismatches {self.value_mismatches.height}; max diff {diffs}")


def compare(zorro: pl.DataFrame, python: pl.DataFrame, keys: list[str], values: list[str],
            tol: float = 1e-6, relative: bool = True) -> Parity:
    """Join on ``keys`` and compare ``values`` (relative difference unless ``relative=False``)."""
    j = zorro.join(python, on=keys, how="full", suffix="_py", coalesce=True)
    has_z = pl.all_horizontal([pl.col(v).is_not_null() for v in values])
    has_p = pl.all_horizontal([pl.col(f"{v}_py").is_not_null() for v in values])
    only_z = j.filter(has_z & ~has_p).select(keys)
    only_p = j.filter(~has_z & has_p).select(keys)
    both = j.filter(has_z & has_p)
    flags, max_d = [], {}
    for v in values:
        d = (pl.col(v) - pl.col(f"{v}_py")).abs()
        if relative:
            d = d / pl.col(f"{v}_py").abs().clip(lower_bound=1e-12)
        both = both.with_columns(d.alias(f"d_{v}"))
        max_d[v] = float(both[f"d_{v}"].max() or 0.0) if both.height else 0.0
        flags.append(pl.col(f"d_{v}") > tol)
    mism = both.filter(pl.any_horizontal(flags)) if flags else both.head(0)
    return Parity(zorro.height, python.height, both.height, only_z, only_p, mism, max_d)
