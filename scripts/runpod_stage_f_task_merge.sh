#!/usr/bin/env bash
set -Eeuo pipefail

PROJECT="/workspace/vox_rescue_clean"
STATE="/workspace/vox_datasets_v2/state"
MANIFEST="$PROJECT/manifests/clarity_v2/canonical.json"
BASE="$PROJECT/checkpoints/clarity_v2/stage_a2_6500.pt"
CANDIDATE="$PROJECT/checkpoints/clarity_v2/stage_f_task_merge.pt"
MODEL_DIR="$PROJECT/vendor/pretrained/DeepFilterNet3"
OUTPUT="$PROJECT/outputs/clarity_v2/stage_f_task_merge"

cd "$PROJECT"
mkdir -p "$OUTPUT" logs

.venv/bin/python scripts/merge_task_vectors.py \
  --base "$BASE" \
  --branch "$PROJECT/checkpoints/clarity_v2/stage_c_interferer_6750.pt:0.75" \
  --branch "$PROJECT/checkpoints/clarity_v2/stage_d_hard_noise_6750.pt:1.0" \
  --branch "$PROJECT/checkpoints/clarity_v2/stage_e_balanced_7250.pt:0.75" \
  --branch "$PROJECT/checkpoints/clarity_v2/stage_a3_7500.pt:0.5" \
  --output "$CANDIDATE" --step 7250 \
  > logs/clarity_stage_f_merge.log 2>&1

evaluate_case() {
  local name="$1"
  shift
  PYTHONPATH=src .venv/bin/python scripts/evaluate_deepfilternet3.py \
    --manifest "$MANIFEST" --model-dir "$MODEL_DIR" \
    --checkpoint "$CANDIDATE" --base-checkpoint "$BASE" \
    --output-dir "$OUTPUT/$name" --samples 24 --seconds 3 "$@" \
    > "logs/clarity_stage_f_eval_${name}.log" 2>&1
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

sha256sum "$BASE" "$CANDIDATE" > "$OUTPUT/checkpoint_hashes.sha256"
date -u +%Y-%m-%dT%H:%M:%SZ > "$STATE/CLARITY_STAGE_F_TASK_MERGE_EVAL_READY"
echo "CLARITY_STAGE_F_TASK_MERGE_EVAL_READY checkpoint=$CANDIDATE"
