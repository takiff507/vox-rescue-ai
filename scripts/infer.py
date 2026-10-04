"""Offline file inference using the same causal model used for streaming later."""

from __future__ import annotations

import argparse
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--checkpoint", type=Path, default=Path("checkpoints/latest.pt"))
    parser.add_argument("--config", type=Path, default=Path("configs/default.toml"))
    args = parser.parse_args()
    try:
        import torch
    except ImportError as exc:
        raise SystemExit("Inference runtime needs PyTorch; install it only in the later RunPod environment.") from exc

    from vox_rescue.audio import enhance_waveform, load_mono, save_mono
    from vox_rescue.config import load_config
    from vox_rescue.model import build_model

    config = load_config(args.config)
    audio_cfg, model_cfg = config["audio"], config["model"]
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model = build_model(n_fft=audio_cfg["n_fft"], hidden_size=model_cfg["hidden_size"], max_gain=model_cfg["max_gain"]).to(device)
    state = torch.load(args.checkpoint, map_location=device)
    model.load_state_dict(state["model"])
    model.eval()
    waveform = load_mono(args.input, audio_cfg["sample_rate"]).to(device)
    with torch.no_grad():
        enhanced = enhance_waveform(model, waveform, n_fft=audio_cfg["n_fft"], hop_length=round(audio_cfg["sample_rate"] * audio_cfg["hop_ms"] / 1000))
    save_mono(args.output, enhanced.squeeze(0), audio_cfg["sample_rate"])
    print(f"Enhanced file written: {args.output.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

