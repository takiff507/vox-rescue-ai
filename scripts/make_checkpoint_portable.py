"""Rewrite checkpoint metadata without OS-specific pathlib objects."""

from __future__ import annotations

import argparse
import os
from pathlib import Path, PurePath

import torch


def portable(value):
    if isinstance(value, PurePath):
        return str(value)
    if isinstance(value, dict):
        return {portable(key): portable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [portable(item) for item in value]
    if isinstance(value, tuple):
        return tuple(portable(item) for item in value)
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()

    payload = torch.load(args.source, map_location="cpu", weights_only=False)
    converted = portable(payload)
    # The conversion must never alter model tensors.
    for name, tensor in payload["model"].items():
        if not torch.equal(tensor, converted["model"][name]):
            raise RuntimeError(f"Model tensor changed during conversion: {name}")

    args.destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.destination.with_suffix(args.destination.suffix + ".tmp")
    torch.save(converted, temporary)
    os.replace(temporary, args.destination)
    print(
        f"PORTABLE_CHECKPOINT_OK step={converted['step']} "
        f"destination={args.destination}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
