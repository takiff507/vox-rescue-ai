"""Small TOML configuration loader based on Python's standard library."""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any


def load_config(path: Path) -> dict[str, Any]:
    with path.open("rb") as handle:
        return tomllib.load(handle)

