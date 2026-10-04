#!/usr/bin/env bash
set -Eeuo pipefail

PROJECT="/workspace/vox_rescue_clean"
DATA_ROOT="/workspace/vox_datasets_v2"
STAGE="$DATA_ROOT/staging/rirs_noises"
STATE="$DATA_ROOT/state"
EXPECTED=61273

actual="$(find "$STAGE" -type f | wc -l)"
if [[ "$actual" -ne "$EXPECTED" ]]; then
  echo "RIRS_FINAL_COUNT_FAIL expected=$EXPECTED actual=$actual" >&2
  exit 60
fi
if find "$STAGE" -type f -name '.*.extract-*' -print -quit | grep -q .; then
  echo "RIRS_FINAL_TEMP_FAIL" >&2
  exit 61
fi

extractor_pid="$(pgrep -f '^/workspace/vox_rescue_clean/.venv/bin/python /workspace/vox_rescue_clean/scripts/parallel_extract_zip.py --archive /workspace/vox_datasets_v2/archives/rirs_noises/rirs_noises.zip' | head -n 1 || true)"
if [[ -n "$extractor_pid" ]]; then
  kill -TERM "$extractor_pid"
fi

temporary="$STATE/RIRS_STAGE_READY.tmp"
printf '{"expected_files":%d,"actual_files":%d,"validated":"crc_or_atomic_extract"}\n' \
  "$EXPECTED" "$actual" > "$temporary"
mv "$temporary" "$STATE/RIRS_STAGE_READY"
echo "RIRS_STAGE_READY files=$actual"

bash "$PROJECT/scripts/runpod_verify_extract_clarity.sh"
