"""Run a tiny local pipeline check without datasets, GPU, or network."""

from __future__ import annotations

import argparse
import math
import tempfile
import wave
from pathlib import Path

from .manifest import inspect_wav


def _write_tone(path: Path, sample_rate: int = 16_000, duration: float = 0.1) -> None:
    frames = int(sample_rate * duration)
    with wave.open(str(path), "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(sample_rate)
        samples = bytearray()
        for index in range(frames):
            value = int(0.1 * 32767 * math.sin(2 * math.pi * 440 * index / sample_rate))
            samples.extend(value.to_bytes(2, byteorder="little", signed=True))
        audio.writeframes(bytes(samples))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="vox_rescue_smoke_") as temp_dir:
        root = Path(temp_dir)
        sample = root / "sample.wav"
        _write_tone(sample)
        row = inspect_wav(sample, root)
        assert row["status"] == "ok", row
        assert row["sample_rate"] == "16000", row
        assert row["channels"] == "1", row
        assert float(row["duration_seconds"]) > 0, row
    print("Smoke test passed: WAV inspection works without datasets, GPU, or network.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

