#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="/workspace/dns5_archives/headset_remaining"
LOG="/workspace/vox_rescue_clean/logs/dns5_remaining_validate.log"

mkdir -p "$(dirname "$LOG")"
exec > >(tee -a "$LOG") 2>&1

validate_group() {
  local name="$1"
  shift
  local parts=("$@")
  echo "[$(date -Is)] validating $name parts=${#parts[@]}"
  for part in "${parts[@]}"; do
    [[ -s "$part" ]] || { echo "missing or empty: $part"; return 1; }
    [[ -f "$part.done" ]] || { echo "missing completion marker: $part.done"; return 1; }
  done
  cat "${parts[@]}" | gzip -t
  echo "[$(date -Is)] VALIDATION_OK $name"
}

validate_group french \
  "$ROOT/french_speech.tar.gz.partaa" "$ROOT/french_speech.tar.gz.partab" \
  "$ROOT/french_speech.tar.gz.partac" "$ROOT/french_speech.tar.gz.partad" \
  "$ROOT/french_speech.tar.gz.partae" "$ROOT/french_speech.tar.gz.partah" &
pid_french=$!

validate_group german \
  "$ROOT/german_speech.tgz.partaa" "$ROOT/german_speech.tgz.partab" \
  "$ROOT/german_speech.tgz.partac" "$ROOT/german_speech.tgz.partad" \
  "$ROOT/german_speech.tgz.partae" "$ROOT/german_speech.tgz.partaf" \
  "$ROOT/german_speech.tgz.partag" "$ROOT/german_speech.tgz.partah" \
  "$ROOT/german_speech.tgz.partaj" "$ROOT/german_speech.tgz.partal" \
  "$ROOT/german_speech.tgz.partam" "$ROOT/german_speech.tgz.partan" \
  "$ROOT/german_speech.tgz.partao" "$ROOT/german_speech.tgz.partap" \
  "$ROOT/german_speech.tgz.partaq" "$ROOT/german_speech.tgz.partar" \
  "$ROOT/german_speech.tgz.partas" "$ROOT/german_speech.tgz.partat" \
  "$ROOT/german_speech.tgz.partau" "$ROOT/german_speech.tgz.partav" \
  "$ROOT/german_speech.tgz.partaw" &
pid_german=$!

validate_group italian \
  "$ROOT/italian_speech.tgz.partaa" "$ROOT/italian_speech.tgz.partab" \
  "$ROOT/italian_speech.tgz.partac" "$ROOT/italian_speech.tgz.partad" &
pid_italian=$!

validate_group spanish \
  "$ROOT/spanish_speech.tgz.partaa" "$ROOT/spanish_speech.tgz.partab" \
  "$ROOT/spanish_speech.tgz.partac" "$ROOT/spanish_speech.tgz.partad" \
  "$ROOT/spanish_speech.tgz.partae" "$ROOT/spanish_speech.tgz.partaf" \
  "$ROOT/spanish_speech.tgz.partag" &
pid_spanish=$!

wait "$pid_french"
wait "$pid_german"
wait "$pid_italian"
wait "$pid_spanish"
echo "[$(date -Is)] DNS5 remaining validation complete"
