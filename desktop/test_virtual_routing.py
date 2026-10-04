import types
import unittest
from unittest.mock import patch

import numpy as np

from desktop import vox_rescue_studio as studio
from desktop.virtual_audio import endpoints_for_host


class FakeProcessor:
    def __init__(self, *_args, **_kwargs):
        self.chunk_size = 960
        self.ready = True
        self.error = None
        self.checkpoint_step = 7000
        self.last_process_ms = 0.0
        self.dropped_chunks = 0

    def start(self):
        pass

    def stop(self):
        pass

    def flush(self):
        pass

    def submit(self, _chunk):
        return True

    def pop_output(self):
        return None


class FakeStream:
    created = []

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.started = False
        self.closed = False
        self.__class__.created.append(self)

    def start(self):
        self.started = True

    def stop(self):
        self.started = False

    def close(self):
        self.closed = True


class VirtualRoutingTests(unittest.TestCase):
    def setUp(self):
        FakeStream.created.clear()
        self.fake_sd = types.SimpleNamespace(Stream=FakeStream, OutputStream=FakeStream)
        self.patches = (
            patch.object(studio, "DF3ChunkProcessor", FakeProcessor),
            patch.object(studio, "sd", self.fake_sd),
        )
        for item in self.patches:
            item.start()
        self.engine = studio.AudioEngine(
            studio.AudioSettings(),
            lambda _value: None,
            lambda _text, _color: None,
            "unused-model-dir",
            "unused-checkpoint",
        )

    def tearDown(self):
        self.engine.shutdown()
        for item in reversed(self.patches):
            item.stop()

    def test_virtual_route_starts_automatically_and_targets_cable(self):
        self.engine.set_devices(20, 17, 30, "CABLE Output")
        self.assertTrue(self.engine.virtual_mic_active)
        self.assertEqual(self.engine.stream.kwargs["device"], (20, 30))
        self.assertIsNone(self.engine.monitor_stream)

    def test_return_checkbox_only_controls_secondary_headphone_stream(self):
        self.engine.set_devices(20, 17, 30, "CABLE Output")
        primary = self.engine.stream
        self.engine.set_monitor(True)
        self.assertIs(self.engine.stream, primary)
        self.assertEqual(self.engine.monitor_stream.kwargs["device"], 17)
        self.engine.set_monitor(False)
        self.assertIs(self.engine.stream, primary)
        self.assertIsNone(self.engine.monitor_stream)

    def test_virtual_output_publishes_dry_audio_when_ai_is_off(self):
        self.engine.set_devices(20, 17, 30, "CABLE Output")
        source = np.linspace(-0.25, 0.25, 480, dtype=np.float32).reshape(-1, 1)
        output = np.zeros((480, 2), dtype=np.float32)
        self.engine._callback(source, output, 480, None, None)
        output.fill(0)
        self.engine._callback(source, output, 480, None, None)
        np.testing.assert_allclose(output[:, 0], source[:, 0], atol=1e-6)
        np.testing.assert_allclose(output[:, 1], source[:, 0], atol=1e-6)

    def test_ai_off_preserves_quiet_audio_without_a_gate(self):
        self.engine.set_devices(20, 17, 30, "CABLE Output")
        time = np.arange(480, dtype=np.float32) / 48_000
        source = (0.0075 * np.sin(2.0 * np.pi * 120.0 * time)).reshape(-1, 1)
        output = np.ones((480, 2), dtype=np.float32)
        self.engine._callback(source, output, 480, None, None)
        np.testing.assert_allclose(output[:, 0], source[:, 0], atol=1e-7)

    def test_ai_on_does_not_hard_mute_soft_voice(self):
        self.engine.set_devices(20, 17, 30, "CABLE Output")
        self.engine.set_ai(True)
        time = np.arange(480, dtype=np.float32) / 48_000
        source = (0.012 * np.sin(2.0 * np.pi * 220.0 * time)).reshape(-1, 1)
        output = np.zeros((480, 2), dtype=np.float32)
        self.engine._callback(source, output, 480, None, None)
        self.assertGreater(float(np.max(np.abs(output))), 0.01)
        self.engine._callback(source, output, 480, None, None)
        np.testing.assert_allclose(output[:, 0], source[:, 0], atol=1e-7)

    def test_digital_mute_eventually_closes_ai_output_after_speech_tail(self):
        self.engine.set_devices(20, 17, 30, "CABLE Output")
        self.engine.set_ai(True)
        self.engine._process_ai = lambda mono: np.full_like(mono, 0.01)
        output = np.zeros((480, 2), dtype=np.float32)
        self.engine._callback(np.full((480, 1), 0.1, dtype=np.float32), output, 480, None, None)
        for _ in range(35):
            self.engine._callback(np.zeros((480, 1), dtype=np.float32), output, 480, None, None)
        self.assertEqual(np.count_nonzero(output), 0)

    def test_without_virtual_driver_return_behaves_as_direct_monitor(self):
        self.engine.set_devices(20, 17)
        self.assertIsNone(self.engine.stream)
        self.engine.set_monitor(True)
        self.assertEqual(self.engine.stream.kwargs["device"], (20, 17))
        self.engine.set_monitor(False)
        self.assertIsNone(self.engine.stream)

    def test_callback_failure_keeps_virtual_microphone_on_dry_bypass(self):
        self.engine.set_devices(20, 17, 30, "CABLE Output")
        self.engine.ai_enabled = True
        self.engine._process_ai = lambda _mono: (_ for _ in ()).throw(
            RuntimeError("synthetic inference failure")
        )
        source = np.linspace(-0.2, 0.2, 480, dtype=np.float32).reshape(-1, 1)
        output = np.zeros((480, 2), dtype=np.float32)
        self.engine._callback(source, output, 480, None, None)
        self.assertTrue(np.isfinite(output).all())
        self.assertGreater(float(np.max(np.abs(output))), 0.1)
        self.assertEqual(self.engine._callback_failures, 1)

    def test_return_underrun_does_not_replay_previous_block(self):
        self.engine._monitor_last = np.full(480, 0.2, dtype=np.float32)
        output = np.ones((480, 2), dtype=np.float32)
        self.engine._monitor_callback(output, 480, None, None)
        bridge_samples = self.engine.settings.sample_rate // 1000
        self.assertTrue(np.all(output[bridge_samples:, :] == 0.0))
        self.assertEqual(output[-1, 0], 0.0)

    def test_inactive_audio_stream_is_reported_for_automatic_recovery(self):
        self.engine.set_devices(20, 17, 30, "CABLE Output")
        self.assertIsNone(self.engine.health_issue())
        self.engine.stream.started = False
        self.assertEqual(self.engine.health_issue(), "primary audio stream inactive")

    def test_first_party_virtual_route_is_preferred_over_legacy_cable(self):
        devices = [
            {"hostapi": 0, "name": "CABLE Input", "max_output_channels": 2, "max_input_channels": 0},
            {"hostapi": 0, "name": "CABLE Output", "max_output_channels": 0, "max_input_channels": 1},
            {"hostapi": 0, "name": "Vox Rescue Processor", "max_output_channels": 2, "max_input_channels": 0},
            {"hostapi": 0, "name": "Vox Rescue Microphone", "max_output_channels": 0, "max_input_channels": 1},
        ]
        playback, capture = endpoints_for_host(devices, 0)
        self.assertEqual(playback[0], 2)
        self.assertEqual(capture[0], 3)

    def test_setup_action_opens_the_included_guide(self):
        statuses = []
        fake_app = types.SimpleNamespace(
            set_status=lambda text, color: statuses.append((text, color))
        )
        with patch.object(studio.webbrowser, "open", return_value=True) as opener:
            studio.VoxRescueStudio.open_virtual_cable_setup(fake_app)
        opener.assert_called_once_with(
            (studio.application_root() / "website" / "help.html").as_uri(), new=2
        )
        self.assertEqual(studio.VB_CABLE_DOWNLOAD_URL, "https://vb-audio.com/Cable/")
        self.assertIn("SETUP GUIDE OPENED", statuses[-1][0])


if __name__ == "__main__":
    unittest.main()
