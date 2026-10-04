#!/usr/bin/env bash
set -Eeuo pipefail

PROJECT="/workspace/vox_rescue_clean"
STATE="/workspace/vox_datasets_v2/state"
MANIFEST="$PROJECT/manifests/clarity_v2/canonical.json"
BASELINE="$PROJECT/checkpoints/df3_stage1_5000.pt"
SOURCE="$PROJECT/checkpoints/clarity_v2/stage_a2_6500.pt"
CANDIDATE="$PROJECT/checkpoints/clarity_v2/best_production_candidate.pt"
MODEL_DIR="$PROJECT/vendor/pretrained/DeepFilterNet3"
OUTPUT="$PROJECT/outputs/clarity_v2/final_benchmark"

cd "$PROJECT"
mkdir -p "$OUTPUT" logs
if [[ ! -e "$CANDIDATE" ]]; then
  cp --reflink=auto "$SOURCE" "$CANDIDATE"
fi

evaluate_case() {
  local name="$1"
  shift
  PYTHONPATH=src .venv/bin/python scripts/evaluate_deepfilternet3.py \
    --manifest "$MANIFEST" --model-dir "$MODEL_DIR" \
    --checkpoint "$CANDIDATE" --base-checkpoint "$BASELINE" \
    --output-dir "$OUTPUT/$name" --samples 24 --seconds 3 "$@" \
    > "logs/clarity_final_eval_${name}.log" 2>&1
}

evaluate_case hindi_hard --clean-list manifests/clarity_v2/hindi_holdout_wavs.txt --snr-values=-10,-5,0,5
evaluate_case dns_hard --snr-values=-10,-5,0,5
evaluate_case hindi_reverb --clean-list manifests/clarity_v2/hindi_holdout_wavs.txt --reverb --rir-max-seconds 0.6 --snr-values=-5,0,5,10
evaluate_case dns_reverb --reverb --rir-max-seconds 0.6 --snr-values=-5,0,5,10
evaluate_case hindi_interferer --clean-list manifests/clarity_v2/hindi_holdout_wavs.txt --interferer --snr-values=0,5,10,15
evaluate_case dns_interferer --interferer --snr-values=0,5,10,15

PYTHONPATH=src .venv/bin/python scripts/summarize_final_benchmark.py \
  > logs/clarity_final_scorecard.log 2>&1
sha256sum "$BASELINE" "$CANDIDATE" > "$OUTPUT/checkpoint_hashes.sha256"
date -u +%Y-%m-%dT%H:%M:%SZ > "$STATE/CLARITY_FINAL_BENCHMARK_READY"
echo "CLARITY_FINAL_BENCHMARK_READY candidate=$CANDIDATE"
