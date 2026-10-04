#!/usr/bin/env bash
set -Eeuo pipefail

AZCOPY="/workspace/tools/azcopy/azcopy"
BASE="https://dnschallengepublic.blob.core.windows.net/dns5archive/V5_training_dataset"
ROOT="/workspace/datasets_fullband"
CACHE="/workspace/azcopy_cache"
LOG="/workspace/vox_rescue_clean/logs/read_resume.log"
PIGZ_THREADS="${PIGZ_THREADS:-$(nproc)}"

mkdir -p "$ROOT" "$CACHE" "$(dirname "$LOG")"
exec > >(tee -a "$LOG") 2>&1
# Let AzCopy auto-tune transfer concurrency for the host and route.
unset AZCOPY_CONCURRENCY_VALUE || true
TAR_Z=(--use-compress-program="pigz -p ${PIGZ_THREADS}")

for part in aa ab ac ad ae af ag ah ai aj ak al am an ao ap aq ar as at au; do
  name="read_speech.tgz.part$part"
  if [ -s "$CACHE/$name" ]; then
    echo "[$(date -Is)] cache exists $name"
  else
    echo "[$(date -Is)] azcopy Track1_Headset/$name"
    "$AZCOPY" copy "$BASE/Track1_Headset/$name" "$CACHE/$name" \
      --overwrite=true --output-type=text
  fi
done

BUNDLE="$CACHE/read_speech.tgz.bundle.tgz"
: > "$BUNDLE"
for part in aa ab ac ad ae af ag ah ai aj ak al am an ao ap aq ar as at au; do
  cat "$CACHE/read_speech.tgz.part$part" >> "$BUNDLE"
done

echo "[$(date -Is)] validating $BUNDLE"
tar "${TAR_Z[@]}" --no-same-owner --no-same-permissions -tf "$BUNDLE" >/dev/null
echo "[$(date -Is)] extracting $BUNDLE with pigz threads=$PIGZ_THREADS"
tar "${TAR_Z[@]}" --no-same-owner --no-same-permissions -xf "$BUNDLE" -C "$ROOT"
echo "[$(date -Is)] read-speech resume complete"
