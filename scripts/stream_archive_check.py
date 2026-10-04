"""Validate that WAV samples can be streamed directly from a .tar.gz archive."""

from __future__ import annotations

import argparse
import io
import subprocess
import tarfile
from pathlib import Path

import soundfile as sf


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument("--rapidgzip", type=Path, required=True)
    parser.add_argument("--samples", type=int, default=32)
    args = parser.parse_args()

    command = [str(args.rapidgzip), "-d", "-c", "-P", "0", str(args.archive)]
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if process.stdout is None:
        raise RuntimeError("rapidgzip stdout pipe was not created")

    checked = 0
    total_frames = 0
    try:
        with tarfile.open(fileobj=process.stdout, mode="r|") as archive:
            for member in archive:
                if not member.isfile() or not member.name.lower().endswith(".wav"):
                    continue
                extracted = archive.extractfile(member)
                if extracted is None:
                    raise RuntimeError(f"Could not stream {member.name}")
                payload = extracted.read()
                info = sf.info(io.BytesIO(payload))
                if info.frames <= 0 or info.samplerate <= 0 or info.channels <= 0:
                    raise RuntimeError(f"Invalid WAV metadata for {member.name}")
                total_frames += int(info.frames)
                checked += 1
                if checked >= args.samples:
                    break
    finally:
        process.stdout.close()
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=10)

    if checked != args.samples:
        stderr = process.stderr.read().decode("utf-8", errors="replace") if process.stderr else ""
        raise SystemExit(f"Only streamed {checked}/{args.samples} WAVs. {stderr}")
    print(f"STREAM_CHECK_OK samples={checked} total_frames={total_frames}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
