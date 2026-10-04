#!/usr/bin/env bash
set -Eeuo pipefail

AZCOPY="/workspace/tools/azcopy/azcopy"
BASE="https://dns4public.blob.core.windows.net/dns4archive/datasets_fullband"
SOURCE_SCRIPT="/workspace/dns-challenge/download-dns-challenge-5-speakerphone-training.sh"
DEST="/workspace/dns5_archives/german_track2_identical"
LOG="/workspace/vox_rescue_clean/logs/german_fallback.log"
MAX_PARALLEL="${MAX_PARALLEL:-4}"

# Match validation workers to the container's effective CPU quota. `nproc` can
# report the host/cpuset count even when RunPod applies a smaller cgroup quota.
CPU_MAX_FILE="/sys/fs/cgroup/cpu.max"
if [[ -r "$CPU_MAX_FILE" ]]; then
  read -r CPU_QUOTA CPU_PERIOD < "$CPU_MAX_FILE"
else
  CPU_QUOTA="max"
  CPU_PERIOD="100000"
fi
if [[ "$CPU_QUOTA" == "max" ]]; then
  EFFECTIVE_CPUS="$(nproc)"
else
  EFFECTIVE_CPUS="$(( (CPU_QUOTA + CPU_PERIOD - 1) / CPU_PERIOD ))"
fi
VALIDATE_PARALLEL="${VALIDATE_PARALLEL:-$EFFECTIVE_CPUS}"

mkdir -p "$DEST" "$(dirname "$LOG")"
exec > >(tee -a "$LOG") 2>&1
unset AZCOPY_CONCURRENCY_VALUE || true

mapfile -t BLOBS < <(
  sed -n '/BLOB_NAMES=(/,/^)/p' "$SOURCE_SCRIPT" |
    awk '/clean_fullband.*german_speech.*tar\.bz2/ {print $1}'
)
[[ ${#BLOBS[@]} -eq 43 ]] || {
  echo "Expected 43 official German shards, found ${#BLOBS[@]}"
  exit 1
}

download_one() {
  local blob="$1"
  local name="${blob##*/}"
  local target="$DEST/$name"
  if [[ -s "$target" && -f "$target.done" ]]; then
    echo "[$(date -Is)] already complete $name"
    return 0
  fi
  echo "[$(date -Is)] downloading $blob"
  "$AZCOPY" copy "$BASE/$blob" "$target" --overwrite=true --output-type=text
  touch "$target.done"
  echo "[$(date -Is)] complete $name bytes=$(stat -c %s "$target")"
}

pids=()
for blob in "${BLOBS[@]}"; do
  download_one "$blob" &
  pids+=("$!")
  if (( ${#pids[@]} >= MAX_PARALLEL )); then
    wait "${pids[0]}"
    pids=("${pids[@]:1}")
  fi
done
for pid in "${pids[@]}"; do
  wait "$pid"
done

echo "[$(date -Is)] validating German fallback shards"
pids=()
for blob in "${BLOBS[@]}"; do
  bzip2 -t "$DEST/${blob##*/}" &
  pids+=("$!")
  if (( ${#pids[@]} >= VALIDATE_PARALLEL )); then
    wait "${pids[0]}"
    pids=("${pids[@]:1}")
  fi
done
for pid in "${pids[@]}"; do
  wait "$pid"
done
echo "[$(date -Is)] GERMAN_FALLBACK_VALIDATION_OK files=${#BLOBS[@]}"
