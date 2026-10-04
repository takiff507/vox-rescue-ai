#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="/workspace/vox_datasets_v2"
ARCHIVES="$ROOT/archives"
LICENSED="$ROOT/licensed"
RESEARCH_ONLY="$ROOT/research_only"
STAGING="$ROOT/staging"
STATE="$ROOT/state"
PROJECT="/workspace/vox_rescue_clean"

mkdir -p "$LICENSED" "$RESEARCH_ONLY" "$STAGING" "$STATE"

for required in \
  "$ARCHIVES/musan/musan.tar.gz" \
  "$ARCHIVES/rirs_noises/rirs_noises.zip"; do
  if [[ ! -s "$required" ]]; then
    echo "MISSING_ARCHIVE $required" >&2
    exit 30
  fi
done

if (( $(find "$ARCHIVES/ears_nc" -maxdepth 1 -type f -name 'p*.zip' | wc -l) != 107 )); then
  echo "EARS_COUNT_FAIL" >&2
  exit 31
fi
if (( $(find "$ARCHIVES/indicvoices_r_hindi/data" -maxdepth 1 -type f -name '*.parquet' | wc -l) != 10 )); then
  echo "HINDI_COUNT_FAIL" >&2
  exit 32
fi

if [[ ! -f "$STATE/ARCHIVES_VERIFIED" ]]; then
  echo "INTEGRITY_START"
  gzip -t "$ARCHIVES/musan/musan.tar.gz" &
  gzip_pid=$!
  unzip -tq "$ARCHIVES/rirs_noises/rirs_noises.zip" &
  rir_pid=$!
  find "$ARCHIVES/ears_nc" -maxdepth 1 -type f -name 'p*.zip' -print0 \
    | xargs -0 -r -n 1 -P 16 unzip -tq &
  ears_pid=$!

  wait "$gzip_pid"
  wait "$rir_pid"
  wait "$ears_pid"
  "$PROJECT/.venv/bin/python" "$PROJECT/scripts/inspect_hindi_parquet.py" \
    > "$STATE/indic_hindi_parquet_report.json"
  date -u +%Y-%m-%dT%H:%M:%SZ > "$STATE/ARCHIVES_VERIFIED"
  echo "INTEGRITY_OK"
else
  echo "INTEGRITY_ALREADY_VERIFIED"
fi

if [[ ! -f "$STATE/MUSAN_EXTRACTED" ]]; then
  musan_stage="$STAGING/musan"
  mkdir -p "$musan_stage"
  tar --no-same-owner --no-same-permissions --use-compress-program=pigz \
    -xf "$ARCHIVES/musan/musan.tar.gz" -C "$musan_stage"
  if [[ ! -d "$musan_stage/musan/noise" || ! -d "$musan_stage/musan/music" ]]; then
    echo "MUSAN_LAYOUT_FAIL" >&2
    exit 33
  fi
  if [[ -e "$LICENSED/musan" ]]; then
    echo "MUSAN_DESTINATION_EXISTS_WITHOUT_MARKER" >&2
    exit 35
  fi
  mv "$musan_stage/musan" "$LICENSED/musan"
  date -u +%Y-%m-%dT%H:%M:%SZ > "$STATE/MUSAN_EXTRACTED"
fi

if [[ ! -f "$STATE/RIRS_EXTRACTED" ]]; then
  rir_stage="$STAGING/rirs_noises"
  mkdir -p "$rir_stage"
  if [[ ! -f "$STATE/RIRS_STAGE_READY" ]]; then
    unzip -q -o "$ARCHIVES/rirs_noises/rirs_noises.zip" -d "$rir_stage"
  fi
  if (( $(find "$rir_stage" -type f | wc -l) < 1000 )); then
    echo "RIRS_LAYOUT_FAIL" >&2
    exit 34
  fi
  if [[ -e "$LICENSED/rirs_noises" ]]; then
    echo "RIRS_DESTINATION_EXISTS_WITHOUT_MARKER" >&2
    exit 36
  fi
  mv "$rir_stage" "$LICENSED/rirs_noises"
  date -u +%Y-%m-%dT%H:%M:%SZ > "$STATE/RIRS_EXTRACTED"
fi

sha256sum \
  "$ARCHIVES/musan/musan.tar.gz" \
  "$ARCHIVES/rirs_noises/rirs_noises.zip" \
  > "$STATE/core_archives.sha256"

date -u +%Y-%m-%dT%H:%M:%SZ > "$STATE/CLARITY_DATA_READY"
du -sh "$LICENSED/musan" "$LICENSED/rirs_noises" "$ARCHIVES/indicvoices_r_hindi" "$ARCHIVES/ears_nc"
echo "CLARITY_DATA_READY"
