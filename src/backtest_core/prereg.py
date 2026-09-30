"""Pre-registration: hash the rules before a run, and spend a holdout exactly once.

A ledger is a text file of ``<sha256> *<file name>`` lines (the format ``sha256sum`` writes), kept next to the
study: ``spec.sha256`` for pre-registrations, ``verdict.sha256`` for verdicts. A holdout is spent by creating
``holdout_<name>.spent`` beside the ledger; a second attempt raises, so "run the holdout once" is enforced by
the code rather than by memory.
"""
from __future__ import annotations

import hashlib
from datetime import datetime
from pathlib import Path


class HoldoutSpentError(RuntimeError):
    pass


class HashMismatchError(RuntimeError):
    pass


def sha256(path: Path | str) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _entries(ledger: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if ledger.exists():
        for line in ledger.read_text(encoding="utf-8").splitlines():
            if line.strip():
                digest, name = line.split(maxsplit=1)
                out[Path(name.lstrip("*")).name] = digest
    return out


def register(path: Path | str, ledger: Path | str | None = None) -> str:
    """Append ``path``'s hash to the ledger (default: ``spec.sha256`` beside it). Returns the hash.

    Registering the same content again is a no-op; registering a changed file under a name already in the
    ledger raises, because an edited pre-registration is a new one and needs a new name.
    """
    path = Path(path)
    ledger = Path(ledger) if ledger else path.parent / "spec.sha256"
    digest = sha256(path)
    known = _entries(ledger).get(path.name)
    if known == digest:
        return digest
    if known is not None:
        raise HashMismatchError(f"{path.name} is already registered with a different hash ({known[:8]}...)")
    with ledger.open("a", encoding="utf-8", newline="\n") as f:
        f.write(f"{digest} *{path.name}\n")
    return digest


def verify(path: Path | str, ledger: Path | str | None = None) -> str:
    """Raise unless ``path`` still has the hash it was registered with."""
    path = Path(path)
    ledger = Path(ledger) if ledger else path.parent / "spec.sha256"
    known = _entries(ledger).get(path.name)
    digest = sha256(path)
    if known is None:
        raise HashMismatchError(f"{path.name} is not in {ledger}")
    if known != digest:
        raise HashMismatchError(f"{path.name} changed since it was registered")
    return digest


def spend_holdout(study_dir: Path | str, name: str, spec: Path | str | None = None) -> Path:
    """Mark holdout ``name`` as spent, or raise if it already was.

    If ``spec`` is given it must still match its registered hash, so a holdout cannot run under rules edited
    after the in-sample result.
    """
    study_dir = Path(study_dir)
    if spec is not None:
        verify(spec)
    marker = study_dir / f"holdout_{name}.spent"
    if marker.exists():
        raise HoldoutSpentError(f"holdout '{name}' was already run ({marker.read_text(encoding='utf-8').strip()})")
    marker.write_text(f"spent {datetime.now().isoformat(timespec='seconds')}\n", encoding="utf-8")
    return marker
