"""Headless bridge using the same protected engine and routes as the desktop app."""
from __future__ import annotations
import argparse
import queue
import sys
import threading
import time
from pathlib import Path

try:
    from vox_rescue_studio import AudioEngine, AudioSettings, file_sha256, PROTECTED_MODEL_SHA256
    from virtual_audio import endpoints_for_host, is_virtual_capture, is_virtual_playback
except ImportError:
    from desktop.vox_rescue_studio import AudioEngine, AudioSettings, file_sha256, PROTECTED_MODEL_SHA256
    from desktop.virtual_audio import endpoints_for_host, is_virtual_capture, is_virtual_playback
import sounddevice as sd


def emit(kind: str, value=""):
    text = str(value).replace("\r", " ").replace("\n", " ")
    print(f"{kind}\t{text}", flush=True)


class RealtimeWorker:
    def __init__(self, root: Path):
        checkpoint = root / "models" / "protected" / "vox_rescue_engine.vrm"
        if not checkpoint.is_file() or file_sha256(checkpoint) != PROTECTED_MODEL_SHA256:
            raise RuntimeError("Production model integrity check failed")
        self.engine = AudioEngine(AudioSettings(), lambda _value: None,
                                  lambda text, _color: emit("STATUS", text),
                                  root / "models" / "DeepFilterNet3", checkpoint)
        self.requested_ai = False
        self.stop_event = threading.Event()
        self.command_queue = queue.Queue()

    def refresh_devices(self):
        devices = list(sd.query_devices())
        hosts = list(sd.query_hostapis())
        candidates = []
        for host, api in enumerate(hosts):
            inputs, outputs = [], []
            for i, device in enumerate(devices):
                if device["hostapi"] != host:
                    continue
                try:
                    if device["max_input_channels"] and not is_virtual_capture(device["name"]):
                        sd.check_input_settings(device=i, channels=1, dtype="float32", samplerate=48000)
                        inputs.append(i)
                    if device["max_output_channels"] >= 2 and not is_virtual_playback(device["name"]):
                        sd.check_output_settings(device=i, channels=2, dtype="float32", samplerate=48000)
                        outputs.append(i)
                except sd.PortAudioError:
                    continue
            playback, capture = endpoints_for_host(devices, host)
            valid_playback = []
            for i in playback:
                try:
                    sd.check_output_settings(device=i, channels=2, dtype="float32", samplerate=48000)
                    valid_playback.append(i)
                except sd.PortAudioError:
                    pass
            if inputs and outputs:
                candidates.append((0 if valid_playback and capture else 1,
                                   0 if "wasapi" in api["name"].lower() else 1,
                                   inputs, outputs, valid_playback, capture))
        if not candidates:
            raise RuntimeError("No compatible 48 kHz microphone/output pair found")
        _, _, inputs, outputs, playback, capture = min(candidates, key=lambda item: item[:2])
        default_input, default_output = sd.default.device
        mic = int(default_input) if int(default_input) in inputs else inputs[0]
        headphones = int(default_output) if int(default_output) in outputs else outputs[0]
        virtual_output = playback[0] if playback and capture else None
        capture_name = devices[capture[0]]["name"] if virtual_output is not None else None
        self.engine.set_devices(mic, headphones, virtual_output, capture_name)
        emit("DEVICES", devices[mic]["name"])
        emit("ROUTE", capture_name or "Install VB-CABLE separately for use in other apps")

    def command(self, line):
        command, _, value = line.strip().partition(" ")
        command = command.upper()
        if command == "ENABLE":
            self.requested_ai = value == "1"
            self.engine.set_ai(self.requested_ai and self.engine.model_processor.ready)
        elif command == "MONITOR":
            self.engine.set_monitor(value == "1")
        elif command == "REFRESH":
            self.refresh_devices()
        elif command == "QUIT":
            self.stop_event.set()

    def run(self):
        emit("WORKER", "STARTING")
        def read_commands():
            for line in sys.stdin:
                self.command_queue.put(line)
            self.command_queue.put("QUIT")
        threading.Thread(target=read_commands, daemon=True).start()
        last_ready = False
        last_emit = 0.0
        next_health = time.monotonic() + 3.0
        try:
            self.refresh_devices()
            while not self.stop_event.is_set():
                try:
                    self.command(self.command_queue.get(timeout=0.05))
                except queue.Empty:
                    pass
                except Exception as exc:
                    emit("ERROR", exc)
                processor = self.engine.model_processor
                if processor.error:
                    emit("ERROR", processor.error)
                    self.engine.set_ai(False)
                    break
                if processor.ready and not last_ready:
                    last_ready = True
                    emit("READY", "Protected engine ready")
                    self.engine.set_ai(self.requested_ai)
                now = time.monotonic()
                if now - last_emit >= 0.1:
                    emit("METER", self.engine._last_meter)
                    last_emit = now
                if now >= next_health:
                    next_health = now + 3.0
                    if self.engine.health_issue(now):
                        self.refresh_devices()
                        self.engine.restart()
        finally:
            self.engine.shutdown()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    try:
        RealtimeWorker(args.root).run()
        return 0
    except Exception as exc:
        emit("ERROR", f"{type(exc).__name__}: {exc}")
        return 1

if __name__ == "__main__":
    raise SystemExit(main())
