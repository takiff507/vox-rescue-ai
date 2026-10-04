"""Fetch several real batches from the clarity manifest and report throughput."""

from __future__ import annotations

import argparse
import time
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--rapidgzip", type=Path, required=True)
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--num-workers", type=int, default=10)
    parser.add_argument("--batches", type=int, default=4)
    args = parser.parse_args()

    import torch
    from torch.utils.data import DataLoader

    from vox_rescue.archive_dataset import DNS5ArchiveDataset

    dataset = DNS5ArchiveDataset(
        args.manifest,
        args.rapidgzip,
        sample_rate=48_000,
        segment_seconds=2.0,
        snr_min_db=5.0,
        snr_max_db=30.0,
        clean_probability=0.20,
        clean_type_weights={"archive": 0.35, "parquet": 0.45, "extracted": 0.20},
    )
    loader = DataLoader(
        dataset,
        batch_size=args.batch_size,
        num_workers=args.num_workers,
        pin_memory=True,
        persistent_workers=args.num_workers > 0,
        prefetch_factor=2 if args.num_workers > 0 else None,
        drop_last=True,
    )
    started = time.perf_counter()
    examples = 0
    iterator = iter(loader)
    for index in range(args.batches):
        noisy, clean = next(iterator)
        if noisy.shape != clean.shape or noisy.shape[-1] != 96_000:
            raise RuntimeError(f"Unexpected batch shapes: {noisy.shape} {clean.shape}")
        if not torch.isfinite(noisy).all() or not torch.isfinite(clean).all():
            raise RuntimeError("Non-finite audio in real dataset batch")
        examples += int(noisy.shape[0])
        print(
            f"CLARITY_BATCH_OK batch={index + 1} shape={tuple(noisy.shape)} "
            f"noisy_peak={float(noisy.abs().max()):.4f} clean_peak={float(clean.abs().max()):.4f}",
            flush=True,
        )
    elapsed = max(time.perf_counter() - started, 1e-9)
    print(
        f"CLARITY_LOADER_OK batches={args.batches} examples={examples} "
        f"elapsed={elapsed:.3f}s examples_per_second={examples / elapsed:.2f}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
