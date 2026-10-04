#!/usr/bin/env bash
set -Eeuo pipefail

PROJECT="/workspace/vox_rescue_clean"
DATA_ROOT="/workspace/vox_datasets_v2"
LOG_PREFIX="CLARITY_PREP"

cd "$PROJECT"
while [[ ! -f "$DATA_ROOT/state/CLARITY_DATA_READY" ]]; do
  if ! pgrep -f 'parallel_extract_zip.py.*rirs_noises.zip' >/dev/null; then
    echo "$LOG_PREFIX extraction process missing before READY marker" >&2
    exit 40
  fi
  echo "$LOG_PREFIX waiting_for_data"
  sleep 10
done

echo "$LOG_PREFIX building_manifest"
PYTHONPATH=src .venv/bin/python scripts/build_clarity_manifest.py

echo "$LOG_PREFIX loader_smoke"
PYTHONPATH=src .venv/bin/python scripts/smoke_clarity_dataset.py \
  --manifest manifests/clarity_v2/canonical.json \
  --rapidgzip .venv/bin/rapidgzip \
  --batch-size 64 \
  --num-workers 10 \
  --batches 4

sha256sum checkpoints/df3_stage1_5000.pt checkpoints/best.pt
date -u +%Y-%m-%dT%H:%M:%SZ > "$DATA_ROOT/state/CLARITY_PREP_READY"
echo "$LOG_PREFIX ready_for_gpu_smoke"
