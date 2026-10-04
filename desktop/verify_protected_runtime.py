"""Smoke-check the protected engine with real DF3 initialization and inference."""

from __future__ import annotations

import sys
import time
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
NATIVE_DIR = ROOT / "desktop" / "native_model_guard" / "x64" / "Release"
for directory in (ROOT / "desktop", NATIVE_DIR):
    if str(directory) not in sys.path:
        sys.path.insert(0, str(directory))

from df3_runtime import DF3ChunkProcessor


def main() -> int:
    processor = DF3ChunkProcessor(
        ROOT / "models" / "DeepFilterNet3",
        ROOT / "models" / "protected" / "vox_rescue_engine.vrm",
        sample_rate=48_000,
        chunk_ms=20,
    )
    processor.start()
    deadline = time.monotonic() + 30.0
    while not processor.ready and not processor.error and time.monotonic() < deadline:
        time.sleep(0.05)
    if processor.error:
        raise RuntimeError(processor.error)
    if not processor.ready:
        raise TimeoutError("Protected engine did not become ready")

    phase = np.linspace(0.0, 2.0 * np.pi * 220.0 / 50.0, processor.chunk_size,
                        endpoint=False, dtype=np.float32)
    chunk = (0.1 * np.sin(phase)).astype(np.float32)
    outputs = []
    for _ in range(processor.context_chunks + 4):
        while not processor.submit(chunk):
            if processor.error:
                raise RuntimeError(processor.error)
            time.sleep(0.01)
        limit = time.monotonic() + 5.0
        while time.monotonic() < limit:
            output = processor.pop_output()
            if output is not None:
                outputs.append(output)
                break
            time.sleep(0.01)
    processor.stop()
    if not outputs:
        raise RuntimeError("Protected engine produced no smoke-test output")
    if not all(np.isfinite(output).all() for output in outputs):
        raise RuntimeError("Protected engine produced non-finite output")
    print(f"READY=1")
    print(f"LOAD_SECONDS={processor.load_seconds:.4f}")
    print(f"OUTPUT_CHUNKS={len(outputs)}")
    print(f"LAST_PROCESS_MS={processor.last_process_ms:.3f}")
    print(f"MAX_PROCESS_MS={processor.max_process_ms:.3f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
