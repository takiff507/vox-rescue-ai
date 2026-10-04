"""Authenticated in-memory loader for the protected Vox Rescue model."""

from __future__ import annotations

import io
from pathlib import Path


def load_protected_checkpoint(path: Path):
    import sys
    # Source launches and the native client use the same protected loader.
    # Frozen releases already include this extension at their bundle root.
    native_dir = Path(__file__).resolve().parent / "native_model_guard" / "x64" / "Release"
    if native_dir.is_dir() and str(native_dir) not in sys.path:
        sys.path.insert(0, str(native_dir))
    import model_guard
    import torch

    decrypted = model_guard.decrypt(str(Path(path)))
    stream = io.BytesIO(decrypted)
    decrypted[:] = b"\0" * len(decrypted)
    try:
        return torch.load(stream, map_location="cpu", weights_only=False)
    finally:
        view = stream.getbuffer()
        view[:] = b"\0" * len(view)
        view.release()
        stream.close()
