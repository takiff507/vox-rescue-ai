"""Audio I/O and causal STFT helpers; soundfile and torch are runtime deps."""

from __future__ import annotations

import math
import random
from pathlib import Path


def _runtime_imports():
    try:
        import soundfile as sf
        import torch
        import torch.nn.functional as functional
    except ImportError as exc:  # pragma: no cover - depends on RunPod runtime
        raise RuntimeError(
            "Audio training/inference needs soundfile and PyTorch; install "
            "requirements-runpod.txt inside the RunPod environment."
        ) from exc
    return sf, torch, functional


def load_mono(path: Path, sample_rate: int):
    sf, torch, functional = _runtime_imports()
    samples, source_rate = sf.read(str(path), dtype="float32", always_2d=True)
    waveform = torch.from_numpy(samples.T).mean(dim=0)
    if source_rate == sample_rate:
        return waveform
    new_length = round(waveform.numel() * sample_rate / source_rate)
    resized = functional.interpolate(
        waveform[None, None, :], size=new_length, mode="linear", align_corners=False
    )
    return resized[0, 0]


def load_mono_segment(path: Path, sample_rate: int, segment_length: int):
    """Read only the source frames needed for one random training segment."""

    sf, torch, functional = _runtime_imports()
    with sf.SoundFile(str(path), mode="r") as audio:
        source_rate = int(audio.samplerate)
        source_frames = max(1, math.ceil(segment_length * source_rate / sample_rate))
        available = int(audio.frames)
        if available > source_frames:
            audio.seek(random.randint(0, available - source_frames))
        samples = audio.read(frames=source_frames, dtype="float32", always_2d=True)

    waveform = torch.from_numpy(samples.T).mean(dim=0)
    if source_rate != sample_rate and waveform.numel() > 0:
        output_length = max(1, round(waveform.numel() * sample_rate / source_rate))
        waveform = functional.interpolate(
            waveform[None, None, :],
            size=output_length,
            mode="linear",
            align_corners=False,
        )[0, 0]
    if waveform.numel() < segment_length:
        waveform = functional.pad(waveform, (0, segment_length - waveform.numel()))
    return waveform[:segment_length]


def save_mono(path: Path, waveform, sample_rate: int) -> None:
    sf, _, _ = _runtime_imports()
    path.parent.mkdir(parents=True, exist_ok=True)
    waveform = waveform.detach().float().cpu().clamp(-1.0, 1.0).numpy()
    sf.write(str(path), waveform, sample_rate, subtype="PCM_16")


def enhance_waveform(model, waveform, *, n_fft: int, hop_length: int):
    _, torch, _ = _runtime_imports()
    if waveform.dim() == 1:
        waveform = waveform.unsqueeze(0)
    original_length = waveform.shape[-1]
    if original_length < n_fft:
        waveform = torch.nn.functional.pad(waveform, (0, n_fft - original_length))
    window = torch.hann_window(n_fft, device=waveform.device)
    spectrum = torch.stft(
        waveform,
        n_fft=n_fft,
        hop_length=hop_length,
        win_length=n_fft,
        window=window,
        center=False,
        return_complex=True,
    )
    magnitude = spectrum.abs().clamp_min(1e-5)
    log_magnitude = torch.log1p(magnitude).transpose(1, 2)
    gain, _ = model(log_magnitude)
    enhanced = spectrum * gain.transpose(1, 2)
    result = torch.istft(
        enhanced,
        n_fft=n_fft,
        hop_length=hop_length,
        win_length=n_fft,
        window=window,
        center=False,
        length=waveform.shape[-1],
    )
    return result[..., :original_length]
