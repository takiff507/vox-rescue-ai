"""Compare pretrained and fine-tuned DF3 on deterministic held-out mixtures."""

from __future__ import annotations

import argparse
import json
import random
from pathlib import Path


def read_paths(path: Path) -> list[Path]:
    return [Path(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def si_sdr(torch, estimate, target, eps: float = 1e-8):
    estimate = estimate - estimate.mean()
    target = target - target.mean()
    projection = target * (torch.dot(estimate, target) / torch.dot(target, target).clamp_min(eps))
    residual = estimate - projection
    return 10.0 * torch.log10(
        projection.square().sum().clamp_min(eps) / residual.square().sum().clamp_min(eps)
    )


def align_by_correlation(torch, estimate, target, max_lag: int = 4096):
    """Remove the fixed causal filter delay before waveform metrics."""
    length = estimate.numel() + target.numel() - 1
    fft_length = 1 << (length - 1).bit_length()
    correlation = torch.fft.irfft(
        torch.fft.rfft(estimate, fft_length)
        * torch.conj(torch.fft.rfft(target, fft_length)),
        fft_length,
    )
    candidates = torch.cat((correlation[-max_lag:], correlation[: max_lag + 1]))
    lag = int(candidates.argmax()) - max_lag
    if lag > 0:
        estimate = estimate[lag:]
        target = target[:-lag]
    elif lag < 0:
        estimate = estimate[:lag]
        target = target[-lag:]
    return estimate, target, lag


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--model-dir", type=Path, required=True)
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--base-checkpoint", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--clean-list", type=Path)
    parser.add_argument("--noise-list", type=Path)
    parser.add_argument("--samples", type=int, default=12)
    parser.add_argument("--seconds", type=float, default=3.0)
    parser.add_argument("--snr-values", default="-5,0,5,10")
    parser.add_argument("--clean-only", action="store_true")
    parser.add_argument("--seed", type=int, default=20260808)
    parser.add_argument("--reverb", action="store_true")
    parser.add_argument("--interferer", action="store_true")
    parser.add_argument("--rir-max-seconds", type=float, default=1.0)
    args = parser.parse_args()

    import soundfile as sf
    import torch
    from df.enhance import enhance, init_df
    from df.model import ModelParams

    from vox_rescue.archive_dataset import fft_convolve_same, load_aligned_rir
    from vox_rescue.audio import load_mono_segment

    try:
        import numpy as np
        from pesq import pesq
        from pystoi import stoi
        from scipy.signal import resample_poly
    except ImportError:
        np = pesq = stoi = resample_poly = None

    def perceptual_metrics(estimate, target):
        if resample_poly is None:
            return None, None
        estimate_16k = resample_poly(estimate.detach().cpu().numpy(), 1, 3)
        target_16k = resample_poly(target.detach().cpu().numpy(), 1, 3)
        usable = min(len(estimate_16k), len(target_16k))
        estimate_16k = np.clip(estimate_16k[:usable], -1.0, 1.0)
        target_16k = np.clip(target_16k[:usable], -1.0, 1.0)
        try:
            stoi_score = float(stoi(target_16k, estimate_16k, 16_000, extended=False))
        except Exception:
            stoi_score = None
        try:
            pesq_score = float(pesq(16_000, target_16k, estimate_16k, "wb"))
        except Exception:
            pesq_score = None
        return stoi_score, pesq_score

    def mean_available(values):
        available = [value for value in values if value is not None]
        return sum(available) / len(available) if available else None

    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    if args.clean_list:
        clean_paths = read_paths(args.clean_list)
        clean_source = str(args.clean_list)
    else:
        clean_lists = [read_paths(Path(item["path_list"])) for item in manifest["clean_extracted"]]
        clean_paths = [path for paths in clean_lists for path in paths]
        clean_source = "manifest.clean_extracted"
    noise_path_list = args.noise_list or Path(manifest["noise"]["path_list"])
    noise_paths = read_paths(noise_path_list)
    rir_paths = read_paths(Path(manifest["rir"]["path_list"]))
    interferer_lists = [
        read_paths(Path(item["path_list"]))
        for item in manifest.get("interferer_extracted", [])
    ]
    interferer_paths = [path for paths in interferer_lists for path in paths] or clean_paths
    snr_values = tuple(float(value) for value in args.snr_values.split(","))
    if not snr_values:
        raise RuntimeError("At least one --snr-values entry is required")
    if len(clean_paths) < args.samples or (not args.clean_only and len(noise_paths) < args.samples):
        raise RuntimeError("Not enough extracted clean/noise files for evaluation")
    if args.interferer and len(interferer_paths) < args.samples:
        raise RuntimeError("Not enough dedicated interferer files for evaluation")

    initialized = init_df(model_base_dir=str(args.model_dir), log_file=None, log_level="ERROR")
    model, df_state = initialized[0], initialized[1]
    params = ModelParams()
    length = round(params.sr * args.seconds)
    rng = random.Random(args.seed)
    clean_selection = rng.sample(clean_paths, args.samples)
    noise_selection = (
        [None] * args.samples if args.clean_only else rng.sample(noise_paths, args.samples)
    )
    rir_selection = rng.sample(rir_paths, args.samples) if args.reverb else [None] * args.samples
    interferer_selection = (
        rng.sample(interferer_paths, args.samples) if args.interferer else [None] * args.samples
    )
    mixtures = []
    for index, (clean_path, noise_path, rir_path, interferer_path) in enumerate(
        zip(clean_selection, noise_selection, rir_selection, interferer_selection)
    ):
        random.seed(1000 + index)
        clean = load_mono_segment(clean_path, params.sr, length)
        speech = clean
        target = clean
        if rir_path is not None:
            rir = load_aligned_rir(rir_path, params.sr, args.rir_max_seconds)
            speech = fft_convolve_same(clean, rir, length)
            early_rir = rir[: round(params.sr * 0.05)]
            target = fft_convolve_same(clean, early_rir, length)
            clean_rms = clean.square().mean().sqrt().clamp_min(1e-8)
            speech = speech * (clean_rms / speech.square().mean().sqrt().clamp_min(1e-8))
            target = target * (clean_rms / target.square().mean().sqrt().clamp_min(1e-8))
        if interferer_path is not None:
            random.seed(3000 + index)
            interferer = load_mono_segment(interferer_path, params.sr, length)
            sir_db = (3.0, 6.0, 9.0, 12.0)[index % 4]
            target_rms = target.square().mean().sqrt().clamp_min(1e-8)
            interferer_rms = interferer.square().mean().sqrt().clamp_min(1e-8)
            speech = speech + interferer * (
                target_rms / (10 ** (sir_db / 20.0)) / interferer_rms
            )
        snr_db = None
        noisy = speech
        if noise_path is not None:
            random.seed(2000 + index)
            noise = load_mono_segment(noise_path, params.sr, length)
            snr_db = snr_values[index % len(snr_values)]
            clean_rms = target.square().mean().sqrt().clamp_min(1e-8)
            noise_rms = noise.square().mean().sqrt().clamp_min(1e-8)
            noise = noise * (clean_rms / (10 ** (snr_db / 20.0)) / noise_rms)
            noisy = speech + noise
        peak = torch.maximum(noisy.abs().max(), target.abs().max()).clamp_min(1e-6)
        if peak > 0.98:
            noisy = noisy * (0.98 / peak)
            target = target * (0.98 / peak)
        mixtures.append((noisy, target, snr_db))

    def evaluate_current():
        scores = []
        stoi_scores = []
        pesq_scores = []
        outputs = []
        lags = []
        model.eval()
        for noisy, clean, _ in mixtures:
            reset = getattr(df_state, "reset", None)
            if reset is not None:
                reset()
            with torch.no_grad():
                output = enhance(model, df_state, noisy.unsqueeze(0), pad=False).squeeze(0).cpu()
            usable = min(output.numel(), clean.numel())
            output = output[:usable]
            aligned, target, lag = align_by_correlation(torch, output, clean[:usable])
            scores.append(float(si_sdr(torch, aligned, target)))
            stoi_score, pesq_score = perceptual_metrics(aligned, target)
            stoi_scores.append(stoi_score)
            pesq_scores.append(pesq_score)
            outputs.append(output)
            lags.append(lag)
        return scores, stoi_scores, pesq_scores, outputs, lags

    noisy_scores = [float(si_sdr(torch, noisy, clean)) for noisy, clean, _ in mixtures]
    noisy_perceptual = [perceptual_metrics(noisy, clean) for noisy, clean, _ in mixtures]
    noisy_stoi_scores = [item[0] for item in noisy_perceptual]
    noisy_pesq_scores = [item[1] for item in noisy_perceptual]
    base_step = "pretrained"
    if args.base_checkpoint:
        base_state = torch.load(
            args.base_checkpoint,
            map_location=next(model.parameters()).device,
            weights_only=False,
        )
        model.load_state_dict(base_state["model"])
        base_step = int(base_state["step"])
    base_scores, base_stoi_scores, base_pesq_scores, base_outputs, base_lags = evaluate_current()
    state = torch.load(args.checkpoint, map_location=next(model.parameters()).device, weights_only=False)
    model.load_state_dict(state["model"])
    tuned_scores, tuned_stoi_scores, tuned_pesq_scores, tuned_outputs, tuned_lags = evaluate_current()

    args.output_dir.mkdir(parents=True, exist_ok=True)
    for index in range(min(3, args.samples)):
        noisy, clean, _ = mixtures[index]
        sf.write(args.output_dir / f"{index:02d}_clean.wav", clean.numpy(), params.sr)
        sf.write(args.output_dir / f"{index:02d}_noisy.wav", noisy.numpy(), params.sr)
        sf.write(args.output_dir / f"{index:02d}_base.wav", base_outputs[index].numpy(), params.sr)
        sf.write(args.output_dir / f"{index:02d}_tuned.wav", tuned_outputs[index].numpy(), params.sr)

    base_mean = sum(base_scores) / len(base_scores)
    tuned_mean = sum(tuned_scores) / len(tuned_scores)
    noisy_mean = sum(noisy_scores) / len(noisy_scores)
    noisy_stoi_mean = mean_available(noisy_stoi_scores)
    base_stoi_mean = mean_available(base_stoi_scores)
    tuned_stoi_mean = mean_available(tuned_stoi_scores)
    noisy_pesq_mean = mean_available(noisy_pesq_scores)
    base_pesq_mean = mean_available(base_pesq_scores)
    tuned_pesq_mean = mean_available(tuned_pesq_scores)
    report = {
        "checkpoint_step": int(state["step"]),
        "base_checkpoint_step": base_step,
        "clean_source": clean_source,
        "noise_source": None if args.clean_only else str(noise_path_list),
        "clean_only": args.clean_only,
        "snr_values": snr_values,
        "reverb": args.reverb,
        "interferer": args.interferer,
        "samples": args.samples,
        "noisy_si_sdr_db": noisy_mean,
        "base_si_sdr_db": base_mean,
        "tuned_si_sdr_db": tuned_mean,
        "delta_si_sdr_db": tuned_mean - base_mean,
        "noisy_stoi": noisy_stoi_mean,
        "base_stoi": base_stoi_mean,
        "tuned_stoi": tuned_stoi_mean,
        "delta_stoi": None if base_stoi_mean is None else tuned_stoi_mean - base_stoi_mean,
        "noisy_pesq_wb": noisy_pesq_mean,
        "base_pesq_wb": base_pesq_mean,
        "tuned_pesq_wb": tuned_pesq_mean,
        "delta_pesq_wb": None if base_pesq_mean is None else tuned_pesq_mean - base_pesq_mean,
        "base_scores": base_scores,
        "tuned_scores": tuned_scores,
        "base_lags": base_lags,
        "tuned_lags": tuned_lags,
    }
    (args.output_dir / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(
        f"DF3_EVAL_OK base_step={base_step} step={state['step']} "
        f"clean_only={args.clean_only} reverb={args.reverb} "
        f"interferer={args.interferer} samples={args.samples} "
        f"noisy_si_sdr_db={noisy_mean:.3f} base_si_sdr_db={base_mean:.3f} "
        f"tuned_si_sdr_db={tuned_mean:.3f} "
        f"delta_si_sdr_db={tuned_mean - base_mean:+.3f} "
        f"delta_stoi={None if base_stoi_mean is None else tuned_stoi_mean - base_stoi_mean} "
        f"delta_pesq_wb={None if base_pesq_mean is None else tuned_pesq_mean - base_pesq_mean}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
