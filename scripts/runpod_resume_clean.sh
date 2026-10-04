#!/usr/bin/env bash
set -Eeuo pipefail

# Resume point after the completed noise and impulse-response archives.
# The archive type is selected from its suffix: .tgz is gzip, .tar.bz2 is bzip2.
BASE="https://dnschallengepublic.blob.core.windows.net/dns5archive/V5_training_dataset"
ROOT="/workspace/datasets_fullband"
LOG="/workspace/vox_rescue_clean/logs/dns_download.log"

mkdir -p "$ROOT" "$(dirname "$LOG")"
exec > >(tee -a "$LOG") 2>&1

download_archive() {
  local remote="$1"
  local destination="$2"
  local tar_flag
  case "$remote" in
    *.tar.bz2) tar_flag="-xj" ;;
    *.tgz|*.tar.gz) tar_flag="-xz" ;;
    *) echo "Unsupported archive format: $remote" >&2; return 2 ;;
  esac
  mkdir -p "$ROOT/$destination"
  echo "[$(date -Is)] extracting $remote"
  curl --fail --location --retry 5 --retry-delay 5 "$BASE/$remote" | tar --no-same-owner --no-same-permissions -C "$ROOT/$destination" "$tar_flag"
}

download_split_gzip() {
  local destination="$1"
  shift
  mkdir -p "$ROOT/$destination"
  echo "[$(date -Is)] extracting split archive into $destination"
  for remote in "$@"; do
    echo "[$(date -Is)] streaming $remote"
    curl --fail --location --retry 5 --retry-delay 5 "$BASE/$remote"
  done | tar --no-same-owner --no-same-permissions -C "$ROOT/$destination" -xz
}

download_archive "Track1_Headset/VocalSet_48kHz_mono.tgz" "."
download_archive "Track1_Headset/emotional_speech.tgz" "."
download_archive "Track1_Headset/russian_speech.tgz" "."

download_split_gzip "datasets_fullband/clean_fullband" \
  Track1_Headset/vctk_wav48_silence_trimmed.tgz.partaa \
  Track1_Headset/vctk_wav48_silence_trimmed.tgz.partab \
  Track1_Headset/vctk_wav48_silence_trimmed.tgz.partac

download_split_gzip "datasets_fullband/clean_fullband" \
  Track1_Headset/read_speech.tgz.partaa \
  Track1_Headset/read_speech.tgz.partab \
  Track1_Headset/read_speech.tgz.partac \
  Track1_Headset/read_speech.tgz.partad \
  Track1_Headset/read_speech.tgz.partae \
  Track1_Headset/read_speech.tgz.partaf \
  Track1_Headset/read_speech.tgz.partag \
  Track1_Headset/read_speech.tgz.partah \
  Track1_Headset/read_speech.tgz.partai \
  Track1_Headset/read_speech.tgz.partaj \
  Track1_Headset/read_speech.tgz.partak \
  Track1_Headset/read_speech.tgz.partal \
  Track1_Headset/read_speech.tgz.partam \
  Track1_Headset/read_speech.tgz.partan \
  Track1_Headset/read_speech.tgz.partao \
  Track1_Headset/read_speech.tgz.partap \
  Track1_Headset/read_speech.tgz.partaq \
  Track1_Headset/read_speech.tgz.partar \
  Track1_Headset/read_speech.tgz.partas \
  Track1_Headset/read_speech.tgz.partat \
  Track1_Headset/read_speech.tgz.partau

echo "[$(date -Is)] clean speech resume complete"
