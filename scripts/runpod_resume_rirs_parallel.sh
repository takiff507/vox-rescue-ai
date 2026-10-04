#!/usr/bin/env bash
set -Eeuo pipefail

PROJECT="/workspace/vox_rescue_clean"
DATA_ROOT="/workspace/vox_datasets_v2"

cd "$PROJECT"
"$PROJECT/.venv/bin/python" "$PROJECT/scripts/parallel_extract_zip.py" \
  --archive "$DATA_ROOT/archives/rirs_noises/rirs_noises.zip" \
  --destination "$DATA_ROOT/staging/rirs_noises" \
  --workers 16 \
  --ready-marker "$DATA_ROOT/state/RIRS_STAGE_READY"

bash "$PROJECT/scripts/runpod_verify_extract_clarity.sh"
