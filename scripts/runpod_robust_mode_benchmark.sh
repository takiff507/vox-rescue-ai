#!/usr/bin/env bash
set -Eeuo pipefail

PROJECT="/workspace/vox_rescue_clean"
STATE="/workspace/vox_datasets_v2/state"
MANIFEST="$PROJECT/manifests/clarity_v2/canonical.json"
BASE="$PROJECT/checkpoints/df3_stage1_5000.pt"
MODEL_DIR="$PROJECT/vendor/experiments/DeepFilterNet3ClarityV3"
OUTPUT="$PROJECT/outputs/production_mode_benchmark"

cd "$PROJECT"
mkdir -p "$OUTPUT" logs

evaluate_case() {
  local mode="$1"
  local checkpoint="$2"
  local name="$3"
  shift 3
  PYTHONPATH=src .venv/bin/python scripts/evaluate_deepfilternet3.py \
    --manifest "$MANIFEST" --model-dir "$MODEL_DIR" \
    --checkpoint "$checkpoint" --base-checkpoint "$BASE" \
    --output-dir "$OUTPUT/$mode/$name" --samples 96 --seconds 3 "$@" \
    > "logs/robust_${mode}_${name}.log" 2>&1
}

benchmark_mode() {
  local mode="$1"
  local checkpoint="$2"
  evaluate_case "$mode" "$checkpoint" dns_normal --snr-values=-5,0,5,10
  evaluate_case "$mode" "$checkpoint" dns_hard --snr-values=-10,-5,0,5
  evaluate_case "$mode" "$checkpoint" dns_reverb --reverb --rir-max-seconds 0.6 --snr-values=-5,0,5,10
  evaluate_case "$mode" "$checkpoint" dns_interferer --interferer --snr-values=0,5,10,15
  sha256sum "$checkpoint" > "$OUTPUT/$mode/checkpoint.sha256"
}

benchmark_mode universal "$PROJECT/checkpoints/clarity_v2/stage_a2_6500.pt"
benchmark_mode clarity_plus "$PROJECT/checkpoints/clarity_v3/stage_g_perceptual_6800.pt"
benchmark_mode voice_isolation "$PROJECT/checkpoints/clarity_v2/stage_f_task_merge.pt"

date -u +%Y-%m-%dT%H:%M:%SZ > "$STATE/ROBUST_PRODUCTION_MODE_BENCHMARK_READY"
echo "ROBUST_PRODUCTION_MODE_BENCHMARK_READY output=$OUTPUT"
