"""Storage-safe project self-check."""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path


REQUIRED_DIRS = ("data", "manifests", "checkpoints", "outputs", "logs", "configs")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--minimum-free-gb", type=float, default=5.0)
    args = parser.parse_args()
    root = args.root.resolve()

    missing = [name for name in REQUIRED_DIRS if not (root / name).is_dir()]
    if missing:
        print(f"Missing directories: {', '.join(missing)}")
        return 1

    free_gb = shutil.disk_usage(root).free / (1024**3)
    print(f"Python: {sys.version.split()[0]}")
    print(f"Workspace: {root}")
    print(f"Free space visible to Python: {free_gb:.2f} GB")
    if free_gb < args.minimum_free_gb:
        print(f"WARNING: below configured safety floor of {args.minimum_free_gb:.2f} GB")
    print("Network/download check: this self-check performs no network access.")
    print("Project self-check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

