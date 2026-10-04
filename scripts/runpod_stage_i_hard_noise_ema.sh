#!/usr/bin/env bash
set -Eeuo pipefail

PROJECT="/workspace/vox_rescue_clean"
STATE="/workspace/vox_datasets_v2/state"
MANIFEST="$PROJECT/manifests/clarity_v2/canonical.json"
BASE="$PROJECT/checkpoints/df3_stage1_5000.pt"
PARENT="$PROJECT/checkpoints/clarity_v2/stage_a2_6500.pt"
CANDIDATE="$PROJECT/checkpoints/clarity_v3/stage_i_hard_noise_7000.pt"
MODEL_DIR="$PROJECT/vendor/pretrained/DeepFilterNet3"
OUTPUT="$PROJECT/outputs/clarity_v3/stage_i_hard_noise"

cd "$PROJECT"
mkdir -p "$OUTPUT" logs checkpoints/clarity_v3

PYTHONPATH=src .venv/bin/python scripts/train_deepfilternet3.py \
  --manifest "$MANIFEST" --rapidgzip .venv/bin/rapidgzip \
  --model-dir "$MODEL_DIR" --checkpoint "$CANDIDATE" \
  --init-checkpoint "$PARENT" \
  --max-steps 7000 --checkpoint-every 100 \
  --batch-size 128 --num-workers 10 --segment-seconds 2 \
  --learning-rate 3e-7 --snr-min-db -10 --snr-max-db 15 \
  --clean-probability 0.30 --rir-probability 0.05 --rir-max-seconds 0.6 \
  --interferer-probability 0 \
  --archive-weight 0.35 --parquet-weight 0.45 --extracted-weight 0.20 \
  --ema-decay 0.99 --seed 20260817 \
  > logs/clarity_stage_i_hard_noise_7000.log 2>&1

evaluate_case() {
  local name="$1"
  local samples="$2"
  shift 2
  PYTHONPATH=src .venv/bin/python scripts/evaluate_deepfilternet3.py \
    --manifest "$MANIFEST" --model-dir "$MODEL_DIR" \
    --checkpoint "$CANDIDATE" --base-checkpoint "$BASE" \
    --output-dir "$OUTPUT/$name" --samples "$samples" --seconds 3 "$@" \
    > "logs/clarity_stage_i_eval_${name}.log" 2>&1
}

evaluate_case dns_hard 96 --snr-values=-10,-5,0,5
evaluate_case dns_normal 96 --snr-values=-5,0,5,10
evaluate_case dns_reverb 96 --reverb --rir-max-seconds 0.6 --snr-values=-5,0,5,10
evaluate_case hindi_hard 24 --clean-list manifests/clarity_v2/hindi_holdout_wavs.txt --snr-values=-10,-5,0,5
evaluate_case hindi_normal 24 --clean-list manifests/clarity_v2/hindi_holdout_wavs.txt --snr-values=-5,0,5,10
evaluate_case hindi_clean 24 --clean-list manifests/clarity_v2/hindi_holdout_wavs.txt --clean-only

sha256sum "$BASE" "$PARENT" "$CANDIDATE" > "$OUTPUT/checkpoint_hashes.sha256"
date -u +%Y-%m-%dT%H:%M:%SZ > "$STATE/CLARITY_STAGE_I_HARD_NOISE_EVAL_READY"
echo "CLARITY_STAGE_I_HARD_NOISE_EVAL_READY checkpoint=$CANDIDATE"
