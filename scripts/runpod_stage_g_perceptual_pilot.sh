#!/usr/bin/env bash
set -Eeuo pipefail

PROJECT="/workspace/vox_rescue_clean"
STATE="/workspace/vox_datasets_v2/state"
MANIFEST="$PROJECT/manifests/clarity_v2/canonical.json"
PARENT="$PROJECT/checkpoints/clarity_v2/stage_a2_6500.pt"
CANDIDATE="$PROJECT/checkpoints/clarity_v3/stage_g_perceptual_6800.pt"
MODEL_DIR="$PROJECT/vendor/experiments/DeepFilterNet3ClarityV3"
OUTPUT="$PROJECT/outputs/clarity_v3/stage_g_perceptual"

cd "$PROJECT"
mkdir -p "$MODEL_DIR/checkpoints" "$OUTPUT" logs checkpoints/clarity_v3
cp configs/df3_clarity_v3.ini "$MODEL_DIR/config.ini"
cp vendor/pretrained/DeepFilterNet3/checkpoints/model_120.ckpt.best \
  "$MODEL_DIR/checkpoints/model_120.ckpt.best"

PYTHONPATH=src .venv/bin/python scripts/train_deepfilternet3.py \
  --manifest "$MANIFEST" --rapidgzip .venv/bin/rapidgzip \
  --model-dir "$MODEL_DIR" --checkpoint "$CANDIDATE" \
  --init-checkpoint "$PARENT" \
  --max-steps 6800 --checkpoint-every 100 \
  --batch-size 128 --num-workers 10 --segment-seconds 2 \
  --learning-rate 2e-7 --snr-min-db -5 --snr-max-db 30 \
  --clean-probability 0.25 --rir-probability 0.05 --rir-max-seconds 0.6 \
  --interferer-probability 0.04 --sir-min-db 3 --sir-max-db 15 \
  --archive-weight 0.35 --parquet-weight 0.45 --extracted-weight 0.20 \
  --ema-decay 0.99 --seed 20260815 \
  > logs/clarity_stage_g_perceptual_6800.log 2>&1

evaluate_case() {
  local name="$1"
  shift
  PYTHONPATH=src .venv/bin/python scripts/evaluate_deepfilternet3.py \
    --manifest "$MANIFEST" --model-dir "$MODEL_DIR" \
    --checkpoint "$CANDIDATE" --base-checkpoint "$PARENT" \
    --output-dir "$OUTPUT/$name" --samples 24 --seconds 3 "$@" \
    > "logs/clarity_stage_g_eval_${name}.log" 2>&1
}

evaluate_case hindi_normal --clean-list manifests/clarity_v2/hindi_holdout_wavs.txt --snr-values=-5,0,5,10
evaluate_case dns_normal --snr-values=-5,0,5,10
evaluate_case hindi_clean --clean-list manifests/clarity_v2/hindi_holdout_wavs.txt --clean-only
evaluate_case hindi_hard --clean-list manifests/clarity_v2/hindi_holdout_wavs.txt --snr-values=-10,-5,0,5
evaluate_case dns_hard --snr-values=-10,-5,0,5
evaluate_case hindi_reverb --clean-list manifests/clarity_v2/hindi_holdout_wavs.txt --reverb --rir-max-seconds 0.6 --snr-values=-5,0,5,10
evaluate_case dns_reverb --reverb --rir-max-seconds 0.6 --snr-values=-5,0,5,10
evaluate_case hindi_interferer --clean-list manifests/clarity_v2/hindi_holdout_wavs.txt --interferer --snr-values=0,5,10,15
evaluate_case dns_interferer --interferer --snr-values=0,5,10,15

sha256sum "$PARENT" "$CANDIDATE" > "$OUTPUT/checkpoint_hashes.sha256"
date -u +%Y-%m-%dT%H:%M:%SZ > "$STATE/CLARITY_STAGE_G_PERCEPTUAL_EVAL_READY"
echo "CLARITY_STAGE_G_PERCEPTUAL_EVAL_READY checkpoint=$CANDIDATE"
