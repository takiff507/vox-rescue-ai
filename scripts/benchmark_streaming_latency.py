"""Benchmark stateful DF3 chunk sizes on the RunPod CPU."""

from __future__ import annotations

import argparse
import json
import os
import statistics
import time
from pathlib import Path


def percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, round((len(ordered) - 1) * fraction))]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-dir", type=Path, required=True)
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--iterations", type=int, default=80)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    import torch
    from df.enhance import enhance, init_df

    torch.set_num_threads(max(1, min(8, os.cpu_count() or 4)))
    model, state, _ = init_df(
        model_base_dir=str(args.model_dir), log_file=None, log_level="ERROR"
    )
    payload = torch.load(args.checkpoint, map_location="cpu", weights_only=False)
    model.load_state_dict(payload["model"])
    model.eval()
    rows = []
    for chunk_ms in (10, 20, 40, 60, 80, 120, 250):
        samples = round(48_000 * chunk_ms / 1000)
        try:
            reset = getattr(state, "reset", None)
            if reset is not None:
                reset()
            chunk = torch.randn(1, samples) * 0.02
            times = []
            output = None
            with torch.inference_mode():
                for index in range(args.iterations + 5):
                    started = time.perf_counter()
                    output = enhance(model, state, chunk, pad=False)
                    elapsed_ms = (time.perf_counter() - started) * 1000
                    if index >= 5:
                        times.append(elapsed_ms)
            assert output is not None
            p95 = percentile(times, 0.95)
            rows.append(
                {
                    "chunk_ms": chunk_ms,
                    "supported": True,
                    "samples": samples,
                    "output_samples": int(output.shape[-1]),
                    "finite": bool(torch.isfinite(output).all()),
                    "mean_process_ms": statistics.fmean(times),
                    "p50_process_ms": percentile(times, 0.50),
                    "p95_process_ms": p95,
                    "realtime_headroom_p95": chunk_ms / max(p95, 1e-9),
                }
            )
        except Exception as exc:
            rows.append(
                {
                    "chunk_ms": chunk_ms,
                    "supported": False,
                    "samples": samples,
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )
    result = {"cpu_threads": torch.get_num_threads(), "checkpoint_step": payload["step"], "rows": rows}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
