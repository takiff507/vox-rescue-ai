"""Virtual microphone endpoint detection for Vox Rescue on Windows."""

from __future__ import annotations


def _normalized(name: str) -> str:
    return " ".join(str(name).casefold().split())


def is_virtual_playback(name: str) -> bool:
    """Return True for the endpoint Vox Rescue writes processed audio into."""
    value = _normalized(name)
    return any(
        marker in value
        for marker in (
            "cable input",
            "vox rescue processor",
            "vox rescue virtual input",
        )
    )


def is_virtual_capture(name: str) -> bool:
    """Return True for the microphone endpoint calling apps should select."""
    value = _normalized(name)
    return any(
        marker in value
        for marker in (
            "cable output",
            "vox rescue microphone",
            "vox rescue virtual microphone",
        )
    )


def endpoints_for_host(devices, host_index: int):
    """Find a playback/capture virtual-cable pair for one PortAudio host API."""
    playback = []
    capture = []
    for index, device in enumerate(devices):
        if int(device["hostapi"]) != int(host_index):
            continue
        name = str(device["name"])
        if int(device["max_output_channels"]) >= 2 and is_virtual_playback(name):
            playback.append(index)
        if int(device["max_input_channels"]) >= 1 and is_virtual_capture(name):
            capture.append(index)
    # A playback endpoint and a recording endpoint must belong to the same
    # driver. Matching only the host API can silently join two unrelated cables.
    for family in ("vox rescue", "cable"):
        outputs = [i for i in playback if family in _normalized(devices[i]["name"])]
        inputs = [i for i in capture if family in _normalized(devices[i]["name"])]
        if outputs and inputs:
            return outputs, inputs
    return [], []
