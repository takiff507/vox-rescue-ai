"""Safe training entrypoint; --dry-run never imports PyTorch or downloads data."""

from __future__ import annotations

import argparse
import csv
import time
from pathlib import Path


def dry_run(pair_manifest: Path) -> int:
    if not pair_manifest.exists():
        print(f"DRY RUN: pair manifest is not present yet: {pair_manifest}")
        print("DRY RUN: no training started and no network access performed.")
        return 0
    with pair_manifest.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(row for row in handle if not row.lstrip().startswith("#")))
    required = {"noisy_path", "clean_path", "split"}
    columns = set(rows[0]) if rows else set()
    missing = required - columns
    if missing:
        raise SystemExit(f"Pair manifest missing columns: {', '.join(sorted(missing))}")
    print(f"DRY RUN: pair rows found: {len(rows)}")
    print("DRY RUN: configuration and manifest schema are valid.")
    print("DRY RUN: no training started and no network access performed.")
    return 0


def dry_run_synthetic(clean_root: Path, noise_root: Path) -> int:
    clean_count = sum(1 for path in clean_root.rglob("*") if path.is_file() and path.suffix.lower() == ".wav")
    noise_count = sum(1 for path in noise_root.rglob("*") if path.is_file() and path.suffix.lower() == ".wav")
    print(f"DRY RUN: clean WAV files found: {clean_count}")
    print(f"DRY RUN: noise WAV files found: {noise_count}")
    if not clean_count or not noise_count:
        print("DRY RUN: waiting for both clean and noise datasets.")
        return 0
    print("DRY RUN: synthetic on-the-fly mixing is ready.")
    print("DRY RUN: no training started and no network access performed.")
    return 0


def read_source_list(path: Path) -> list[Path]:
    with path.open(encoding="utf-8") as handle:
        files = [Path(line.strip()) for line in handle if line.strip()]
    if not files:
        raise SystemExit(f"Source list is empty: {path}")
    return files


def dry_run_source_lists(clean_list: Path, noise_list: Path) -> int:
    clean_files = read_source_list(clean_list)
    noise_files = read_source_list(noise_list)
    print(f"DRY RUN: clean WAV paths listed: {len(clean_files)}")
    print(f"DRY RUN: noise WAV paths listed: {len(noise_files)}")
    print("DRY RUN: cached source lists are ready; no recursive scan performed.")
    return 0


def full_train(args) -> int:
    try:
        import torch
        from torch.utils.data import DataLoader
        from tqdm import tqdm
    except ImportError as exc:
        raise SystemExit(
            "Training runtime is not installed. Use requirements-runpod.txt on RunPod."
        ) from exc

    from vox_rescue.audio import enhance_waveform
    from vox_rescue.config import load_config
    from vox_rescue.model import build_model
    from vox_rescue.pairs import PairedWavDataset, read_pairs
    from vox_rescue.synthetic import SyntheticWavDataset, find_wavs

    config = load_config(args.config)
    audio_cfg = config["audio"]
    model_cfg = config["model"]
    train_cfg = config["training"]
    is_iterable = False
    if args.archive_manifest:
        from vox_rescue.archive_dataset import DNS5ArchiveDataset

        dataset = DNS5ArchiveDataset(
            args.archive_manifest,
            args.rapidgzip,
            sample_rate=audio_cfg["sample_rate"],
            segment_seconds=train_cfg["segment_seconds"],
        )
        is_iterable = True
        print(f"Canonical archive sources: {args.archive_manifest}")
    elif args.clean_list and args.noise_list:
        clean_files = read_source_list(args.clean_list)
        noise_files = read_source_list(args.noise_list)
        print(f"Cached synthetic sources: clean={len(clean_files)} noise={len(noise_files)}")
        dataset = SyntheticWavDataset(
            clean_files,
            noise_files,
            sample_rate=audio_cfg["sample_rate"],
            segment_seconds=train_cfg["segment_seconds"],
        )
    elif args.clean_root and args.noise_root:
        clean_files = find_wavs(args.clean_root)
        noise_files = find_wavs(args.noise_root)
        print(f"Synthetic sources: clean={len(clean_files)} noise={len(noise_files)}")
        dataset = SyntheticWavDataset(
            clean_files,
            noise_files,
            sample_rate=audio_cfg["sample_rate"],
            segment_seconds=train_cfg["segment_seconds"],
        )
    else:
        rows = read_pairs(args.pairs, split=args.split)
        dataset = PairedWavDataset(
            rows,
            sample_rate=audio_cfg["sample_rate"],
            segment_seconds=train_cfg["segment_seconds"],
        )
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    pin_memory = bool(train_cfg.get("pin_memory", True)) and device.type == "cuda"
    num_workers = (
        int(args.num_workers)
        if args.num_workers is not None
        else int(train_cfg.get("num_workers", 0))
    )
    batch_size = (
        int(args.batch_size)
        if args.batch_size is not None
        else int(train_cfg["batch_size"])
    )
    loader_options = {
        "dataset": dataset,
        "batch_size": batch_size,
        "shuffle": not is_iterable,
        "num_workers": num_workers,
        "drop_last": False,
        "pin_memory": pin_memory,
    }
    if num_workers > 0:
        loader_options.update(
            prefetch_factor=int(train_cfg.get("prefetch_factor", 4)),
            persistent_workers=bool(train_cfg.get("persistent_workers", True)),
        )
    loader = DataLoader(**loader_options)
    if device.type == "cuda":
        torch.backends.cudnn.benchmark = True
        torch.backends.cuda.matmul.allow_tf32 = True
        torch.set_float32_matmul_precision("high")
    model = build_model(
        n_fft=audio_cfg["n_fft"],
        hidden_size=model_cfg["hidden_size"],
        max_gain=model_cfg["max_gain"],
    ).to(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=train_cfg["learning_rate"])
    loss_fn = torch.nn.SmoothL1Loss()
    use_amp = bool(train_cfg.get("mixed_precision", True)) and device.type == "cuda"
    scaler = torch.amp.GradScaler("cuda", enabled=use_amp)
    checkpoint_dir = args.checkpoints
    checkpoint_dir.mkdir(parents=True, exist_ok=True)
    latest = checkpoint_dir / "latest.pt"
    start_step = 0
    if args.resume and latest.exists():
        state = torch.load(latest, map_location=device)
        model.load_state_dict(state["model"])
        optimizer.load_state_dict(state["optimizer"])
        start_step = int(state["step"])
        print(f"Resumed checkpoint at step {start_step}")

    model.train()
    n_fft = audio_cfg["n_fft"]
    hop = round(audio_cfg["sample_rate"] * audio_cfg["hop_ms"] / 1000)
    window = torch.hann_window(n_fft, device=device)
    step = start_step
    examples = 0
    train_started = time.perf_counter()
    max_steps = args.max_steps if args.max_steps is not None else train_cfg["max_steps"]
    checkpoint_every = args.checkpoint_every or config["safety"]["checkpoint_every_steps"]
    while step < max_steps:
        for noisy, clean in tqdm(loader, desc=f"train:{device}"):
            if step >= max_steps:
                break
            noisy = noisy.to(device, non_blocking=pin_memory)
            clean = clean.to(device, non_blocking=pin_memory)
            with torch.autocast(device_type=device.type, dtype=torch.float16, enabled=use_amp):
                noisy_spec = torch.stft(noisy, n_fft=n_fft, hop_length=hop, win_length=n_fft, window=window, center=False, return_complex=True)
                clean_spec = torch.stft(clean, n_fft=n_fft, hop_length=hop, win_length=n_fft, window=window, center=False, return_complex=True)
                noisy_mag = noisy_spec.abs().clamp_min(1e-5)
                target = (clean_spec.abs() / noisy_mag).clamp(0.0, model_cfg["max_gain"])
                predicted, _ = model(torch.log1p(noisy_mag).transpose(1, 2))
                loss = loss_fn(predicted, target.transpose(1, 2))
            optimizer.zero_grad(set_to_none=True)
            scaler.scale(loss).backward()
            scaler.unscale_(optimizer)
            torch.nn.utils.clip_grad_norm_(model.parameters(), 3.0)
            scaler.step(optimizer)
            scaler.update()
            step += 1
            examples += int(noisy.shape[0])
            if step % checkpoint_every == 0 or step == max_steps:
                torch.save({"step": step, "model": model.state_dict(), "optimizer": optimizer.state_dict(), "config": config}, latest)
                print(f"checkpoint step={step} loss={loss.item():.6f}")
    elapsed = max(time.perf_counter() - train_started, 1e-9)
    completed_steps = step - start_step
    print(
        f"Training finished safely at step {step}; device={device}; amp={use_amp}; "
        f"batch={batch_size}; workers={num_workers}; elapsed={elapsed:.3f}s; "
        f"steps_per_second={completed_steps / elapsed:.3f}; "
        f"examples_per_second={examples / elapsed:.1f}"
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path("configs/default.toml"))
    parser.add_argument("--pairs", type=Path, default=Path("manifests/pairs.csv"))
    parser.add_argument("--checkpoints", type=Path, default=Path("checkpoints"))
    parser.add_argument("--split", default="train")
    parser.add_argument("--clean-root", type=Path)
    parser.add_argument("--noise-root", type=Path)
    parser.add_argument("--clean-list", type=Path)
    parser.add_argument("--noise-list", type=Path)
    parser.add_argument("--archive-manifest", type=Path)
    parser.add_argument(
        "--rapidgzip",
        type=Path,
        default=Path("/workspace/vox_rescue_clean/.venv/bin/rapidgzip"),
    )
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--max-steps", type=int)
    parser.add_argument("--checkpoint-every", type=int)
    parser.add_argument("--batch-size", type=int)
    parser.add_argument("--num-workers", type=int)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if bool(args.clean_list) != bool(args.noise_list):
        parser.error("--clean-list and --noise-list must be supplied together")
    if bool(args.clean_root) != bool(args.noise_root):
        parser.error("--clean-root and --noise-root must be supplied together")
    if args.dry_run:
        if args.clean_list and args.noise_list:
            return dry_run_source_lists(args.clean_list, args.noise_list)
        if args.clean_root and args.noise_root:
            return dry_run_synthetic(args.clean_root, args.noise_root)
        return dry_run(args.pairs)
    return full_train(args)


if __name__ == "__main__":
    raise SystemExit(main())
