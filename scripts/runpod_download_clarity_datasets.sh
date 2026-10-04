#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="/workspace/vox_datasets_v2"
ARCHIVES="$ROOT/archives"
LICENSED="$ROOT/licensed"
RESEARCH_ONLY="$ROOT/research_only"
STATE="$ROOT/state"
LOGS="/workspace/vox_rescue_clean/logs"
MAX_WORKSPACE_BYTES=1750000000000

mkdir -p \
  "$ARCHIVES/musan" \
  "$ARCHIVES/rirs_noises" \
  "$ARCHIVES/indicvoices_r_hindi" \
  "$ARCHIVES/ears_nc" \
  "$LICENSED" \
  "$RESEARCH_ONLY" \
  "$STATE" \
  "$LOGS"

used_bytes="$(du -sb /workspace | awk '{print $1}')"
if (( used_bytes >= MAX_WORKSPACE_BYTES )); then
  echo "SPACE_GUARD_FAIL used_bytes=$used_bytes limit=$MAX_WORKSPACE_BYTES" >&2
  exit 20
fi

if ! command -v aria2c >/dev/null 2>&1; then
  echo "aria2c is required" >&2
  exit 21
fi
if ! command -v jq >/dev/null 2>&1; then
  echo "jq is required" >&2
  exit 22
fi

cat > "$ROOT/LICENSE_POLICY.txt" <<'EOF'
Production-training candidates:
- VCTK 0.92: CC BY 4.0 (already present in the validated DNS5 archive set)
- MUSAN: CC BY 4.0
- RIRS_NOISES / SLR28: Apache 2.0
- IndicVoices-R: CC BY 4.0 according to the official AI4Bharat repository

Research/evaluation only:
- EARS: CC BY-NC 4.0. Never add EARS paths to a commercial training manifest.

Source datasets are immutable. Generated manifests and extracted copies live in
separate directories. Attribution records must ship with any commercial release.
EOF

input_file="$STATE/clarity_downloads.aria2.txt"
: > "$input_file"

add_download() {
  local url="$1"
  local directory="$2"
  local output="$3"
  printf '%s\n dir=%s\n out=%s\n' "$url" "$directory" "$output" >> "$input_file"
}

add_download \
  "https://openslr.trmal.net/resources/17/musan.tar.gz" \
  "$ARCHIVES/musan" \
  "musan.tar.gz"

add_download \
  "https://www.openslr.org/resources/28/rirs_noises.zip" \
  "$ARCHIVES/rirs_noises" \
  "rirs_noises.zip"

hindi_tree="$STATE/indicvoices_r_hindi_tree.json"
curl --fail --location --retry 8 --retry-all-errors --retry-delay 3 \
  --output "$hindi_tree.tmp" \
  "https://huggingface.co/api/datasets/ai4bharat/indicvoices_r/tree/main/Hindi?recursive=true&expand=false&limit=1000"
mv "$hindi_tree.tmp" "$hindi_tree"

mapfile -t hindi_paths < <(jq -r '.[] | select(.type == "file" and (.path | endswith(".parquet"))) | .path' "$hindi_tree")
if (( ${#hindi_paths[@]} != 101 )); then
  echo "INDIC_TREE_FAIL expected=101 actual=${#hindi_paths[@]}" >&2
  exit 23
fi
for path in "${hindi_paths[@]}"; do
  filename="${path##*/}"
  add_download \
    "https://huggingface.co/datasets/ai4bharat/indicvoices_r/resolve/main/$path?download=true" \
    "$ARCHIVES/indicvoices_r_hindi" \
    "$filename"
done

for speaker in $(seq -w 1 107); do
  add_download \
    "https://github.com/facebookresearch/ears_dataset/releases/download/dataset/p${speaker}.zip" \
    "$ARCHIVES/ears_nc" \
    "p${speaker}.zip"
done

echo "DOWNLOAD_PLAN files=$((2 + ${#hindi_paths[@]} + 107)) used_bytes=$used_bytes"

aria2c \
  --input-file="$input_file" \
  --continue=true \
  --max-concurrent-downloads=16 \
  --split=4 \
  --max-connection-per-server=4 \
  --min-split-size=8M \
  --file-allocation=none \
  --auto-file-renaming=false \
  --allow-overwrite=false \
  --max-tries=0 \
  --retry-wait=5 \
  --connect-timeout=20 \
  --timeout=60 \
  --summary-interval=30 \
  --console-log-level=notice \
  --download-result=full \
  --human-readable=true

gzip -t "$ARCHIVES/musan/musan.tar.gz"
unzip -tq "$ARCHIVES/rirs_noises/rirs_noises.zip"

expected_hindi_bytes="$(jq '[.[] | select(.type == "file" and (.path | endswith(".parquet"))) | .size] | add' "$hindi_tree")"
actual_hindi_bytes="$(find "$ARCHIVES/indicvoices_r_hindi" -maxdepth 1 -type f -name '*.parquet' -printf '%s\n' | awk '{sum += $1} END {print sum + 0}')"
if [[ "$actual_hindi_bytes" != "$expected_hindi_bytes" ]]; then
  echo "INDIC_SIZE_FAIL expected=$expected_hindi_bytes actual=$actual_hindi_bytes" >&2
  exit 24
fi

find "$ARCHIVES/ears_nc" -maxdepth 1 -type f -name 'p*.zip' -print0 \
  | xargs -0 -r -n 1 -P 16 unzip -tq

sha256sum \
  "$ARCHIVES/musan/musan.tar.gz" \
  "$ARCHIVES/rirs_noises/rirs_noises.zip" \
  > "$STATE/core_archives.sha256"

date -u +%Y-%m-%dT%H:%M:%SZ > "$STATE/DOWNLOADS_VERIFIED"
echo "CLARITY_DOWNLOADS_OK hindi_files=${#hindi_paths[@]} hindi_bytes=$actual_hindi_bytes"
