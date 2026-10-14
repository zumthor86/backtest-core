"""Fidelity of a build: does our return series track the published series of the same rule?

A rule rebuilt on our data (a narrower universe, other costs, other dates) can drift from what its source measured.
`compare` puts our daily series on months and reads it against a published monthly series: correlation, beta,
tracking error and both means over the common months. `verdict` reads the correlation against a floor set from data
(builds with a known public series); a build below the floor is "uninformative": its test says little about the
source's claim, whatever its Sharpe.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class Fidelity:
    months: int
    first: np.datetime64
    last: np.datetime64
    corr: float
    beta: float
    tracking_error: float      # annualised, of ours minus theirs
    mean_ours: float           # monthly
    mean_published: float      # monthly

    def line(self, label: str) -> str:
        return (f"{label}: {self.months} months {self.first} .. {self.last}, correlation {self.corr:+.2f}, beta "
                f"{self.beta:+.2f}, tracking error {self.tracking_error:.1%} a year, mean {self.mean_ours:+.2%} a month "
                f"against {self.mean_published:+.2%}")


def to_monthly(days: np.ndarray, daily: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Compound daily returns within each calendar month."""
    months = days.astype("datetime64[M]")
    keys, inv = np.unique(months, return_inverse=True)
    growth = np.ones(len(keys))
    np.multiply.at(growth, inv, 1 + daily)
    return keys, growth - 1


def compare(days: np.ndarray, daily: np.ndarray, pub_months: np.ndarray, pub_monthly: np.ndarray,
            first: np.datetime64 | None = None, last: np.datetime64 | None = None) -> Fidelity:
    om, orr = to_monthly(days, daily)
    common, i, j = np.intersect1d(om, pub_months.astype("datetime64[M]"), return_indices=True)
    keep = np.ones(len(common), dtype=bool)
    if first is not None:
        keep &= common >= np.datetime64(first, "M")
    if last is not None:
        keep &= common <= np.datetime64(last, "M")
    a, b, m = orr[i][keep], pub_monthly[j][keep], common[keep]
    if len(m) < 24:
        raise ValueError(f"only {len(m)} common months: too few to judge a build")
    beta = float(np.cov(a, b)[0, 1] / b.var(ddof=1))
    return Fidelity(len(m), m[0], m[-1], float(np.corrcoef(a, b)[0, 1]), beta, float((a - b).std(ddof=1) * np.sqrt(12)),
                    float(a.mean()), float(b.mean()))


def verdict(f: Fidelity, floor: float) -> str:
    return "fit" if f.corr >= floor else "uninformative"
