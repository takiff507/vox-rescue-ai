"""Build reusable WAV path lists with one fast filesystem walk."""

from __future__ import annotations

import argparse
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path


def iter_wavs(root: Path):
    for directory, _, filenames in os.walk(root):
        for filename in filenames:
            if filename.lower().endswith(".wav"):
                yield str(Path(directory, filename))


def write_list(root: Path, output: Path) -> int:
    output.parent.mkdir(parents=True, exist_ok=True)
    count = 0
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
        for path in iter_wavs(root):
            handle.write(path)
            handle.write("\n")
            count += 1
    temporary.replace(output)
    return count


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--clean-root", type=Path, required=True)
    parser.add_argument("--noise-root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    clean_output = args.output_dir / "clean_wavs.txt"
    noise_output = args.output_dir / "noise_wavs.txt"
    clean_count = write_list(args.clean_root, clean_output)
    noise_count = write_list(args.noise_root, noise_output)
    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "clean_root": str(args.clean_root.resolve()),
        "noise_root": str(args.noise_root.resolve()),
        "clean_count": clean_count,
        "noise_count": noise_count,
        "clean_list": str(clean_output.resolve()),
        "noise_list": str(noise_output.resolve()),
    }
    summary_output = args.output_dir / "source_lists.json"
    summary_output.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
