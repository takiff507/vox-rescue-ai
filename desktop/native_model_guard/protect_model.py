"""Create an authenticated Vox Rescue model container and native key header."""

from __future__ import annotations

import argparse
import hashlib
import os
import secrets
from pathlib import Path

from cryptography.hazmat.primitives.ciphers.aead import AESGCM


MAGIC = b"VXVRM001"
NONCE_SIZE = 12
TAG_SIZE = 16


def _bytes_literal(data: bytes) -> str:
    return ", ".join(f"0x{value:02x}" for value in data)


def _generated_header(key: bytes, entropy: bytes, key_id: str) -> str:
    mask_a = secrets.token_bytes(len(key))
    mask_b = secrets.token_bytes(len(key))
    encoded = bytes(
        value ^ first ^ second
        for value, first, second in zip(key, mask_a, mask_b, strict=True)
    )
    return f"""#pragma once

#include <array>
#include <cstdint>

namespace vox_model_key {{
inline constexpr std::array<std::uint8_t, 32> kEncoded = {{{_bytes_literal(encoded)}}};
inline constexpr std::array<std::uint8_t, 32> kMaskA = {{{_bytes_literal(mask_a)}}};
inline constexpr std::array<std::uint8_t, 32> kMaskB = {{{_bytes_literal(mask_b)}}};
inline constexpr std::array<std::uint8_t, 32> kDpapiEntropy = {{{_bytes_literal(entropy)}}};
inline constexpr wchar_t kKeyFileName[] = L"model_{key_id}.key";
}}  // namespace vox_model_key
"""


def protect(source: Path, destination: Path, header: Path) -> tuple[str, str]:
    source = source.resolve()
    destination = destination.resolve()
    header = header.resolve()
    if not source.is_file():
        raise FileNotFoundError(source)
    if destination.exists():
        raise FileExistsError(f"Refusing to overwrite protected model: {destination}")
    if header.exists():
        raise FileExistsError(f"Refusing to overwrite generated key header: {header}")

    plaintext = bytearray(source.read_bytes())
    key = bytearray(secrets.token_bytes(32))
    nonce = secrets.token_bytes(NONCE_SIZE)
    entropy = secrets.token_bytes(32)
    destination.parent.mkdir(parents=True, exist_ok=True)
    header.parent.mkdir(parents=True, exist_ok=True)

    destination_tmp = destination.with_suffix(destination.suffix + ".tmp")
    header_tmp = header.with_suffix(header.suffix + ".tmp")
    if destination_tmp.exists() or header_tmp.exists():
        raise FileExistsError("A previous protection temporary file already exists")

    try:
        encrypted_and_tag = AESGCM(bytes(key)).encrypt(nonce, bytes(plaintext), MAGIC)
        ciphertext = encrypted_and_tag[:-TAG_SIZE]
        tag = encrypted_and_tag[-TAG_SIZE:]
        container = MAGIC + nonce + tag + ciphertext
        plaintext_hash = hashlib.sha256(plaintext).hexdigest().upper()
        protected_hash = hashlib.sha256(container).hexdigest().upper()
        key_id = protected_hash[:16].lower()

        with destination_tmp.open("xb") as output:
            output.write(container)
            output.flush()
            os.fsync(output.fileno())
        with header_tmp.open("x", encoding="utf-8", newline="\n") as output:
            output.write(_generated_header(bytes(key), entropy, key_id))
            output.flush()
            os.fsync(output.fileno())
        os.replace(destination_tmp, destination)
        os.replace(header_tmp, header)
        return plaintext_hash, protected_hash
    finally:
        plaintext[:] = b"\0" * len(plaintext)
        key[:] = b"\0" * len(key)
        if destination_tmp.exists():
            destination_tmp.unlink()
        if header_tmp.exists():
            header_tmp.unlink()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    parser.add_argument("header", type=Path)
    args = parser.parse_args()
    plaintext_hash, protected_hash = protect(args.source, args.destination, args.header)
    print(f"PLAINTEXT_SHA256={plaintext_hash}")
    print(f"PROTECTED_SHA256={protected_hash}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
