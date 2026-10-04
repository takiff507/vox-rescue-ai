"""Fine-tune DeepFilterNet3 directly from the canonical DNS5 archive stream."""

from __future__ import annotations

import argparse
import os
import random
import time
from pathlib import Path


def atomic_checkpoint(torch, payload: dict, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    torch.save(payload, temporary)
    os.replace(temporary, destination)


def reset_df_state(df_state) -> None:
    reset = getattr(df_state, "reset", None)
    if reset is not None:
        reset()


def portable_cli_args(args) -> dict:
    """Keep checkpoints loadable on Windows as well as Linux."""
    return {
        key: str(value) if isinstance(value, Path) else value
        for key, value in vars(args).items()
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--rapidgzip", type=Path, required=True)
    parser.add_argument("--model-dir", type=Path, required=True)
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--max-steps", type=int, default=20)
    parser.add_argument("--checkpoint-every", type=int, default=10)
    parser.add_argument("--batch-size", type=int, default=4)
    parser.add_argument("--num-workers", type=int, default=8)
    parser.add_argument("--segment-seconds", type=float, default=2.0)
    parser.add_argument("--learning-rate", type=float, default=1e-5)
    parser.add_argument("--snr-min-db", type=float, default=-5.0)
    parser.add_argument("--snr-max-db", type=float, default=20.0)
    parser.add_argument("--clean-probability", type=float, default=0.0)
    parser.add_argument("--rir-probability", type=float, default=0.0)
    parser.add_argument("--rir-max-seconds", type=float, default=1.0)
    parser.add_argument("--interferer-probability", type=float, default=0.0)
    parser.add_argument("--sir-min-db", type=float, default=3.0)
    parser.add_argument("--sir-max-db", type=float, default=15.0)
    parser.add_argument("--archive-weight", type=float, default=1.0)
    parser.add_argument("--parquet-weight", type=float, default=1.0)
    parser.add_argument("--extracted-weight", type=float, default=1.0)
    parser.add_argument("--seed", type=int, default=20260808)
    parser.add_argument("--ema-decay", type=float, default=0.0)
    parser.add_argument("--init-checkpoint", type=Path)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()

    if args.resume and args.init_checkpoint:
        parser.error("--resume and --init-checkpoint are mutually exclusive")
    if args.snr_min_db > args.snr_max_db:
        parser.error("--snr-min-db must not exceed --snr-max-db")
    if not 0.0 <= args.ema_decay < 1.0:
        parser.error("--ema-decay must be in [0, 1)")

    import numpy as np
    import torch
    from df.enhance import df_features, init_df
    from df.loss import Istft, Loss
    from df.model import ModelParams
    from torch.utils.data import DataLoader

    from vox_rescue.archive_dataset import DNS5ArchiveDataset

    random.seed(args.seed)
    np.random.seed(args.seed)
    torch.manual_seed(args.seed)
    torch.cuda.manual_seed_all(args.seed)
    torch.backends.cudnn.benchmark = True
    torch.backends.cuda.matmul.allow_tf32 = True
    torch.set_float32_matmul_precision("high")
    initialized = init_df(
        model_base_dir=str(args.model_dir), log_file=None, log_level="ERROR"
    )
    model, df_state = initialized[0], initialized[1]
    params = ModelParams()
    device = next(model.parameters()).device
    if device.type != "cuda":
        raise RuntimeError(f"CUDA model required, got {device}")

    dataset = DNS5ArchiveDataset(
        args.manifest,
        args.rapidgzip,
        sample_rate=params.sr,
        segment_seconds=args.segment_seconds,
        snr_min_db=args.snr_min_db,
        snr_max_db=args.snr_max_db,
        rir_probability=args.rir_probability,
        rir_max_seconds=args.rir_max_seconds,
        interferer_probability=args.interferer_probability,
        sir_min_db=args.sir_min_db,
        sir_max_db=args.sir_max_db,
        clean_probability=args.clean_probability,
        clean_type_weights={
            "archive": args.archive_weight,
            "parquet": args.parquet_weight,
            "extracted": args.extracted_weight,
        },
    )
    print(
        f"DF3_DATASET_OK snr_db={args.snr_min_db:g}:{args.snr_max_db:g} "
        f"clean_probability={args.clean_probability:g} "
        f"weights={args.archive_weight:g}:{args.parquet_weight:g}:{args.extracted_weight:g} "
        f"rir_probability={args.rir_probability:g} "
        f"rir_max_seconds={args.rir_max_seconds:g} "
        f"interferer_probability={args.interferer_probability:g} "
        f"sir_db={args.sir_min_db:g}:{args.sir_max_db:g}",
        flush=True,
    )
    loader = DataLoader(
        dataset,
        batch_size=args.batch_size,
        num_workers=args.num_workers,
        pin_memory=True,
        persistent_workers=args.num_workers > 0,
        prefetch_factor=2 if args.num_workers > 0 else None,
        drop_last=True,
    )
    optimizer = torch.optim.AdamW(
        model.parameters(), lr=args.learning_rate, fused=device.type == "cuda"
    )
    istft = Istft(
        params.fft_size,
        params.hop_size,
        torch.as_tensor(df_state.fft_window().copy()),
    ).to(device)
    loss_fn = Loss(df_state, istft=istft).to(device)
    print(
        f"DF3_LOSS_OK mrsl={loss_fn.mrsl_f:g} "
        f"mrsl_complex={loss_fn.mrsl_fc:g} sdr={loss_fn.sdrl_f:g} "
        f"local_snr={loss_fn.lsnr_f:g}",
        flush=True,
    )
    # DF3's multi-frame complex einsum requires ComplexFloat. Native FP16
    # autocast turns the coefficients into ComplexHalf and fails in PyTorch.
    scaler = torch.amp.GradScaler("cuda", enabled=False)
    start_step = 0
    parent_checkpoint = None
    if args.init_checkpoint:
        state = torch.load(args.init_checkpoint, map_location=device, weights_only=False)
        model.load_state_dict(state["model"])
        start_step = int(state["step"])
        parent_checkpoint = str(args.init_checkpoint)
        print(
            f"DF3_INIT_OK step={start_step} source={args.init_checkpoint} "
            f"learning_rate={args.learning_rate:g}",
            flush=True,
        )
    if args.resume and args.checkpoint.exists():
        state = torch.load(args.checkpoint, map_location=device, weights_only=False)
        train_state = state.get("train_model")
        model.load_state_dict(train_state if train_state is not None else state["model"])
        optimizer.load_state_dict(state["optimizer"])
        # Optimizer checkpoints also contain the old learning rate. Respect the
        # explicit CLI value when beginning a new fine-tuning stage.
        for parameter_group in optimizer.param_groups:
            parameter_group["lr"] = args.learning_rate
        start_step = int(state["step"])
        parent_checkpoint = str(args.checkpoint)
        print(
            f"DF3_RESUME_OK step={start_step} learning_rate={args.learning_rate:g}",
            flush=True,
        )

    ema_state = None
    if args.ema_decay > 0:
        source_state = model.state_dict()
        if args.resume and args.checkpoint.exists() and "ema_model" in state:
            source_state = state["ema_model"]
        ema_state = {
            name: value.detach().clone()
            for name, value in source_state.items()
        }
        print(f"DF3_EMA_OK decay={args.ema_decay:g}", flush=True)

    model.train()
    started = time.perf_counter()
    examples = 0
    step = start_step
    iterator = iter(loader)
    last_step_time = time.perf_counter()
    while step < args.max_steps:
        noisy, clean = next(iterator)
        # libDF feature extraction is CPU-side; model forward/loss/backward stay on CUDA.
        noisy = noisy.float().contiguous()
        clean = clean.float().contiguous()
        reset_df_state(df_state)
        noisy_spec, erb_feat, spec_feat = df_features(
            noisy, df_state, params.nb_df, device=device
        )
        reset_df_state(df_state)
        clean_spec = df_features(clean, df_state, params.nb_df, device=device)[0]
        noise = noisy - clean
        snrs = 10.0 * torch.log10(
            clean.square().mean(dim=-1).clamp_min(1e-12)
            / noise.square().mean(dim=-1).clamp_min(1e-12)
        ).clamp(-30.0, 80.0)
        snrs = snrs.to(device=device, non_blocking=True)

        optimizer.zero_grad(set_to_none=True)
        enhanced_spec, mask, lsnr, _ = model(noisy_spec, erb_feat, spec_feat)
        noisy_complex = torch.view_as_complex(noisy_spec.float().contiguous())
        clean_complex = torch.view_as_complex(clean_spec.float().contiguous())
        enhanced_complex = torch.view_as_complex(enhanced_spec.float().contiguous())
        loss = loss_fn(
            clean_complex,
            noisy_complex,
            enhanced_complex,
            mask,
            lsnr,
            snrs,
        )
        scaler.scale(loss).backward()
        scaler.unscale_(optimizer)
        grad_norm = torch.nn.utils.clip_grad_norm_(model.parameters(), 5.0)
        scaler.step(optimizer)
        scaler.update()
        if ema_state is not None:
            with torch.no_grad():
                for name, value in model.state_dict().items():
                    if value.is_floating_point() or value.is_complex():
                        ema_state[name].mul_(args.ema_decay).add_(
                            value, alpha=1.0 - args.ema_decay
                        )
                    else:
                        ema_state[name].copy_(value)
        step += 1
        examples += int(noisy.shape[0])
        elapsed = max(time.perf_counter() - started, 1e-9)
        now = time.perf_counter()
        step_seconds = now - last_step_time
        last_step_time = now
        gpu_memory_mb = torch.cuda.max_memory_allocated(device) / (1024 * 1024)
        print(
            f"DF3_STEP step={step} loss={loss.item():.6f} "
            f"input_snr_db={snrs.mean().item():.2f} grad={float(grad_norm):.4f} "
            f"step_seconds={step_seconds:.3f} examples_per_second={examples / elapsed:.2f} "
            f"gpu_memory_mb={gpu_memory_mb:.0f}",
            flush=True,
        )
        if step % args.checkpoint_every == 0 or step == args.max_steps:
            inference_state = ema_state if ema_state is not None else model.state_dict()
            atomic_checkpoint(
                torch,
                {
                    "step": step,
                    "model": inference_state,
                    "train_model": model.state_dict() if ema_state is not None else None,
                    "ema_model": ema_state,
                    "ema_decay": args.ema_decay,
                    "optimizer": optimizer.state_dict(),
                    "model_dir": str(args.model_dir),
                    "parent_checkpoint": parent_checkpoint,
                    "training_args": portable_cli_args(args),
                },
                args.checkpoint,
            )
            print(f"DF3_CHECKPOINT_OK step={step} path={args.checkpoint}", flush=True)

    elapsed = max(time.perf_counter() - started, 1e-9)
    print(
        f"DF3_TRAIN_OK step={step} elapsed={elapsed:.3f}s "
        f"examples_per_second={examples / elapsed:.2f} checkpoint={args.checkpoint}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
