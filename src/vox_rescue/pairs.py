"""Validation and loading for clean/noisy paired training examples."""

from __future__ import annotations

import csv
import random
from pathlib import Path

from .audio import load_mono


REQUIRED_COLUMNS = {"noisy_path", "clean_path", "split"}


def read_pairs(path: Path, split: str = "train") -> list[dict[str, str]]:
    if not path.exists():
        raise FileNotFoundError(f"Pair manifest not found: {path}")
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(row for row in handle if not row.lstrip().startswith("#"))
        columns = set(reader.fieldnames or [])
        missing = REQUIRED_COLUMNS - columns
        if missing:
            raise ValueError(f"Pair manifest missing columns: {', '.join(sorted(missing))}")
        rows = [row for row in reader if row.get("split", "train") == split]
    if not rows:
        raise ValueError(f"Pair manifest has no rows for split={split!r}")
    return rows


class PairedWavDataset:
    """Dependency-light dataset wrapper; torch Dataset is imported lazily."""

    def __init__(self, rows, sample_rate: int, segment_seconds: float):
        self.rows = rows
        self.sample_rate = sample_rate
        self.segment_length = max(1, round(sample_rate * segment_seconds))

    def __len__(self):
        return len(self.rows)

    def __getitem__(self, index):
        import torch

        row = self.rows[index]
        noisy = load_mono(Path(row["noisy_path"]), self.sample_rate)
        clean = load_mono(Path(row["clean_path"]), self.sample_rate)
        length = min(noisy.numel(), clean.numel())
        noisy, clean = noisy[:length], clean[:length]
        if length >= self.segment_length:
            start = random.randint(0, length - self.segment_length)
            noisy = noisy[start : start + self.segment_length]
            clean = clean[start : start + self.segment_length]
        else:
            pad = self.segment_length - length
            noisy = torch.nn.functional.pad(noisy, (0, pad))
            clean = torch.nn.functional.pad(clean, (0, pad))
        return noisy, clean

