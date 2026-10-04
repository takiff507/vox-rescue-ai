#!/usr/bin/env bash
set -Eeuo pipefail

PROJECT="/workspace/vox_rescue_clean"
STATE="/workspace/vox_datasets_v2/state"
MANIFEST="$PROJECT/manifests/clarity_v2/canonical.json"
BASELINE="$PROJECT/checkpoints/df3_stage1_5000.pt"
MODEL_DIR="$PROJECT/vendor/pretrained/DeepFilterNet3"
RAPIDGZIP="$PROJECT/.venv/bin/rapidgzip"

cd "$PROJECT"
while [[ ! -f "$STATE/CLARITY_PREP_READY" ]]; do
  if ! pgrep -f 'runpod_prepare_clarity.sh' >/dev/null; then
    echo "CLARITY_BENCH prep process missing before READY marker" >&2
    exit 50
  fi
  echo "CLARITY_BENCH waiting_for_prep"
  sleep 10
done

mkdir -p checkpoints/clarity_v2 logs
run_candidate() {
  local batch="$1"
  local workers="$2"
  local output="checkpoints/clarity_v2/smoke_b${batch}.pt"
  PYTHONPATH=src .venv/bin/python scripts/train_deepfilternet3.py \
    --manifest "$MANIFEST" \
    --rapidgzip "$RAPIDGZIP" \
    --model-dir "$MODEL_DIR" \
    --checkpoint "$output" \
    --init-checkpoint "$BASELINE" \
    --max-steps 5010 \
    --checkpoint-every 10 \
    --batch-size "$batch" \
    --num-workers "$workers" \
    --segment-seconds 2 \
    --learning-rate 2e-6 \
    --snr-min-db 5 \
    --snr-max-db 30 \
    --clean-probability 0.20 \
    --archive-weight 0.35 \
    --parquet-weight 0.45 \
    --extracted-weight 0.20 \
    --seed "$((20260808 + batch))" \
    > "logs/clarity_smoke_b${batch}.log" 2>&1
}

echo "CLARITY_BENCH batch64_start"
run_candidate 64 10
echo "CLARITY_BENCH batch64_ok"

echo "CLARITY_BENCH batch128_start"
if run_candidate 128 10; then
  echo "CLARITY_BENCH batch128_ok"
else
  echo "CLARITY_BENCH batch128_failed_fallback64"
fi

date -u +%Y-%m-%dT%H:%M:%SZ > "$STATE/CLARITY_GPU_BENCH_READY"
echo "CLARITY_BENCH ready_for_selection"
