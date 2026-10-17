"""One-off: the live futures sleeves on the volume-roll history against the weekend-roll history (Hermes spec 004, US4).

    ZORRO_DIR=C:/Users/Christopher/ZorroCompare python -m backtest_core.zorro.roll_compare

Each sleeve's Zorro script runs over the full history (its own costs, rules fixed, as in register rows 95 and 173)
once on bar-store source ``databento_v0`` (the vendor's volume roll, kept until spec task T032) and once on
``databento`` (the weekend roll),
each with its own roll table in ``ZZFactors.h``. It runs in a separate Zorro copy, never the live one or the paper
check's, and decides nothing: it shows whether moving the roll dates moves the results. Holdout windows play no part:
the scripts' test mode is the in-sample history the battery used.
"""
from __future__ import annotations

import shutil
import sys

from . import export, live, paths, paper, run

SLEEVES = ("ZigZagGC", "ZigZagCL", "BreakGC", "BreakES", "DipBuyNQ")
SOURCES = ("databento_v0", "databento")
FLAG = 0.10                                    # a change in Sharpe ratio worth the user's look


def prepare(source: str) -> None:
    for r in live.ROOTS:
        n = export.t6(r, source)
        print(f"{r} [{source}]: {sum(n.values()):,} bars", flush=True)
    text = live.HEADER + "\n" + "\n".join(export.factor_block(r, source) for r in live.ROOTS)
    (paths.strategy_dir() / "ZZFactors.h").write_text(text, encoding="ascii", newline="\r\n")


def main() -> int:
    if paths.ZORRO_DIR.resolve() in (paper.LIVE_ZORRO.resolve(),):
        print("refused: ZORRO_DIR is the live Zorro folder", file=sys.stderr)
        return 2
    paper.setup()
    run.deploy()
    rows = {}
    for source in SOURCES:
        prepare(source)
        for script in SLEEVES:
            rep = run.run(script, timeout=7200, low_priority=True)
            shutil.copy2(paths.log_dir() / f"{script}.txt", paths.log_dir() / f"{script}_{source}.txt")
            rows[(script, source)] = rep
            print(f"{script} [{source}]: Sharpe {rep.sharpe} PF {rep.profit_factor} trades {rep.trades}", flush=True)
    print("\n| Sleeve | Sharpe volume roll | Sharpe weekend roll | Change | PF | Trades | Flag |")
    print("|---|---|---|---|---|---|---|")
    for script in SLEEVES:
        a, b = rows[(script, SOURCES[0])], rows[(script, SOURCES[1])]
        d = (b.sharpe or 0) - (a.sharpe or 0)
        print(f"| {script} | {a.sharpe} | {b.sharpe} | {d:+.2f} | {a.profit_factor} -> {b.profit_factor} | "
              f"{a.trades} -> {b.trades} | {'CHECK' if abs(d) > FLAG else ''} |")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
