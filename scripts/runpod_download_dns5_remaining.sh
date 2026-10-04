#!/usr/bin/env bash
set -Eeuo pipefail

AZCOPY="/workspace/tools/azcopy/azcopy"
BASE="https://dnschallengepublic.blob.core.windows.net/dns5archive/V5_training_dataset"
DEST="/workspace/dns5_archives/headset_remaining"
LOG="/workspace/vox_rescue_clean/logs/dns5_remaining.log"
MAX_PARALLEL="${MAX_PARALLEL:-4}"

mkdir -p "$DEST" "$(dirname "$LOG")"
exec > >(tee -a "$LOG") 2>&1
unset AZCOPY_CONCURRENCY_VALUE || true

BLOBS=(
  Track1_Headset/french_speech.tar.gz.partaa
  Track1_Headset/french_speech.tar.gz.partab
  Track1_Headset/french_speech.tar.gz.partac
  Track1_Headset/french_speech.tar.gz.partad
  Track1_Headset/french_speech.tar.gz.partae
  Track1_Headset/french_speech.tar.gz.partah

  Track1_Headset/german_speech.tgz.partaa
  Track1_Headset/german_speech.tgz.partab
  Track1_Headset/german_speech.tgz.partac
  Track1_Headset/german_speech.tgz.partad
  Track1_Headset/german_speech.tgz.partae
  Track1_Headset/german_speech.tgz.partaf
  Track1_Headset/german_speech.tgz.partag
  Track1_Headset/german_speech.tgz.partah
  Track1_Headset/german_speech.tgz.partaj
  Track1_Headset/german_speech.tgz.partal
  Track1_Headset/german_speech.tgz.partam
  Track1_Headset/german_speech.tgz.partan
  Track1_Headset/german_speech.tgz.partao
  Track1_Headset/german_speech.tgz.partap
  Track1_Headset/german_speech.tgz.partaq
  Track1_Headset/german_speech.tgz.partar
  Track1_Headset/german_speech.tgz.partas
  Track1_Headset/german_speech.tgz.partat
  Track1_Headset/german_speech.tgz.partau
  Track1_Headset/german_speech.tgz.partav
  Track1_Headset/german_speech.tgz.partaw

  Track1_Headset/italian_speech.tgz.partaa
  Track1_Headset/italian_speech.tgz.partab
  Track1_Headset/italian_speech.tgz.partac
  Track1_Headset/italian_speech.tgz.partad

  Track1_Headset/spanish_speech.tgz.partaa
  Track1_Headset/spanish_speech.tgz.partab
  Track1_Headset/spanish_speech.tgz.partac
  Track1_Headset/spanish_speech.tgz.partad
  Track1_Headset/spanish_speech.tgz.partae
  Track1_Headset/spanish_speech.tgz.partaf
  Track1_Headset/spanish_speech.tgz.partag
)

download_blob() {
  local blob="$1"
  local name="${blob##*/}"
  local target="$DEST/$name"
  local marker="$target.done"
  if [[ -s "$target" && -f "$marker" ]]; then
    echo "[$(date -Is)] already verified $name"
    return 0
  fi
  echo "[$(date -Is)] downloading $blob"
  "$AZCOPY" copy "$BASE/$blob" "$target" --overwrite=true --output-type=text
  touch "$marker"
  echo "[$(date -Is)] complete $name bytes=$(stat -c %s "$target")"
}

pids=()
for blob in "${BLOBS[@]}"; do
  download_blob "$blob" &
  pids+=("$!")
  if (( ${#pids[@]} >= MAX_PARALLEL )); then
    wait "${pids[0]}"
    pids=("${pids[@]:1}")
  fi
done
for pid in "${pids[@]}"; do
  wait "$pid"
done

echo "[$(date -Is)] DNS5 remaining headset downloads complete files=${#BLOBS[@]}"
