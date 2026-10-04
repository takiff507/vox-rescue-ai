"""Compare downloaded archive parts against Azure Blob Content-MD5 headers."""

from __future__ import annotations

import argparse
import base64
import hashlib
import urllib.request
from pathlib import Path


def md5_base64(path: Path) -> str:
    digest = hashlib.md5(usedforsecurity=False)
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(16 * 1024 * 1024), b""):
            digest.update(chunk)
    return base64.b64encode(digest.digest()).decode("ascii")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("pattern")
    parser.add_argument("base_url")
    args = parser.parse_args()

    failed = 0
    files = sorted(args.directory.glob(args.pattern))
    if not files:
        raise SystemExit("No matching files")
    for path in files:
        if path.name.endswith(".done") or path.name.startswith(".azDownload-"):
            continue
        url = f"{args.base_url.rstrip('/')}/{path.name}"
        request = urllib.request.Request(url, method="HEAD")
        with urllib.request.urlopen(request, timeout=30) as response:
            expected = response.headers.get("Content-MD5", "")
            expected_size = int(response.headers.get("Content-Length", "-1"))
        actual = md5_base64(path)
        ok = bool(expected) and expected == actual and expected_size == path.stat().st_size
        print(
            f"{'MD5_OK' if ok else 'MD5_FAIL'} {path.name} "
            f"bytes={path.stat().st_size} expected_bytes={expected_size}"
        )
        failed += int(not ok)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
