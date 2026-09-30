"""Deploy our lite-C scripts into Zorro and run them from Python."""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Iterable

from . import paths, report


class ZorroError(RuntimeError):
    pass


def deploy(names: Iterable[str] | None = None, src: Path | str | None = None) -> list[Path]:
    """Copy scripts (``.c``/``.h``) from the repo into Zorro's Strategy folder; all of them if ``names`` is None.

    The repo copy is the source of truth; nothing should edit Zorro's folder directly.
    """
    src = Path(src) if src else paths.SCRIPTS_DIR
    files = [src / n for n in names] if names else sorted([*src.glob("*.c"), *src.glob("*.h")])
    out = []
    for f in files:
        if not f.exists():
            raise FileNotFoundError(f)
        dst = paths.strategy_dir() / f.name
        shutil.copy2(f, dst)
        out.append(dst)
    return out


def run(script: str, *ints: int, defines: Iterable[str] = (), mode: str = "run", timeout: int | None = 3600,
        report_name: str | None = None, output: Path | str | None = None) -> report.Report | None:
    """Run ``Zorro.exe -<mode> <script> [-i n ...] [-d X ...] -quiet`` and parse ``Log/<script>.txt``.

    ``ints`` become ``Command[0..3]``. Raises if Zorro exits with an error or writes no fresh report.
    With ``output``, that file must come out fresh instead and nothing is parsed (returns None): a run with
    ``NumTotalCycles`` writes no performance report at all (Zorro's ``LogNumber = 0`` default).
    """
    target = Path(output) if output is not None else paths.log_dir() / f"{report_name or script}.txt"
    before = target.stat().st_mtime if target.exists() else 0.0
    cmd = _exec(script, ints, defines, mode, timeout)
    if not target.exists() or target.stat().st_mtime <= before:
        raise ZorroError(f"{' '.join(cmd)} wrote no fresh {target} (compile error? check the script)")
    return None if output is not None else report.read(target)


def _exec(script: str, ints, defines, mode: str, timeout: int | None) -> list[str]:
    if len(ints) > 4:
        raise ValueError("Zorro passes at most 4 integers (-i)")
    cmd = [str(paths.ZORRO_DIR / "Zorro.exe"), f"-{mode}", script]
    for n in ints:
        cmd += ["-i", str(int(n))]
    for d in defines:
        cmd += ["-d", d]
    cmd.append("-quiet")
    proc = subprocess.run(cmd, cwd=paths.ZORRO_DIR, capture_output=True, text=True, timeout=timeout)
    if proc.returncode != 0:
        raise ZorroError(f"{' '.join(cmd)} exited {proc.returncode}: {proc.stderr or proc.stdout}")
    return cmd
