"""Build a strict, deduplicated manifest for the DNS5 training sources."""

from __future__ import annotations

import argparse
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(message)


def require_validated(log: Path, marker: str) -> None:
    require(log.is_file(), f"Missing validation log: {log}")
    require(marker in log.read_text(encoding="utf-8", errors="replace"), f"Missing marker: {marker}")


def require_done(paths: list[Path]) -> None:
    for path in paths:
        require(path.is_file() and path.stat().st_size > 0, f"Missing/empty archive: {path}")
        require(Path(f"{path}.done").is_file(), f"Missing completion marker: {path}.done")


def archive_entry(source_id: str, kind: str, paths: list[Path], **metadata):
    return {
        "id": source_id,
        "kind": kind,
        "paths": [str(path) for path in paths],
        "compressed_bytes": sum(path.stat().st_size for path in paths),
        **metadata,
    }


def write_wav_list(root: Path, output: Path) -> int:
    count = 0
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        newline="\n",
        dir=output.parent,
        prefix=f".{output.name}.",
        suffix=".tmp",
        delete=False,
    ) as handle:
        temporary = Path(handle.name)
        for directory, _, filenames in os.walk(root):
            for filename in filenames:
                if filename.lower().endswith(".wav"):
                    handle.write(str(Path(directory, filename)))
                    handle.write("\n")
                    count += 1
    temporary.replace(output)
    require(count > 0, f"No WAV files found under {root}")
    return count


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, default=Path("/workspace"))
    parser.add_argument(
        "--output", type=Path, default=Path("/workspace/vox_rescue_clean/manifests/dns5_canonical.json")
    )
    args = parser.parse_args()
    workspace = args.workspace
    project = workspace / "vox_rescue_clean"
    archives = workspace / "dns5_archives"
    cache = workspace / "azcopy_cache"
    logs = project / "logs"

    french = sorted((archives / "french_track2_identical").glob("*.tar.bz2"))
    german = sorted((archives / "german_track2_identical").glob("*.tar.bz2"))
    require(len(french) == 9, f"Expected 9 French shards, found {len(french)}")
    require(len(german) == 43, f"Expected 43 German shards, found {len(german)}")
    require_done(french + german)
    require_validated(logs / "french_fallback.log", "FRENCH_FALLBACK_VALIDATION_OK files=9")
    require_validated(logs / "german_fallback.log", "GERMAN_FALLBACK_VALIDATION_OK files=43")

    remaining = archives / "headset_remaining"
    italian = sorted(
        path for path in remaining.glob("italian_speech.tgz.part*") if not path.name.endswith(".done")
    )
    spanish = sorted(
        path for path in remaining.glob("spanish_speech.tgz.part*") if not path.name.endswith(".done")
    )
    require(len(italian) == 4, f"Expected 4 Italian parts, found {len(italian)}")
    require(len(spanish) == 7, f"Expected 7 Spanish parts, found {len(spanish)}")
    require_done(italian + spanish)
    require_validated(logs / "dns5_remaining_validate.log", "VALIDATION_OK italian")
    require_validated(logs / "dns5_remaining_validate.log", "VALIDATION_OK spanish")

    read_bundle = cache / "read_speech.tgz.bundle.tgz"
    vctk_bundle = cache / "vctk_wav48_silence_trimmed.tgz.bundle.tgz"
    expected_sizes = {
        read_bundle: 109_325_901_974,
        vctk_bundle: 14_262_902_989,
    }
    for path, expected in expected_sizes.items():
        require(path.is_file(), f"Missing bundle: {path}")
        require(path.stat().st_size == expected, f"Unexpected bundle size: {path}")

    clean_root = workspace / "datasets_fullband/mnt/dnsv5/clean"
    extracted_roots = {
        "russian": clean_root / "russian_speech",
        "emotional": clean_root / "emotional_speech",
        "vocalset": clean_root / "VocalSet_48kHz_mono",
    }
    lists_dir = args.output.parent / "dns5_lists"
    extracted = []
    for source_id, root in extracted_roots.items():
        path_list = lists_dir / f"{source_id}_wavs.txt"
        count = write_wav_list(root, path_list)
        extracted.append(
            {"id": source_id, "kind": "wav_list", "path_list": str(path_list), "wav_count": count}
        )

    noise_root = workspace / "datasets_fullband/datasets_fullband/noise_fullband"
    rir_root = workspace / "datasets_fullband/datasets_fullband/impulse_responses"
    noise_list = lists_dir / "noise_wavs.txt"
    rir_list = lists_dir / "rir_wavs.txt"
    noise_count = write_wav_list(noise_root, noise_list)
    rir_count = write_wav_list(rir_root, rir_list)

    clean_archives = [
        archive_entry("read_speech", "tar_gzip", [read_bundle], validated=True),
        archive_entry("vctk", "tar_gzip", [vctk_bundle], validated=True),
        archive_entry("italian", "split_tar_gzip", italian, validated=True),
        archive_entry("spanish", "split_tar_gzip", spanish, validated=True),
    ]
    clean_archives.extend(
        archive_entry(f"french_{index:03d}", "tar_bzip2", [path], language="fr", validated=True)
        for index, path in enumerate(french)
    )
    clean_archives.extend(
        archive_entry(f"german_{index:03d}", "tar_bzip2", [path], language="de", validated=True)
        for index, path in enumerate(german)
    )

    manifest = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "clean_archives": clean_archives,
        "clean_extracted": extracted,
        "noise": {"kind": "wav_list", "path_list": str(noise_list), "wav_count": noise_count},
        "rir": {"kind": "wav_list", "path_list": str(rir_list), "wav_count": rir_count},
        "excluded": [
            "headset_remaining/french_speech.tar.gz.part* (official list is incomplete)",
            "headset_remaining/german_speech.tgz.part* (official list is incomplete)",
            "azcopy_cache/*.part* (duplicates of validated bundles)",
            "partially extracted read/VCTK trees (duplicates of validated bundles)",
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_suffix(args.output.suffix + ".tmp")
    temporary.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    temporary.replace(args.output)
    print(
        json.dumps(
            {
                "manifest": str(args.output),
                "archive_sources": len(clean_archives),
                "archive_bytes": sum(item["compressed_bytes"] for item in clean_archives),
                "extracted_clean_wavs": sum(item["wav_count"] for item in extracted),
                "noise_wavs": noise_count,
                "rir_wavs": rir_count,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
