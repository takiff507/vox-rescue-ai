"""Measure the one-time protected checkpoint loading overhead."""

from __future__ import annotations

import gc
import io
import statistics
import sys
import time
from pathlib import Path

import torch


ROOT = Path(__file__).resolve().parents[1]
NATIVE_DIR = ROOT / "desktop" / "native_model_guard" / "x64" / "Release"
if str(NATIVE_DIR) not in sys.path:
    sys.path.insert(0, str(NATIVE_DIR))

import model_guard


def load_plain(path: Path):
    return torch.load(path, map_location="cpu", weights_only=False)


def load_protected(path: Path):
    payload = model_guard.decrypt(str(path))
    stream = io.BytesIO(payload)
    payload[:] = b"\0" * len(payload)
    try:
        return torch.load(stream, map_location="cpu", weights_only=False)
    finally:
        view = stream.getbuffer()
        view[:] = b"\0" * len(view)
        view.release()
        stream.close()


def measure(loader, path: Path, count: int = 3):
    measurements = []
    for _ in range(count):
        started = time.perf_counter()
        state = loader(path)
        measurements.append(time.perf_counter() - started)
        del state
        gc.collect()
    return measurements


def main() -> int:
    plain = measure(load_plain, ROOT / "models" / "current" / "vox_rescue_engine.pt")
    protected = measure(
        load_protected, ROOT / "models" / "protected" / "vox_rescue_engine.vrm"
    )
    plain_median = statistics.median(plain)
    protected_median = statistics.median(protected)
    print(f"PLAIN_LOAD_MEDIAN_MS={plain_median * 1000.0:.3f}")
    print(f"PROTECTED_LOAD_MEDIAN_MS={protected_median * 1000.0:.3f}")
    print(f"ONE_TIME_OVERHEAD_MS={(protected_median - plain_median) * 1000.0:.3f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
