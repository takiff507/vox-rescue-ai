#!/usr/bin/env bash
set -Eeuo pipefail

PROJECT="/workspace/vox_rescue_clean"
STATE="/workspace/vox_datasets_v2/state"
MANIFEST="$PROJECT/manifests/clarity_v2/canonical.json"
BASELINE="$PROJECT/checkpoints/df3_stage1_5000.pt"
PARENT="$PROJECT/checkpoints/clarity_v2/stage_a_5500.pt"
CANDIDATE="$PROJECT/checkpoints/clarity_v2/stage_a2_6500.pt"
MODEL_DIR="$PROJECT/vendor/pretrained/DeepFilterNet3"

cd "$PROJECT"
mkdir -p outputs/clarity_v2/stage_a2 logs

PYTHONPATH=src .venv/bin/python scripts/train_deepfilternet3.py \
  --manifest "$MANIFEST" \
  --rapidgzip .venv/bin/rapidgzip \
  --model-dir "$MODEL_DIR" \
  --checkpoint "$CANDIDATE" \
  --init-checkpoint "$PARENT" \
  --max-steps 6500 \
  --checkpoint-every 100 \
  --batch-size 128 \
  --num-workers 10 \
  --segment-seconds 2 \
  --learning-rate 1e-6 \
  --snr-min-db 5 \
  --snr-max-db 30 \
  --clean-probability 0.20 \
  --archive-weight 0.35 \
  --parquet-weight 0.45 \
  --extracted-weight 0.20 \
  --seed 20260809 \
  > logs/clarity_stage_a2_6500.log 2>&1

PYTHONPATH=src .venv/bin/python scripts/evaluate_deepfilternet3.py \
  --manifest "$MANIFEST" --model-dir "$MODEL_DIR" \
  --checkpoint "$CANDIDATE" --base-checkpoint "$BASELINE" \
  --clean-list manifests/clarity_v2/hindi_holdout_wavs.txt \
  --output-dir outputs/clarity_v2/stage_a2/hindi_noisy \
  --samples 24 --seconds 3 --snr-values=-5,0,5,10 \
  > logs/clarity_stage_a2_eval_hindi.log 2>&1

PYTHONPATH=src .venv/bin/python scripts/evaluate_deepfilternet3.py \
  --manifest "$MANIFEST" --model-dir "$MODEL_DIR" \
  --checkpoint "$CANDIDATE" --base-checkpoint "$BASELINE" \
  --output-dir outputs/clarity_v2/stage_a2/dns_noisy \
  --samples 24 --seconds 3 --snr-values=-5,0,5,10 \
  > logs/clarity_stage_a2_eval_dns.log 2>&1

PYTHONPATH=src .venv/bin/python scripts/evaluate_deepfilternet3.py \
  --manifest "$MANIFEST" --model-dir "$MODEL_DIR" \
  --checkpoint "$CANDIDATE" --base-checkpoint "$BASELINE" \
  --clean-list manifests/clarity_v2/hindi_holdout_wavs.txt \
  --output-dir outputs/clarity_v2/stage_a2/hindi_clean \
  --samples 24 --seconds 3 --clean-only \
  > logs/clarity_stage_a2_eval_clean.log 2>&1

date -u +%Y-%m-%dT%H:%M:%SZ > "$STATE/CLARITY_STAGE_A2_EVAL_READY"
echo "CLARITY_STAGE_A2_EVAL_READY checkpoint=$CANDIDATE"
