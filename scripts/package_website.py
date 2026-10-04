"""Validate and package only the static website, without touching the app."""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import zipfile
from pathlib import Path


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    subprocess.run([sys.executable, str(root / "scripts/validate_static_website.py")], check=True)
    website = root / "website"
    destination = root / "release/VoxRescue-Website-Classic-1.2.1.zip"
    destination.parent.mkdir(exist_ok=True)
    files = sorted(path for path in website.rglob("*") if path.is_file())
    with zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in files:
            archive.write(path, path.relative_to(website).as_posix())
    with zipfile.ZipFile(destination) as archive:
        if archive.testzip() is not None:
            raise RuntimeError("Website ZIP failed its integrity check")
        for path in files:
            if archive.read(path.relative_to(website).as_posix()) != path.read_bytes():
                raise RuntimeError(f"Website ZIP differs from source: {path.name}")
    with destination.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    destination.with_suffix(".zip.sha256.txt").write_text(
        f"{digest}  {destination.name}\n", encoding="ascii"
    )
    report = {
        "version": "1.2.1", "html_links_and_assets": "passed",
        "zip_integrity_and_source_match": "passed", "files": len(files),
        "sha256": digest, "desktop_or_model_rebuilt": False,
    }
    (root / "release/WEBSITE_PACKAGE_VALIDATION.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    print(f"WEBSITE_PACKAGE={destination.name}")
    print(f"SHA256={digest}")


if __name__ == "__main__":
    main()
