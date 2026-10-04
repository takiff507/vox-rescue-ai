"""Run before any paid training job; never installs or downloads anything."""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--min-free-gb", type=float, default=10.0)
    args = parser.parse_args()
    root = args.root.resolve()
    free_gb = shutil.disk_usage(root).free / (1024**3)
    print(f"Python: {sys.version.split()[0]}")
    print(f"Free storage: {free_gb:.2f} GB")
    if free_gb < args.min_free_gb:
        raise SystemExit(f"STOP: free storage is below {args.min_free_gb:.2f} GB")

    try:
        import torch
    except ImportError:
        raise SystemExit("STOP: PyTorch is not installed; install the approved RunPod requirements first.")
    print(f"PyTorch: {torch.__version__}")
    print(f"CUDA available: {torch.cuda.is_available()}")
    if not torch.cuda.is_available():
        raise SystemExit("STOP: CUDA GPU is not visible; do not start training on CPU.")
    print(f"GPU: {torch.cuda.get_device_name(0)}")

    config = root / "configs" / "default.toml"
    if not config.exists():
        raise SystemExit(f"STOP: config missing: {config}")
    pairs = root / "manifests" / "pairs.csv"
    if not pairs.exists():
        print(f"WAIT: pair manifest is not mounted yet: {pairs}")
    else:
        print(f"Pair manifest found: {pairs}")
    print("Preflight passed. No training started and no network access performed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

