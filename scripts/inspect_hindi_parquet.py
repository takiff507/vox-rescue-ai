"""Inspect IndicVoices-R Hindi Parquet shards without extracting audio."""

from __future__ import annotations

import glob
import json
from pathlib import Path

import pyarrow.parquet as pq


def scalar_preview(value):
    if isinstance(value, dict):
        return {key: (f"<{len(item)} bytes>" if isinstance(item, bytes) else item) for key, item in value.items()}
    if isinstance(value, bytes):
        return f"<{len(value)} bytes>"
    return value


def main() -> int:
    paths = sorted(
        Path(path)
        for path in glob.glob(
            "/workspace/vox_datasets_v2/archives/indicvoices_r_hindi/data/*.parquet"
        )
    )
    if not paths:
        raise RuntimeError("No Hindi Parquet shards found")
    total_rows = 0
    shard_rows = {}
    for path in paths:
        parquet = pq.ParquetFile(path)
        rows = parquet.metadata.num_rows
        total_rows += rows
        shard_rows[path.name] = rows
    first = pq.ParquetFile(paths[0])
    columns = first.schema_arrow.names
    requested = [name for name in ("audio", "snr", "c50", "duration", "speaker_id", "filename") if name in columns]
    sample = first.read_row_group(0, columns=requested).slice(0, 1).to_pylist()[0]
    report = {
        "files": len(paths),
        "total_bytes": sum(path.stat().st_size for path in paths),
        "total_rows": total_rows,
        "shard_rows": shard_rows,
        "schema": str(first.schema_arrow),
        "sample": {key: scalar_preview(value) for key, value in sample.items()},
    }
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
