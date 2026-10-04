from pathlib import Path
import unittest
import numpy as np
from desktop.df3_runtime import DF3ChunkProcessor


class RuntimeBuffersTests(unittest.TestCase):
    def test_flush_rejects_inflight_audio_from_previous_session(self):
        processor = DF3ChunkProcessor(Path("unused"), Path("unused"))
        old_generation = processor._generation
        processor.flush()
        processor._publish_latest((old_generation, np.ones(960, dtype=np.float32)))
        expected = np.full(960, 0.2, dtype=np.float32)
        processor._publish_latest((processor._generation, expected))
        np.testing.assert_array_equal(processor.pop_output(), expected)
        self.assertIsNone(processor.pop_output())


if __name__ == "__main__":
    unittest.main()
