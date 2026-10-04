"""On-the-fly noisy/clean training pairs from public source audio."""

from __future__ import annotations

import random
from pathlib import Path

from .audio import load_mono_segment


class SyntheticWavDataset:
    """Mix clean speech and noise at random SNR without saving mixtures."""

    def __init__(
        self,
        clean_files: list[Path],
        noise_files: list[Path],
        sample_rate: int,
        segment_seconds: float,
        snr_min_db: float = -5.0,
        snr_max_db: float = 20.0,
    ):
        if not clean_files:
            raise ValueError("No clean WAV files found")
        if not noise_files:
            raise ValueError("No noise WAV files found")
        self.clean_files = clean_files
        self.noise_files = noise_files
        self.sample_rate = sample_rate
        self.segment_length = max(1, round(sample_rate * segment_seconds))
        self.snr_min_db = snr_min_db
        self.snr_max_db = snr_max_db

    def __len__(self):
        # A virtual epoch is large enough to expose many random mixtures while
        # keeping the DataLoader finite and checkpoint steps predictable.
        return max(1024, len(self.clean_files) * 4)

    @staticmethod
    def _rms(waveform, eps=1e-8):
        import torch

        return torch.sqrt(torch.mean(waveform.square()).clamp_min(eps))

    def __getitem__(self, index):
        import math
        import torch

        clean = load_mono_segment(
            random.choice(self.clean_files), self.sample_rate, self.segment_length
        )
        noise = load_mono_segment(
            random.choice(self.noise_files), self.sample_rate, self.segment_length
        )
        snr_db = random.uniform(self.snr_min_db, self.snr_max_db)
        clean_rms = self._rms(clean)
        noise_rms = self._rms(noise)
        desired_noise_rms = clean_rms / (10 ** (snr_db / 20.0))
        noise = noise * (desired_noise_rms / noise_rms)
        mixture = clean + noise
        peak = torch.maximum(mixture.abs().max(), clean.abs().max()).clamp_min(1e-6)
        if peak > 0.98:
            scale = 0.98 / peak
            mixture = mixture * scale
            clean = clean * scale
        return mixture, clean

    def _crop_or_pad(self, waveform):
        import random
        import torch

        if waveform.numel() >= self.segment_length:
            start = random.randint(0, waveform.numel() - self.segment_length)
            return waveform[start : start + self.segment_length]
        return torch.nn.functional.pad(waveform, (0, self.segment_length - waveform.numel()))


def find_wavs(root: Path) -> list[Path]:
    return sorted(path for path in root.rglob("*") if path.is_file() and path.suffix.lower() == ".wav")
