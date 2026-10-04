#!/usr/bin/env bash
set -Eeuo pipefail

PROJECT="/workspace/vox_rescue_clean"
STATE="/workspace/vox_datasets_v2/state"
MANIFEST="$PROJECT/manifests/clarity_v2/canonical.json"
PARENT="$PROJECT/checkpoints/clarity_v2/stage_a2_6500.pt"
CANDIDATE="$PROJECT/checkpoints/clarity_v2/stage_b_rir_6750.pt"
MODEL_DIR="$PROJECT/vendor/pretrained/DeepFilterNet3"

cd "$PROJECT"
mkdir -p outputs/clarity_v2/stage_b_rir logs

PYTHONPATH=src .venv/bin/python scripts/train_deepfilternet3.py \
  --manifest "$MANIFEST" --rapidgzip .venv/bin/rapidgzip \
  --model-dir "$MODEL_DIR" --checkpoint "$CANDIDATE" \
  --init-checkpoint "$PARENT" \
  --max-steps 6750 --checkpoint-every 50 \
  --batch-size 128 --num-workers 10 --segment-seconds 2 \
  --learning-rate 5e-7 --snr-min-db 5 --snr-max-db 30 \
  --clean-probability 0.20 --rir-probability 0.08 --rir-max-seconds 0.6 \
  --archive-weight 0.35 --parquet-weight 0.45 --extracted-weight 0.20 \
  --seed 20260810 \
  > logs/clarity_stage_b_rir_6750.log 2>&1

evaluate_case() {
  local name="$1"
  shift
  PYTHONPATH=src .venv/bin/python scripts/evaluate_deepfilternet3.py \
    --manifest "$MANIFEST" --model-dir "$MODEL_DIR" \
    --checkpoint "$CANDIDATE" --base-checkpoint "$PARENT" \
    --output-dir "outputs/clarity_v2/stage_b_rir/$name" \
    --samples 24 --seconds 3 "$@" \
    > "logs/clarity_stage_b_eval_${name}.log" 2>&1
}

evaluate_case hindi_reverb --clean-list manifests/clarity_v2/hindi_holdout_wavs.txt --reverb --rir-max-seconds 0.6 --snr-values=-5,0,5,10
evaluate_case dns_reverb --reverb --rir-max-seconds 0.6 --snr-values=-5,0,5,10
evaluate_case hindi_dry --clean-list manifests/clarity_v2/hindi_holdout_wavs.txt --snr-values=-5,0,5,10
evaluate_case dns_dry --snr-values=-5,0,5,10
evaluate_case hindi_clean --clean-list manifests/clarity_v2/hindi_holdout_wavs.txt --clean-only

date -u +%Y-%m-%dT%H:%M:%SZ > "$STATE/CLARITY_STAGE_B_RIR_EVAL_READY"
echo "CLARITY_STAGE_B_RIR_EVAL_READY checkpoint=$CANDIDATE"
