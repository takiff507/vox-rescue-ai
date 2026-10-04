"""Compact causal spectral-mask model for the first training stage."""

from __future__ import annotations


def build_model(*, n_fft: int, hidden_size: int, max_gain: float):
    try:
        import torch.nn as nn
    except ImportError as exc:  # pragma: no cover - depends on RunPod runtime
        raise RuntimeError("PyTorch is required for model training/inference") from exc

    class CausalMaskNet(nn.Module):
        """Frame-causal GRU mask estimator.

        The GRU is unidirectional, so each output frame only uses current and
        previous frames. That keeps the model compatible with later streaming
        inference instead of silently introducing future-frame lookahead.
        """

        def __init__(self) -> None:
            super().__init__()
            self.n_fft = n_fft
            self.max_gain = max_gain
            bins = n_fft // 2 + 1
            self.gru = nn.GRU(bins, hidden_size, batch_first=True)
            self.mask_head = nn.Sequential(
                nn.Linear(hidden_size, bins),
                nn.Sigmoid(),
            )
            self.clarity_head = nn.Sequential(
                nn.Linear(hidden_size, bins),
                nn.Sigmoid(),
            )

        def forward(self, log_magnitude, hidden=None):
            states, hidden = self.gru(log_magnitude, hidden)
            suppression = self.mask_head(states)
            # A bounded clarity gain gives the model a vocal-presence head while
            # preventing uncontrolled high-frequency amplification.
            clarity = 0.85 + (self.max_gain - 0.85) * self.clarity_head(states)
            return (suppression * clarity).clamp(0.0, self.max_gain), hidden

    return CausalMaskNet()

