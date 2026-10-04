"""Load the vendored DeepFilterNet3 checkpoint and benchmark a short CUDA forward path."""

from __future__ import annotations

import argparse
import time
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-dir", type=Path, required=True)
    parser.add_argument("--seconds", type=float, default=2.0)
    parser.add_argument("--iterations", type=int, default=5)
    args = parser.parse_args()

    import torch
    from df.enhance import enhance, init_df
    from df.model import ModelParams

    initialized = init_df(model_base_dir=str(args.model_dir), log_file=None, log_level="ERROR")
    if len(initialized) == 4:
        model, df_state, _, epoch = initialized
    else:
        model, df_state, _ = initialized
        epoch = "loaded"
    params = ModelParams()
    device = next(model.parameters()).device
    audio = torch.randn(1, round(params.sr * args.seconds), device="cpu") * 0.02
    with torch.no_grad():
        output = enhance(model, df_state, audio, pad=False)
        if device.type == "cuda":
            torch.cuda.synchronize()
        started = time.perf_counter()
        for _ in range(args.iterations):
            output = enhance(model, df_state, audio, pad=False)
        if device.type == "cuda":
            torch.cuda.synchronize()
    elapsed = time.perf_counter() - started
    audio_seconds = args.seconds * args.iterations
    print(
        f"DEEPFILTERNET3_OK epoch={epoch} device={device} sr={params.sr} "
        f"fft={params.fft_size} hop={params.hop_size} "
        f"parameters={sum(parameter.numel() for parameter in model.parameters())} "
        f"output_shape={tuple(output.shape)} elapsed={elapsed:.4f}s "
        f"rtf={elapsed / audio_seconds:.5f}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
