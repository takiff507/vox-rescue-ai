#!/usr/bin/env bash
set -Eeuo pipefail

AZCOPY="/workspace/tools/azcopy/azcopy"
BASE="https://dns4public.blob.core.windows.net/dns4archive/datasets_fullband/clean_fullband"
DEST="/workspace/dns5_archives/french_track2_identical"
LOG="/workspace/vox_rescue_clean/logs/french_fallback.log"
MAX_PARALLEL="${MAX_PARALLEL:-4}"

mkdir -p "$DEST" "$(dirname "$LOG")"
exec > >(tee -a "$LOG") 2>&1
unset AZCOPY_CONCURRENCY_VALUE || true

FILES=(
  datasets_fullband.clean_fullband.french_speech_000_NA_NA.tar.bz2
  datasets_fullband.clean_fullband.french_speech_001_NA_NA.tar.bz2
  datasets_fullband.clean_fullband.french_speech_002_NA_NA.tar.bz2
  datasets_fullband.clean_fullband.french_speech_003_NA_NA.tar.bz2
  datasets_fullband.clean_fullband.french_speech_004_NA_NA.tar.bz2
  datasets_fullband.clean_fullband.french_speech_005_NA_NA.tar.bz2
  datasets_fullband.clean_fullband.french_speech_006_NA_NA.tar.bz2
  datasets_fullband.clean_fullband.french_speech_007_NA_NA.tar.bz2
  datasets_fullband.clean_fullband.french_speech_008_NA_NA.tar.bz2
)

download_one() {
  local name="$1"
  local target="$DEST/$name"
  if [[ -s "$target" && -f "$target.done" ]]; then
    echo "[$(date -Is)] already complete $name"
    return 0
  fi
  echo "[$(date -Is)] downloading $name"
  "$AZCOPY" copy "$BASE/$name" "$target" --overwrite=true --output-type=text
  touch "$target.done"
  echo "[$(date -Is)] complete $name bytes=$(stat -c %s "$target")"
}

pids=()
for name in "${FILES[@]}"; do
  download_one "$name" &
  pids+=("$!")
  if (( ${#pids[@]} >= MAX_PARALLEL )); then
    wait "${pids[0]}"
    pids=("${pids[@]:1}")
  fi
done
for pid in "${pids[@]}"; do
  wait "$pid"
done

echo "[$(date -Is)] validating French fallback shards"
validation_pids=()
for name in "${FILES[@]}"; do
  bzip2 -t "$DEST/$name" &
  validation_pids+=("$!")
done
for pid in "${validation_pids[@]}"; do
  wait "$pid"
done
echo "[$(date -Is)] FRENCH_FALLBACK_VALIDATION_OK files=${#FILES[@]}"
