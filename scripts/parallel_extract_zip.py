"""Safely resume ZIP extraction with bounded parallelism and atomic files."""

from __future__ import annotations

import argparse
import binascii
import json
import os
import shutil
import threading
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--destination", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=16)
    parser.add_argument("--ready-marker", type=Path, required=True)
    args = parser.parse_args()

    archive = args.archive.resolve(strict=True)
    destination = args.destination.resolve()
    destination.mkdir(parents=True, exist_ok=True)
    workers = max(1, min(args.workers, 32))
    with zipfile.ZipFile(archive) as handle:
        entries = [item for item in handle.infolist() if not item.is_dir()]

    counters = {"complete": 0, "extracted": 0, "skipped": 0, "bytes": 0}
    lock = threading.Lock()
    thread_state = threading.local()
    started = time.monotonic()

    def thread_archive() -> zipfile.ZipFile:
        handle = getattr(thread_state, "archive", None)
        if handle is None:
            handle = zipfile.ZipFile(archive)
            thread_state.archive = handle
        return handle

    def extract(item: zipfile.ZipInfo) -> None:
        target = (destination / item.filename).resolve()
        if destination != target and destination not in target.parents:
            raise RuntimeError(f"Unsafe ZIP member path: {item.filename}")
        if target.is_file() and target.stat().st_size == item.file_size:
            checksum = 0
            with target.open("rb") as existing:
                while chunk := existing.read(4 * 1024 * 1024):
                    checksum = binascii.crc32(chunk, checksum)
            if checksum & 0xFFFFFFFF == item.CRC:
                with lock:
                    counters["complete"] += 1
                    counters["skipped"] += 1
                return
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_name(f".{target.name}.extract-{os.getpid()}-{threading.get_ident()}")
        try:
            with thread_archive().open(item, "r") as source, temporary.open("wb") as output:
                shutil.copyfileobj(source, output, length=4 * 1024 * 1024)
            if temporary.stat().st_size != item.file_size:
                raise RuntimeError(f"Extracted size mismatch: {item.filename}")
            temporary.replace(target)
        finally:
            if temporary.exists():
                temporary.unlink()
        with lock:
            counters["complete"] += 1
            counters["extracted"] += 1
            counters["bytes"] += item.file_size
            complete = counters["complete"]
            if complete % 1000 == 0 or complete == len(entries):
                elapsed = max(time.monotonic() - started, 1e-9)
                print(
                    f"ZIP_PROGRESS complete={complete}/{len(entries)} "
                    f"extracted={counters['extracted']} skipped={counters['skipped']} "
                    f"files_per_second={complete / elapsed:.1f}",
                    flush=True,
                )

    with ThreadPoolExecutor(max_workers=workers) as pool:
        list(pool.map(extract, entries, chunksize=1))

    actual_files = sum(1 for path in destination.rglob("*") if path.is_file())
    if actual_files != len(entries):
        raise RuntimeError(f"ZIP file-count mismatch: expected={len(entries)} actual={actual_files}")
    marker = {
        "archive": str(archive),
        "destination": str(destination),
        "expected_files": len(entries),
        "actual_files": actual_files,
        "workers": workers,
        **counters,
    }
    args.ready_marker.parent.mkdir(parents=True, exist_ok=True)
    temporary_marker = args.ready_marker.with_suffix(args.ready_marker.suffix + ".tmp")
    temporary_marker.write_text(json.dumps(marker, indent=2) + "\n", encoding="utf-8")
    temporary_marker.replace(args.ready_marker)
    print(f"ZIP_EXTRACT_OK files={actual_files} marker={args.ready_marker}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
