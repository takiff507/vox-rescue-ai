"""Build a small, auditable audio manifest without downloading anything."""

from __future__ import annotations

import argparse
import csv
import hashlib
import wave
from pathlib import Path


FIELDS = [
    "path",
    "relative_path",
    "format",
    "sample_rate",
    "channels",
    "sample_width_bytes",
    "num_frames",
    "duration_seconds",
    "sha256",
    "status",
    "error",
]


def _sha256(path: Path, block_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(block_size), b""):
            digest.update(block)
    return digest.hexdigest()


def inspect_wav(path: Path, root: Path) -> dict[str, str]:
    row = {
        "path": str(path.resolve()),
        "relative_path": str(path.relative_to(root)),
        "format": path.suffix.lower().lstrip("."),
        "sample_rate": "",
        "channels": "",
        "sample_width_bytes": "",
        "num_frames": "",
        "duration_seconds": "",
        "sha256": "",
        "status": "ok",
        "error": "",
    }
    try:
        with wave.open(str(path), "rb") as audio:
            frames = audio.getnframes()
            rate = audio.getframerate()
            row.update(
                sample_rate=str(rate),
                channels=str(audio.getnchannels()),
                sample_width_bytes=str(audio.getsampwidth()),
                num_frames=str(frames),
                duration_seconds=f"{frames / rate:.6f}" if rate else "0",
                sha256=_sha256(path),
            )
            if rate <= 0 or frames <= 0:
                row["status"] = "invalid"
                row["error"] = "empty or invalid WAV metadata"
    except (wave.Error, OSError, ValueError) as exc:
        row["status"] = "unreadable"
        row["error"] = str(exc)
    return row


def build_manifest(root: Path, output: Path) -> tuple[int, int]:
    root = root.resolve()
    output = output.resolve()
    root.mkdir(parents=True, exist_ok=True)
    output.parent.mkdir(parents=True, exist_ok=True)

    files = sorted(path for path in root.rglob("*") if path.is_file())
    supported = [path for path in files if path.suffix.lower() == ".wav"]
    unsupported = [path for path in files if path.suffix.lower() != ".wav"]

    rows = [inspect_wav(path, root) for path in supported]
    for path in unsupported:
        rows.append(
            {
                "path": str(path.resolve()),
                "relative_path": str(path.relative_to(root)),
                "format": path.suffix.lower().lstrip(".") or "unknown",
                "sample_rate": "",
                "channels": "",
                "sample_width_bytes": "",
                "num_frames": "",
                "duration_seconds": "",
                "sha256": "",
                "status": "unsupported_format",
                "error": "only WAV is inspected by the stdlib-only setup",
            }
        )

    with output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)

    valid = sum(row["status"] == "ok" for row in rows)
    return len(rows), valid


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("data"))
    parser.add_argument("--output", type=Path, default=Path("manifests/audio_manifest.csv"))
    args = parser.parse_args()
    total, valid = build_manifest(args.root, args.output)
    print(f"Manifest: {args.output.resolve()}")
    print(f"Files inspected: {total}; valid WAV files: {valid}")
    print("No downloads performed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

