import unittest

from desktop.virtual_audio import (
    endpoints_for_host,
    is_virtual_capture,
    is_virtual_playback,
)


class VirtualAudioDetectionTests(unittest.TestCase):
    def test_vb_cable_names(self):
        self.assertTrue(is_virtual_playback("CABLE Input (VB-Audio Virtual Cable)"))
        self.assertTrue(is_virtual_capture("CABLE Output (VB-Audio Virtual Cable)"))

    def test_future_vox_rescue_names(self):
        self.assertTrue(is_virtual_playback("Vox Rescue Processor"))
        self.assertTrue(is_virtual_capture("Vox Rescue Microphone"))

    def test_physical_and_steam_devices_are_not_cables(self):
        self.assertFalse(is_virtual_playback("Speakers (Realtek(R) Audio)"))
        self.assertFalse(is_virtual_capture("Microphone (Steam Streaming Microphone)"))

    def test_pair_is_scoped_to_host_api(self):
        devices = [
            {"name": "CABLE Input", "hostapi": 2, "max_input_channels": 0, "max_output_channels": 2},
            {"name": "CABLE Output", "hostapi": 2, "max_input_channels": 2, "max_output_channels": 0},
            {"name": "CABLE Input", "hostapi": 1, "max_input_channels": 0, "max_output_channels": 2},
        ]
        self.assertEqual(endpoints_for_host(devices, 2), ([0], [1]))

    def test_unrelated_driver_endpoints_are_not_a_pair(self):
        devices = [
            {"name": "Vox Rescue Processor", "hostapi": 0, "max_input_channels": 0, "max_output_channels": 2},
            {"name": "CABLE Output", "hostapi": 0, "max_input_channels": 2, "max_output_channels": 0},
        ]
        self.assertEqual(endpoints_for_host(devices, 0), ([], []))

    def test_incomplete_first_party_route_falls_back_to_complete_cable(self):
        devices = [
            {"name": "Vox Rescue Processor", "hostapi": 0, "max_input_channels": 0, "max_output_channels": 2},
            {"name": "CABLE Input", "hostapi": 0, "max_input_channels": 0, "max_output_channels": 2},
            {"name": "CABLE Output", "hostapi": 0, "max_input_channels": 2, "max_output_channels": 0},
        ]
        self.assertEqual(endpoints_for_host(devices, 0), ([1], [2]))


if __name__ == "__main__":
    unittest.main()
