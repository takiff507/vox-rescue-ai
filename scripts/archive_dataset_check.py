"""Read a bounded number of training batches from the canonical archive dataset."""

from __future__ import annotations

import argparse
import time
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--rapidgzip", type=Path, required=True)
    parser.add_argument("--batches", type=int, default=8)
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--workers", type=int, default=8)
    args = parser.parse_args()

    import torch
    from torch.utils.data import DataLoader

    from vox_rescue.archive_dataset import DNS5ArchiveDataset

    dataset = DNS5ArchiveDataset(
        args.manifest,
        args.rapidgzip,
        sample_rate=16_000,
        segment_seconds=2.0,
    )
    loader = DataLoader(
        dataset,
        batch_size=args.batch_size,
        num_workers=args.workers,
        pin_memory=True,
        prefetch_factor=2 if args.workers else None,
        persistent_workers=bool(args.workers),
    )
    started = time.perf_counter()
    examples = 0
    for index, (noisy, clean) in enumerate(loader, start=1):
        if noisy.shape != clean.shape or noisy.ndim != 2 or noisy.shape[1] != 32_000:
            raise RuntimeError(f"Unexpected batch shapes: noisy={noisy.shape} clean={clean.shape}")
        if not torch.isfinite(noisy).all() or not torch.isfinite(clean).all():
            raise RuntimeError("Non-finite audio encountered")
        examples += noisy.shape[0]
        if index >= args.batches:
            break
    elapsed = time.perf_counter() - started
    print(
        f"ARCHIVE_DATASET_OK batches={args.batches} examples={examples} "
        f"elapsed={elapsed:.3f}s examples_per_second={examples / elapsed:.2f}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
