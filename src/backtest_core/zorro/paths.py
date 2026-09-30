"""Where Zorro and our scripts live. Both overridable by env var for the server."""
from __future__ import annotations

import os
from pathlib import Path

ZORRO_DIR = Path(os.environ.get("ZORRO_DIR", "C:/Users/Christopher/Zorro"))
# Source of truth for our lite-C scripts (tracked in the workspace root repo); deploy copies them into Zorro.
SCRIPTS_DIR = Path(os.environ.get("ZORRO_SCRIPTS_DIR", "C:/Users/Christopher/Documents/python/zorro/Strategy"))


def history_dir() -> Path:
    return ZORRO_DIR / "History"


def strategy_dir() -> Path:
    return ZORRO_DIR / "Strategy"


def log_dir() -> Path:
    return ZORRO_DIR / "Log"
