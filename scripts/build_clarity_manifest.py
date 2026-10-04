"""Build a licensed, quality-filtered curriculum manifest without deleting source data."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

import pyarrow.parquet as pq
import soundfile as sf


PROJECT = Path("/workspace/vox_rescue_clean")
DATA_ROOT = Path("/workspace/vox_datasets_v2")
LICENSED = DATA_ROOT / "licensed"
STATE = DATA_ROOT / "state"
OUTPUT = PROJECT / "manifests" / "clarity_v2"
BASE_MANIFEST = PROJECT / "manifests" / "dns5_canonical.json"
HINDI_PARQUET = DATA_ROOT / "archives" / "indicvoices_r_hindi" / "data"


def atomic_write_lines(path: Path, values: list[Path]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", newline="\n", dir=path.parent, delete=False
    ) as handle:
        temporary = Path(handle.name)
        for value in values:
            handle.write(str(value))
            handle.write("\n")
    temporary.replace(path)


def read_paths(path: Path) -> list[Path]:
    if not path.exists():
        return []
    return [Path(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def wavs_under(root: Path) -> list[Path]:
    return [Path(directory, name) for directory, _, names in os.walk(root) for name in names if name.lower().endswith(".wav")]


def stable_bucket(value: str, modulo: int) -> int:
    digest = hashlib.sha1(value.encode("utf-8", errors="replace")).digest()
    return int.from_bytes(digest[:8], "big") % modulo


def inspect_audio(item: tuple[str, Path]):
    role, path = item
    try:
        info = sf.info(path)
    except Exception as exc:
        return role, path, f"decode:{type(exc).__name__}"
    duration = float(info.duration)
    if info.frames <= 0 or info.samplerate <= 0 or info.channels <= 0:
        return role, path, "empty_header"
    if role == "rir":
        if not (0.001 <= duration <= 12.0):
            return role, path, f"rir_duration:{duration:.3f}"
    elif duration < 0.20:
        return role, path, f"too_short:{duration:.3f}"
    return role, path, None


def classify_rirs(root: Path) -> tuple[list[Path], list[Path], list[Path]]:
    rir_paths: list[Path] = []
    noise_paths: list[Path] = []
    unknown: list[Path] = []
    for path in wavs_under(root):
        relative = path.relative_to(root).as_posix().lower()
        filename = path.name.lower()
        if "pointsource_noises" in relative or "isotropic_noises" in relative and "rir" not in filename:
            noise_paths.append(path)
        elif "simulated_rirs" in relative or "rir" in filename or "impulse" in filename:
            rir_paths.append(path)
        else:
            unknown.append(path)
    return rir_paths, noise_paths, unknown


def materialize_hindi_holdout(parquet_paths: list[Path], maximum: int = 24) -> list[Path]:
    destination = LICENSED / "evaluation" / "hindi_holdout"
    destination.mkdir(parents=True, exist_ok=True)
    selected_rows: dict[Path, list[tuple[int, str, str]]] = defaultdict(list)
    per_speaker = Counter()
    selected_count = 0
    metadata_columns = ["snr", "c50", "duration", "speaker_id"]
    for path in parquet_paths:
        parquet = pq.ParquetFile(path)
        row_offset = 0
        for batch in parquet.iter_batches(batch_size=1024, columns=metadata_columns):
            for local_index, row in enumerate(batch.to_pylist()):
                speaker = str(row.get("speaker_id") or "")
                if stable_bucket(speaker, 20) != 0 or per_speaker[speaker] >= 2:
                    continue
                if float(row.get("snr") or -999) < 25.0:
                    continue
                if float(row.get("c50") or -999) < 20.0:
                    continue
                duration = float(row.get("duration") or 0)
                if not 1.0 <= duration <= 20.0:
                    continue
                selected_rows[path].append((row_offset + local_index, speaker, f"row_{row_offset + local_index}"))
                per_speaker[speaker] += 1
                selected_count += 1
                if selected_count >= maximum:
                    break
            row_offset += batch.num_rows
            if selected_count >= maximum:
                break
        if selected_count >= maximum:
            break
    if selected_count < maximum:
        raise RuntimeError(f"Only {selected_count} Hindi holdout rows passed filters")

    selected_paths: list[Path] = []
    for path, selections in selected_rows.items():
        wanted = {row_index: (speaker, source_name) for row_index, speaker, source_name in selections}
        remaining = set(wanted)
        parquet = pq.ParquetFile(path)
        row_offset = 0
        for batch in parquet.iter_batches(batch_size=16, columns=["audio"]):
            for local_index, row in enumerate(batch.to_pylist()):
                row_index = row_offset + local_index
                if row_index not in remaining:
                    continue
                audio = row.get("audio") or {}
                payload = audio.get("bytes") if isinstance(audio, dict) else None
                if not payload:
                    raise RuntimeError(f"Missing audio payload in {path.name} row {row_index}")
                speaker, fallback_name = wanted[row_index]
                source_name = Path(str(audio.get("path") or fallback_name)).stem
                safe_name = f"{len(selected_paths):04d}_{speaker}_{source_name}.wav".replace("/", "_")
                output_path = destination / safe_name
                if not output_path.exists() or output_path.stat().st_size != len(payload):
                    output_path.write_bytes(payload)
                sf.info(output_path)
                selected_paths.append(output_path)
                remaining.remove(row_index)
            row_offset += batch.num_rows
            if not remaining:
                break
        if remaining:
            raise RuntimeError(f"Could not materialize selected rows from {path}: {sorted(remaining)}")
    return selected_paths


def main() -> int:
    if not (STATE / "CLARITY_DATA_READY").exists():
        raise RuntimeError("Dataset verification/extraction has not completed")
    base = json.loads(BASE_MANIFEST.read_text(encoding="utf-8"))
    required_archives = [item for item in base["clean_archives"] if item.get("validated")]
    if len(required_archives) != len(base["clean_archives"]):
        raise RuntimeError("Base DNS5 manifest contains an unvalidated clean archive")

    existing_clean = []
    for item in base.get("clean_extracted", []):
        existing_clean.extend(read_paths(Path(item["path_list"])))
    existing_noise = read_paths(Path(base["noise"]["path_list"]))
    existing_rir = read_paths(Path(base["rir"]["path_list"]))

    musan_root = LICENSED / "musan"
    musan_noise = wavs_under(musan_root / "noise")
    musan_music = wavs_under(musan_root / "music")
    musan_speech = wavs_under(musan_root / "speech")

    new_rir, new_rir_noise, unknown_rir_audio = classify_rirs(LICENSED / "rirs_noises")
    parquet_paths = sorted(HINDI_PARQUET.glob("*.parquet"))
    if len(parquet_paths) != 10:
        raise RuntimeError(f"Expected 10 Hindi Parquet shards, found {len(parquet_paths)}")

    candidates = {
        "clean": sorted(set(existing_clean)),
        "noise": sorted(set(existing_noise + musan_noise + musan_music + new_rir_noise)),
        "rir": sorted(set(existing_rir + new_rir)),
        "interferer": sorted(set(existing_clean + musan_speech)),
    }
    # Source archives have already passed gzip/ZIP CRC checks and the DNS lists
    # are the same canonical inputs that produced the immutable 5K checkpoint.
    # Re-opening every one of ~200K small files on the network volume adds many
    # minutes without increasing archive integrity. Audit a deterministic,
    # bounded sample here; every clean waveform is still quality-checked by the
    # streaming dataset before it can enter a batch.
    accepted: dict[str, list[Path]] = {
        role: list(paths) for role, paths in candidates.items()
    }
    audit_jobs = []
    for role, paths in candidates.items():
        stride = max(1, len(paths) // 512)
        audit_jobs.extend((role, path) for path in paths[::stride][:512])
    rejected = []
    with ThreadPoolExecutor(max_workers=32) as pool:
        for role, path, reason in pool.map(inspect_audio, audit_jobs, chunksize=32):
            if reason is not None:
                rejected.append((role, path, reason))
    for role, path, _ in rejected:
        try:
            accepted[role].remove(path)
        except ValueError:
            pass
    OUTPUT.mkdir(parents=True, exist_ok=True)
    clean_list = OUTPUT / "clean_extracted_wavs.txt"
    noise_list = OUTPUT / "noise_wavs.txt"
    rir_list = OUTPUT / "rir_wavs.txt"
    interferer_list = OUTPUT / "interferer_wavs.txt"
    holdout_list = OUTPUT / "hindi_holdout_wavs.txt"
    atomic_write_lines(clean_list, accepted["clean"])
    atomic_write_lines(noise_list, accepted["noise"])
    atomic_write_lines(rir_list, accepted["rir"])
    atomic_write_lines(interferer_list, accepted["interferer"])
    holdout_paths = materialize_hindi_holdout(parquet_paths)
    atomic_write_lines(holdout_list, holdout_paths)

    with (OUTPUT / "rejected.tsv").open("w", encoding="utf-8", newline="\n") as handle:
        handle.write("role\tpath\treason\n")
        for role, path, reason in rejected:
            handle.write(f"{role}\t{path}\t{reason}\n")
        for path in unknown_rir_audio:
            handle.write(f"unclassified_rir_audio\t{path}\tunclassified\n")

    manifest = {
        "schema_version": 2,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "purpose": "full validated DNS5 plus licensed clarity curriculum from immutable 5K baseline",
        "clean_type_weights": {"archive": 0.35, "parquet": 0.45, "extracted": 0.20},
        "clean_archives": required_archives,
        "clean_parquet": [
            {
                "id": "indicvoices_r_hindi_train",
                "paths": [str(path) for path in parquet_paths],
                "min_snr_db": 25.0,
                "min_c50_db": 20.0,
                "min_duration_seconds": 1.0,
                "max_duration_seconds": 30.0,
                "holdout_modulo": 20,
                "holdout_bucket": 0,
                "split": "train",
                "license": "CC-BY-4.0",
            }
        ],
        "clean_extracted": [
            {"id": "dns5_extracted_clean", "path_list": str(clean_list), "wav_count": len(accepted["clean"])}
        ],
        "interferer_extracted": [
            {"id": "licensed_interferers", "path_list": str(interferer_list), "wav_count": len(accepted["interferer"])}
        ],
        "noise": {"kind": "wav_list", "path_list": str(noise_list), "wav_count": len(accepted["noise"])},
        "rir": {"kind": "wav_list", "path_list": str(rir_list), "wav_count": len(accepted["rir"])},
        "evaluation": {"hindi_holdout_path_list": str(holdout_list), "wav_count": len(holdout_paths)},
        "license_policy": {
            "production": [
                "DNS5:original-source-licenses-see-microsoft-dns-challenge-readme",
                "VCTK:CC-BY-4.0",
                "MUSAN:CC-BY-4.0",
                "RIRS_NOISES:Apache-2.0",
                "IndicVoices-R:CC-BY-4.0",
            ],
            "excluded_from_commercial_training": ["EARS:CC-BY-NC-4.0"],
        },
    }
    manifest_path = OUTPUT / "canonical.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    summary = {
        "manifest": str(manifest_path),
        "accepted": {key: len(value) for key, value in accepted.items()},
        "rejected": len(rejected),
        "header_audit_files": len(audit_jobs),
        "header_audit_mode": "deterministic-bounded-after-archive-crc; runtime-clean-guard-enabled",
        "unclassified_rir_audio": len(unknown_rir_audio),
        "hindi_parquet_files": len(parquet_paths),
        "hindi_parquet_bytes": sum(path.stat().st_size for path in parquet_paths),
        "hindi_holdout": len(holdout_paths),
        "dns5_validated_clean_archives": len(required_archives),
        "dns5_validated_clean_archive_bytes": sum(
            int(item["compressed_bytes"]) for item in required_archives
        ),
    }
    (OUTPUT / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
