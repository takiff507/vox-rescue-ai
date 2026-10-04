#!/usr/bin/env bash
set -Eeuo pipefail

AZCOPY="/workspace/tools/azcopy/azcopy"
BASE="https://dnschallengepublic.blob.core.windows.net/dns5archive/V5_training_dataset"
ROOT="/workspace/datasets_fullband"
CACHE="/workspace/azcopy_cache"
LOG="/workspace/vox_rescue_clean/logs/azcopy_clean.log"

mkdir -p "$ROOT" "$CACHE" "$(dirname "$LOG")"
exec > >(tee -a "$LOG") 2>&1
# Let AzCopy auto-tune transfer concurrency for the host and route.
unset AZCOPY_CONCURRENCY_VALUE || true
PIGZ_THREADS="${PIGZ_THREADS:-$(nproc)}"
TAR_Z=(--use-compress-program="pigz -p ${PIGZ_THREADS}")

download_blob() {
  local remote="$1"
  local local_name="$2"
  echo "[$(date -Is)] azcopy $remote"
  "$AZCOPY" copy "$BASE/$remote" "$CACHE/$local_name" --overwrite=true --output-type=text
}

extract_single_gzip() {
  local archive="$1"
  echo "[$(date -Is)] validating $archive"
  tar "${TAR_Z[@]}" --no-same-owner --no-same-permissions -tf "$archive" >/dev/null
  echo "[$(date -Is)] extracting $archive"
  tar "${TAR_Z[@]}" --no-same-owner --no-same-permissions -xf "$archive" -C "$ROOT"
}

extract_split_gzip() {
  local prefix="$1"
  shift
  local bundle="$CACHE/$prefix.bundle.tgz"
  : > "$bundle"
  for part in "$@"; do
    cat "$CACHE/$part" >> "$bundle"
  done
  echo "[$(date -Is)] validating $bundle"
  tar "${TAR_Z[@]}" --no-same-owner --no-same-permissions -tf "$bundle" >/dev/null
  echo "[$(date -Is)] extracting $bundle"
  tar "${TAR_Z[@]}" --no-same-owner --no-same-permissions -xf "$bundle" -C "$ROOT"
}

# Russian speech was completed and validated separately before this resume.

for part in aa ab ac; do
  download_blob "Track1_Headset/vctk_wav48_silence_trimmed.tgz.part$part" "vctk_wav48_silence_trimmed.tgz.part$part"
done
extract_split_gzip "vctk_wav48_silence_trimmed.tgz" \
  vctk_wav48_silence_trimmed.tgz.partaa \
  vctk_wav48_silence_trimmed.tgz.partab \
  vctk_wav48_silence_trimmed.tgz.partac

for part in aa ab ac ad ae af ag ah ai aj ak al am an ao ap aq ar as at au; do
  download_blob "Track1_Headset/read_speech.tgz.part$part" "read_speech.tgz.part$part"
done
extract_split_gzip "read_speech.tgz" \
  read_speech.tgz.partaa read_speech.tgz.partab read_speech.tgz.partac \
  read_speech.tgz.partad read_speech.tgz.partae read_speech.tgz.partaf \
  read_speech.tgz.partag read_speech.tgz.partah read_speech.tgz.partai \
  read_speech.tgz.partaj read_speech.tgz.partak read_speech.tgz.partal \
  read_speech.tgz.partam read_speech.tgz.partan read_speech.tgz.partao \
  read_speech.tgz.partap read_speech.tgz.partaq read_speech.tgz.partar \
  read_speech.tgz.partas read_speech.tgz.partat read_speech.tgz.partau

echo "[$(date -Is)] AzCopy clean resume complete"
