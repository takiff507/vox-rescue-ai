#!/usr/bin/env bash
set -Eeuo pipefail

PROJECT="/workspace/vox_rescue_clean"
STATE="/workspace/vox_datasets_v2/state"
PRODUCTION="$PROJECT/checkpoints/production/v3"
UNIVERSAL_SOURCE="$PROJECT/checkpoints/clarity_v3/stage_i_hard_noise_7000.pt"
VOICE_SOURCE="$PROJECT/checkpoints/clarity_v2/stage_f_task_merge.pt"

cd "$PROJECT"
mkdir -p "$PRODUCTION" outputs/production_v3 logs

.venv/bin/python scripts/make_checkpoint_portable.py \
  "$UNIVERSAL_SOURCE" "$PRODUCTION/vox_rescue_universal_v3_step7000.pt"
.venv/bin/python scripts/make_checkpoint_portable.py \
  "$VOICE_SOURCE" "$PRODUCTION/vox_rescue_voice_isolation_v3_step7250.pt"
.venv/bin/python scripts/build_production_v3_manifest.py \
  > logs/production_v3_manifest.log 2>&1

CUDA_VISIBLE_DEVICES="" PYTHONPATH=src .venv/bin/python scripts/benchmark_streaming_latency.py \
  --model-dir vendor/pretrained/DeepFilterNet3 \
  --checkpoint "$PRODUCTION/vox_rescue_universal_v3_step7000.pt" \
  --iterations 80 --output outputs/production_v3/streaming_latency.json \
  > logs/production_v3_latency.log 2>&1

sha256sum "$PRODUCTION"/*.pt > "$PRODUCTION/checkpoints.sha256"
date -u +%Y-%m-%dT%H:%M:%SZ > "$STATE/PRODUCTION_V3_BUNDLE_READY"
echo "PRODUCTION_V3_BUNDLE_READY directory=$PRODUCTION"
