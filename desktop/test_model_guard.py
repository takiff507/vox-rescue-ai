import hashlib
import io
import sys
import tempfile
import unittest
from pathlib import Path

import torch


ROOT = Path(__file__).resolve().parents[1]
NATIVE_DIR = ROOT / "desktop" / "native_model_guard" / "x64" / "Release"
if str(NATIVE_DIR) not in sys.path:
    sys.path.insert(0, str(NATIVE_DIR))

import model_guard


class ProtectedModelTests(unittest.TestCase):
    original = ROOT / "models" / "current" / "vox_rescue_engine.pt"
    protected = ROOT / "models" / "protected" / "vox_rescue_engine.vrm"
    expected_hash = "301b15ed9328c91c19717c1a1265681bff3de56f95f00622392ff2c62b267f0a"

    def decrypt(self):
        return model_guard.decrypt(str(self.protected))

    def test_decrypted_bytes_match_original(self):
        payload = self.decrypt()
        try:
            self.assertEqual(hashlib.sha256(payload).hexdigest(), self.expected_hash)
            self.assertEqual(len(payload), self.original.stat().st_size)
        finally:
            payload[:] = b"\0" * len(payload)

    def test_loaded_checkpoint_tensors_are_identical(self):
        original_state = torch.load(self.original, map_location="cpu", weights_only=False)
        payload = self.decrypt()
        stream = io.BytesIO(payload)
        payload[:] = b"\0" * len(payload)
        try:
            protected_state = torch.load(stream, map_location="cpu", weights_only=False)
        finally:
            view = stream.getbuffer()
            view[:] = b"\0" * len(view)
            view.release()
            stream.close()
        self.assertEqual(original_state.keys(), protected_state.keys())
        self.assertEqual(original_state["step"], protected_state["step"])
        self.assertEqual(original_state["model"].keys(), protected_state["model"].keys())
        for name, tensor in original_state["model"].items():
            self.assertTrue(torch.equal(tensor, protected_state["model"][name]), name)

    def test_modified_container_is_rejected(self):
        modified = bytearray(self.protected.read_bytes())
        modified[len(modified) // 2] ^= 0x01
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "tampered.vrm"
            path.write_bytes(modified)
            with self.assertRaisesRegex(RuntimeError, "authentication or decryption failed"):
                model_guard.decrypt(str(path))


if __name__ == "__main__":
    unittest.main()
