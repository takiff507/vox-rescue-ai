"""Merge compatible fine-tuning task vectors around one protected base checkpoint."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

import torch


def parse_branch(value: str) -> tuple[Path, float]:
    try:
        path, scale = value.rsplit(":", 1)
        return Path(path), float(scale)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("branch must be CHECKPOINT:SCALE") from exc


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", type=Path, required=True)
    parser.add_argument("--branch", type=parse_branch, action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--step", type=int, required=True)
    args = parser.parse_args()

    base_payload = torch.load(args.base, map_location="cpu", weights_only=False)
    base_model = base_payload["model"]
    branches = []
    for path, scale in args.branch:
        payload = torch.load(path, map_location="cpu", weights_only=False)
        model = payload["model"]
        if model.keys() != base_model.keys():
            raise RuntimeError(f"Model keys differ: {path}")
        branches.append((path, scale, model))

    merged = {}
    with torch.no_grad():
        for key, base_value in base_model.items():
            if not (base_value.is_floating_point() or base_value.is_complex()):
                merged[key] = base_value.clone()
                continue
            value = base_value.to(torch.float64)
            for path, scale, model in branches:
                branch_value = model[key]
                if branch_value.shape != base_value.shape:
                    raise RuntimeError(f"Shape differs for {key}: {path}")
                value.add_(branch_value.to(torch.float64) - base_value.to(torch.float64), alpha=scale)
            merged[key] = value.to(base_value.dtype)

    output_payload = {
        "step": args.step,
        "model": merged,
        "optimizer": base_payload.get("optimizer"),
        "model_dir": base_payload.get("model_dir"),
        "parent_checkpoint": str(args.base),
        "merge_provenance": [
            {"checkpoint": str(path), "scale": scale} for path, scale, _ in branches
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_suffix(args.output.suffix + ".tmp")
    torch.save(output_payload, temporary)
    os.replace(temporary, args.output)
    print(f"TASK_VECTOR_MERGE_OK output={args.output} branches={len(branches)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
