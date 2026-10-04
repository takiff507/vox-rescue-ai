import unittest

import numpy as np

from desktop.silence_gate import AdaptiveSilenceGate


class AdaptiveSilenceGateTests(unittest.TestCase):
    def setUp(self):
        self.gate = AdaptiveSilenceGate(48_000)

    def test_digital_silence_is_exact_zero(self):
        block = np.zeros(480, dtype=np.float32)
        for _ in range(20):
            output = self.gate.process(block, block)
            self.assertEqual(np.count_nonzero(output), 0)

    def test_measured_muted_microphone_noise_stays_muted(self):
        rng = np.random.default_rng(7)
        time = np.arange(480, dtype=np.float32) / 48_000
        for _ in range(500):
            # About -44 dBFS, matching the measured Realtek muted-input floor.
            noise = (
                0.0075 * np.sin(2.0 * np.pi * 120.0 * time)
                + rng.normal(0.0, 0.0033, 480)
            ).astype(np.float32)
            output = self.gate.process(noise, noise)
            self.assertEqual(np.count_nonzero(output), 0)

    def test_speech_opens_then_returns_to_exact_mute(self):
        time = np.arange(480, dtype=np.float32) / 48_000
        speech = (0.08 * np.sin(2.0 * np.pi * 220.0 * time)).astype(np.float32)
        opened = [self.gate.process(speech, speech) for _ in range(5)]
        self.assertTrue(self.gate.is_open)
        self.assertGreater(float(np.sqrt(np.mean(opened[-1] ** 2))), 0.04)

        silence = np.zeros(480, dtype=np.float32)
        closed = None
        for _ in range(80):
            closed = self.gate.process(silence, silence)
        self.assertFalse(self.gate.is_open)
        self.assertEqual(self.gate.gain, 0.0)
        self.assertEqual(np.count_nonzero(closed), 0)

    def test_isolated_idle_thumps_never_open_the_gate(self):
        time = np.arange(480, dtype=np.float32) / 48_000
        quiet = np.zeros(480, dtype=np.float32)
        # A one-block -32 dBFS low-frequency bump is louder than the normal
        # open threshold, but it is not sustained speech and must stay muted.
        thump = (0.035 * np.sin(2.0 * np.pi * 75.0 * time)).astype(np.float32)
        model_residual = np.full(480, 0.004, dtype=np.float32)
        for block_index in range(300):
            reference = thump if block_index % 25 == 0 else quiet
            output = self.gate.process(reference, model_residual)
            self.assertEqual(np.count_nonzero(output), 0)
        self.assertFalse(self.gate.is_open)

    def test_quiet_sustained_voice_opens_without_touching_the_audio_shape(self):
        time = np.arange(480, dtype=np.float32) / 48_000
        quiet_voice = (0.028 * np.sin(2.0 * np.pi * 220.0 * time)).astype(np.float32)
        outputs = [self.gate.process(quiet_voice, quiet_voice) for _ in range(6)]
        self.assertTrue(self.gate.is_open)
        self.assertEqual(np.count_nonzero(outputs[0]), 0)
        self.assertEqual(np.count_nonzero(outputs[1]), 0)
        np.testing.assert_allclose(outputs[-1], quiet_voice, atol=1e-7, rtol=0.0)


if __name__ == "__main__":
    unittest.main()
