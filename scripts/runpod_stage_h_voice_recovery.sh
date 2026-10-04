#!/usr/bin/env bash
set -Eeuo pipefail

PROJECT="/workspace/vox_rescue_clean"
STATE="/workspace/vox_datasets_v2/state"
MANIFEST="$PROJECT/manifests/clarity_v2/canonical.json"
BASE="$PROJECT/checkpoints/clarity_v2/stage_a2_6500.pt"
PARENT="$PROJECT/checkpoints/clarity_v3/stage_g_perceptual_6800.pt"
CANDIDATE="$PROJECT/checkpoints/clarity_v3/stage_h_voice_recovery_7200.pt"
MODEL_DIR="$PROJECT/vendor/experiments/DeepFilterNet3ClarityV3"
OUTPUT="$PROJECT/outputs/clarity_v3/stage_h_voice_recovery"

cd "$PROJECT"
mkdir -p "$OUTPUT" logs checkpoints/clarity_v3

PYTHONPATH=src .venv/bin/python scripts/train_deepfilternet3.py \
  --manifest "$MANIFEST" --rapidgzip .venv/bin/rapidgzip \
  --model-dir "$MODEL_DIR" --checkpoint "$CANDIDATE" \
  --init-checkpoint "$PARENT" \
  --max-steps 7200 --checkpoint-every 100 \
  --batch-size 128 --num-workers 10 --segment-seconds 2 \
  --learning-rate 1.5e-7 --snr-min-db -5 --snr-max-db 30 \
  --clean-probability 0.30 --rir-probability 0.05 --rir-max-seconds 0.6 \
  --interferer-probability 0.18 --sir-min-db 3 --sir-max-db 15 \
  --archive-weight 0.35 --parquet-weight 0.45 --extracted-weight 0.20 \
  --ema-decay 0.99 --seed 20260816 \
  > logs/clarity_stage_h_voice_recovery_7200.log 2>&1

evaluate_case() {
  local name="$1"
  shift
  PYTHONPATH=src .venv/bin/python scripts/evaluate_deepfilternet3.py \
    --manifest "$MANIFEST" --model-dir "$MODEL_DIR" \
    --checkpoint "$CANDIDATE" --base-checkpoint "$BASE" \
    --output-dir "$OUTPUT/$name" --samples 24 --seconds 3 "$@" \
    > "logs/clarity_stage_h_eval_${name}.log" 2>&1
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

sha256sum "$BASE" "$PARENT" "$CANDIDATE" > "$OUTPUT/checkpoint_hashes.sha256"
date -u +%Y-%m-%dT%H:%M:%SZ > "$STATE/CLARITY_STAGE_H_VOICE_RECOVERY_EVAL_READY"
echo "CLARITY_STAGE_H_VOICE_RECOVERY_EVAL_READY checkpoint=$CANDIDATE"
