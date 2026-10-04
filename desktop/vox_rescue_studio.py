"""Vox Rescue Studio: listen to the best validated model on Windows."""

from __future__ import annotations

import hashlib
import os
import queue
import sys
import threading
import time
import tkinter as tk
import traceback
import webbrowser
from dataclasses import dataclass
from pathlib import Path
from tkinter import messagebox, ttk

try:
    from df3_runtime import DF3ChunkProcessor
except ImportError:  # imported as desktop.vox_rescue_studio during tests
    from desktop.df3_runtime import DF3ChunkProcessor

try:
    from virtual_audio import endpoints_for_host, is_virtual_capture, is_virtual_playback
except ImportError:  # imported as desktop.vox_rescue_studio during tests
    from desktop.virtual_audio import endpoints_for_host, is_virtual_capture, is_virtual_playback

try:
    from silence_gate import AdaptiveSilenceGate
except ImportError:  # imported as desktop.vox_rescue_studio during tests
    from desktop.silence_gate import AdaptiveSilenceGate

try:
    import numpy as np
except ImportError:  # pragma: no cover - reported in the UI
    np = None

try:
    import sounddevice as sd
except ImportError:  # pragma: no cover - reported in the UI
    sd = None

try:
    import pystray
    from PIL import Image as PILImage
    from PIL import ImageTk
except ImportError:  # pragma: no cover - reported in the UI
    pystray = None
    PILImage = None
    ImageTk = None


COLORS = {
    "bg": "#f6f8f8", "panel": "#ffffff", "panel2": "#eef2f2",
    "line": "#dce4e3", "text": "#212626", "muted": "#697572",
    "accent": "#177c6b", "accent2": "#177c6b", "warn": "#916514",
    "danger": "#bd4051",
}

PROTECTED_MODEL_SHA256 = (
    "b42f1aed76ccd476b293f1bdf98d5acc289fb75d924581fb3c2bdc4b4a341301"
)
VB_CABLE_DOWNLOAD_URL = "https://vb-audio.com/Cable/"
_single_instance_handle = None


def application_root() -> Path:
    """Return the source root or the PyInstaller bundle root."""
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parents[1]


def app_data_dir() -> Path:
    base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    path = base / "VoxRescue"
    path.mkdir(parents=True, exist_ok=True)
    return path


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as source:
        while block := source.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def acquire_single_instance() -> bool:
    """Prevent two copies from competing for the same realtime audio devices."""
    global _single_instance_handle
    if os.name != "nt":
        return True
    try:
        import ctypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        create_mutex = kernel32.CreateMutexW
        create_mutex.argtypes = [ctypes.c_void_p, ctypes.c_bool, ctypes.c_wchar_p]
        create_mutex.restype = ctypes.c_void_p
        handle = create_mutex(None, False, "Local\\VoxRescue.Desktop.1")
        if not handle:
            return True
        if ctypes.get_last_error() == 183:  # ERROR_ALREADY_EXISTS
            kernel32.CloseHandle(handle)
            return False
        _single_instance_handle = handle
    except Exception:
        # A platform-specific guard must never prevent the audio app launching.
        return True
    return True


def square_icon_source(source, size=512, padding=34):
    """Center a transparent logo inside a square icon without distortion."""
    source = source.convert("RGBA")
    bounds = source.getbbox()
    if bounds:
        source = source.crop(bounds)
    available = max(1, size - (padding * 2))
    source.thumbnail((available, available), PILImage.Resampling.LANCZOS)
    canvas = PILImage.new("RGBA", (size, size), (0, 0, 0, 0))
    canvas.alpha_composite(
        source,
        ((size - source.width) // 2, (size - source.height) // 2),
    )
    return canvas


@dataclass
class AudioSettings:
    sample_rate: int = 48_000
    block_size: int = 480
    channels: int = 1
    monitor_gain: float = 0.85


class AudioEngine:
    def __init__(self, settings: AudioSettings, on_meter, on_state, model_dir, checkpoint):
        self.settings = settings
        self.on_meter = on_meter
        self.on_state = on_state
        self.monitor_enabled = False
        self.ai_enabled = False
        self.stream = None
        self.monitor_stream = None
        self.input_device = None
        self.output_device = None
        self.virtual_output_device = None
        self.virtual_capture_name = None
        self.virtual_mic_active = False
        self.model_dir = Path(model_dir)
        self.model_processor = DF3ChunkProcessor(
            self.model_dir, checkpoint, sample_rate=settings.sample_rate, chunk_ms=20
        )
        self.model_processor.start()
        self._ai_input_buffer = np.empty(0, dtype=np.float32) if np is not None else None
        self._ai_output_buffer = np.empty(0, dtype=np.float32) if np is not None else None
        self._ai_started = False
        self._ai_fade_block = 0
        self._ai_fade_blocks = 3
        self._ai_prebuffer_samples = self.model_processor.chunk_size * 3
        self._ai_last_good = np.empty(0, dtype=np.float32) if np is not None else None
        self._ai_underruns = 0
        self._audio_generation = 0
        self._render_generation = 0
        self._limiter_gain = 1.0
        # The trained engine handles analogue noise. This gate only handles
        # digital mute, so soft speech is not classified as background noise.
        self._silence_gate = AdaptiveSilenceGate(
            settings.sample_rate, minimum_open_db=-90.0,
            minimum_close_db=-96.0, instant_open_db=-90.0,
            open_margin_db=0.0, close_margin_db=0.0,
            open_confirmation_ms=0.0,
        )
        self._last_meter = 0.0
        self._callback_error = queue.Queue()
        self._monitor_queue = queue.Queue(maxsize=16)
        self._monitor_last = (
            np.zeros(settings.block_size, dtype=np.float32) if np is not None else None
        )
        self._monitor_underruns = 0
        self._stream_started_at = 0.0
        self._callback_last_seen = 0.0
        self._callback_failures = 0

    @property
    def available(self) -> bool:
        return sd is not None and np is not None

    def set_devices(
        self,
        input_device,
        output_device,
        virtual_output_device=None,
        virtual_capture_name=None,
    ):
        changed = (
            self.input_device,
            self.output_device,
            self.virtual_output_device,
            self.virtual_capture_name,
        ) != (
            input_device,
            output_device,
            virtual_output_device,
            virtual_capture_name,
        )
        self.input_device = input_device
        self.output_device = output_device
        self.virtual_output_device = virtual_output_device
        self.virtual_capture_name = virtual_capture_name
        if changed and (
            self.stream is not None
            or self.monitor_stream is not None
            or self.virtual_output_device is not None
            or self.monitor_enabled
        ):
            self.restart()

    @property
    def virtual_route_ready(self) -> bool:
        return self.virtual_output_device is not None and bool(self.virtual_capture_name)

    def start(self):
        if not self.available:
            raise RuntimeError("Install numpy and sounddevice first")
        target_output = (
            self.virtual_output_device
            if self.virtual_output_device is not None
            else self.output_device
        )
        if self.input_device is None or target_output is None:
            raise RuntimeError("Select a valid microphone and output device")
        self.stop(announce=False)
        self._reset_ai_buffers()
        self.model_processor.flush()
        self._clear_monitor_queue()
        self.stream = sd.Stream(
            samplerate=self.settings.sample_rate,
            blocksize=self.settings.block_size,
            device=(self.input_device, target_output),
            channels=(1, 2),
            dtype="float32",
            latency="low",
            callback=self._callback,
            dither_off=True,
            prime_output_buffers_using_stream_callback=True,
        )
        self.stream.start()
        self._stream_started_at = time.monotonic()
        self._callback_last_seen = 0.0
        self.virtual_mic_active = self.virtual_output_device is not None
        if self.virtual_mic_active and self.monitor_enabled:
            self._start_monitor_stream()
        if self.virtual_mic_active:
            self.on_state("VIRTUAL MIC LIVE", COLORS["accent2"])
        else:
            self.on_state("LIVE MONITOR READY", COLORS["accent2"])

    def restart(self):
        should_run = self.virtual_output_device is not None or self.monitor_enabled
        self.stop(announce=False)
        if should_run:
            self.start()
        else:
            self.on_state("MONITOR OFF", COLORS["muted"])

    def _stop_monitor_stream(self):
        if self.monitor_stream is not None:
            self.monitor_stream.stop()
            self.monitor_stream.close()
            self.monitor_stream = None
        self._clear_monitor_queue()

    def stop(self, announce=True):
        self._stop_monitor_stream()
        if self.stream is not None:
            self.stream.stop()
            self.stream.close()
            self.stream = None
        self._stream_started_at = 0.0
        self._callback_last_seen = 0.0
        self.virtual_mic_active = False
        if announce:
            self.on_state("MONITOR OFF", COLORS["muted"])

    def shutdown(self):
        self.stop()
        self.model_processor.stop()

    def set_model(self, checkpoint):
        """Switch checkpoints while live monitoring stays in safe bypass mode."""
        self.ai_enabled = False
        self._reset_ai_buffers()
        previous = self.model_processor
        previous.stop()
        self.model_processor = DF3ChunkProcessor(
            self.model_dir,
            checkpoint,
            sample_rate=self.settings.sample_rate,
            chunk_ms=20,
        )
        self.model_processor.start()
        self._ai_prebuffer_samples = self.model_processor.chunk_size * 3

    def set_ai(self, enabled: bool):
        self.model_processor.flush()
        self.ai_enabled = enabled
        self._audio_generation += 1

    def _reset_ai_buffers(self):
        self._ai_input_buffer = np.empty(0, dtype=np.float32)
        self._ai_output_buffer = np.empty(0, dtype=np.float32)
        self._ai_started = False
        self._ai_fade_block = 0
        self._ai_last_good = np.empty(0, dtype=np.float32)
        self._ai_underruns = 0
        self._limiter_gain = 1.0
        self._silence_gate.reset()

    def _clear_monitor_queue(self):
        while True:
            try:
                self._monitor_queue.get_nowait()
            except queue.Empty:
                break
        if self._monitor_last is not None:
            self._monitor_last.fill(0.0)
        self._monitor_underruns = 0

    def _start_monitor_stream(self):
        if self.monitor_stream is not None or self.output_device is None:
            return
        self.monitor_stream = sd.OutputStream(
            samplerate=self.settings.sample_rate,
            blocksize=self.settings.block_size,
            device=self.output_device,
            channels=2,
            dtype="float32",
            latency="low",
            callback=self._monitor_callback,
            dither_off=True,
            prime_output_buffers_using_stream_callback=True,
        )
        self.monitor_stream.start()

    def _enqueue_monitor(self, mono):
        try:
            self._monitor_queue.put_nowait(mono.copy())
        except queue.Full:
            try:
                self._monitor_queue.get_nowait()
            except queue.Empty:
                pass
            try:
                self._monitor_queue.put_nowait(mono.copy())
            except queue.Full:
                pass

    def _transparent_limiter(self, signal):
        """Prevent digital clipping with instant attack and a smooth release."""
        peak = float(np.max(np.abs(signal))) if signal.size else 0.0
        target_gain = min(1.0, 0.96 / max(peak, 1e-9))
        if target_gain < self._limiter_gain:
            self._limiter_gain = target_gain
        else:
            self._limiter_gain += (1.0 - self._limiter_gain) * 0.08
        return np.clip(signal * self._limiter_gain, -0.98, 0.98)

    def _smooth_dry_fallback(self, mono):
        fallback = mono.copy()
        if self._ai_last_good.size:
            fade_samples = min(96, fallback.size)
            ramp = np.linspace(0.0, 1.0, fade_samples, dtype=np.float32)
            fallback[:fade_samples] = (
                self._ai_last_good[-1] * (1.0 - ramp)
                + fallback[:fade_samples] * ramp
            )
        return fallback

    def _process_ai(self, mono):
        if not self.model_processor.ready or self.model_processor.error:
            return mono.copy()
        chunk_size = self.model_processor.chunk_size
        if self._ai_input_buffer.size == 0 and mono.size == chunk_size:
            submitted = self.model_processor.submit(mono)
        else:
            self._ai_input_buffer = np.concatenate((self._ai_input_buffer, mono))
            submitted = True
            while self._ai_input_buffer.size >= chunk_size:
                chunk = self._ai_input_buffer[:chunk_size]
                self._ai_input_buffer = self._ai_input_buffer[chunk_size:]
                submitted = self.model_processor.submit(chunk) and submitted
        new_chunks = []
        while True:
            chunk = self.model_processor.pop_output()
            if chunk is None:
                break
            new_chunks.append(chunk)
        if new_chunks:
            self._ai_output_buffer = np.concatenate(
                (self._ai_output_buffer, *new_chunks)
            )
            # If the host pauses, discard stale queued speech and return to a
            # bounded realtime delay instead of replaying an old backlog.
            max_buffer = self._ai_prebuffer_samples + (chunk_size * 3)
            if self._ai_output_buffer.size > max_buffer:
                self._ai_output_buffer = self._ai_output_buffer[-max_buffer:]

        if not submitted:
            self._ai_started = False
            self._ai_fade_block = 0

        if not self._ai_started:
            if self._ai_output_buffer.size >= self._ai_prebuffer_samples:
                self._ai_started = True
                self._ai_fade_block = 0
            else:
                return self._smooth_dry_fallback(mono)

        if self._ai_output_buffer.size < mono.size:
            self._ai_underruns += 1
            self._ai_started = False
            self._ai_fade_block = 0
            return self._smooth_dry_fallback(mono)

        output = self._ai_output_buffer[: mono.size]
        self._ai_output_buffer = self._ai_output_buffer[mono.size :]
        if self._ai_fade_block < self._ai_fade_blocks:
            start = self._ai_fade_block / self._ai_fade_blocks
            end = (self._ai_fade_block + 1) / self._ai_fade_blocks
            ramp = np.linspace(start, end, mono.size, dtype=np.float32)
            output = mono * (1.0 - ramp) + output * ramp
            self._ai_fade_block += 1
        self._ai_last_good = output.copy()
        return output

    def set_monitor(self, enabled: bool):
        self.monitor_enabled = enabled
        try:
            if self.virtual_output_device is not None:
                if self.stream is None:
                    self.start()
                elif enabled:
                    self._start_monitor_stream()
                else:
                    self._stop_monitor_stream()
            elif enabled and self.stream is None:
                self.start()
            elif not enabled:
                self.stop()
        except Exception as exc:  # callback/UI boundary
            self.monitor_enabled = False
            self._stop_monitor_stream()
            self.on_state(f"AUDIO ERROR: {exc}", COLORS["danger"])

    def _callback(self, indata, outdata, frames, _time, status):
        self._callback_last_seen = time.monotonic()
        outdata.fill(0)
        try:
            # Apply UI changes on the callback thread rather than replacing
            # NumPy buffers while that thread may be slicing them.
            if self._render_generation != self._audio_generation:
                generation = self._audio_generation
                self._reset_ai_buffers()
                self._render_generation = generation
            if status:
                self._callback_error.put(str(status))
            mono = indata[:, 0].copy()
            should_publish = self.virtual_output_device is not None or self.monitor_enabled
            if should_publish:
                output = self._process_ai(mono) if self.ai_enabled else mono
                output = np.nan_to_num(output, nan=0.0, posinf=0.98, neginf=-0.98)
                if self.ai_enabled:
                    output = self._silence_gate.process(mono, output)
                output = self._transparent_limiter(output)
                rms = (
                    float(np.sqrt(np.mean(output * output)))
                    if np.count_nonzero(output)
                    else 0.0
                )
                self._last_meter = min(1.0, rms * 7.0)
                if self.virtual_output_device is not None:
                    outdata[:, 0] = output
                    outdata[:, 1] = output
                    if self.monitor_enabled:
                        self._enqueue_monitor(output)
                else:
                    monitored = output * self.settings.monitor_gain
                    outdata[:, 0] = monitored
                    outdata[:, 1] = monitored
            else:
                outdata.fill(0)
                self._last_meter = 0.0
        except Exception as exc:
            # Keep the microphone alive on a clean dry bypass if inference or
            # buffer handling ever fails inside PortAudio's realtime callback.
            self._callback_failures += 1
            self._callback_error.put(f"RECOVERED: {type(exc).__name__}: {exc}")
            try:
                mono = np.nan_to_num(
                    indata[:, 0], nan=0.0, posinf=0.98, neginf=-0.98
                )
                safe = self._transparent_limiter(mono)
                outdata[:, 0] = safe
                outdata[:, 1] = safe
                if self.virtual_output_device is not None and self.monitor_enabled:
                    self._enqueue_monitor(safe)
            except Exception:
                outdata.fill(0)
        self.on_meter(self._last_meter)

    def _monitor_callback(self, outdata, frames, _time, status):
        outdata.fill(0)
        try:
            if status:
                self._callback_error.put(f"RETURN: {status}")
            try:
                mono = self._monitor_queue.get_nowait()
                rendered = mono[:frames] * self.settings.monitor_gain
            except queue.Empty:
                self._monitor_underruns += 1
                rendered = np.zeros(frames, dtype=np.float32)
                if self._monitor_last is not None and self._monitor_last.size:
                    # Never replay an entire old block: bridge only the final
                    # sample to zero over 1 ms, then stay at digital silence.
                    size = min(frames, max(1, self.settings.sample_rate // 1000))
                    rendered[:size] = self._monitor_last[-1] * np.linspace(
                        1.0, 0.0, size, endpoint=True, dtype=np.float32
                    )
            if rendered.size < frames:
                rendered = np.pad(rendered, (0, frames - rendered.size))
            rendered = rendered[:frames]
            outdata[:, 0] = rendered
            outdata[:, 1] = rendered
            self._monitor_last = rendered.copy()
        except Exception as exc:
            self._callback_error.put(f"RETURN RECOVERED: {type(exc).__name__}: {exc}")

    @staticmethod
    def _stream_is_active(stream) -> bool:
        try:
            active = getattr(stream, "active", None)
            if active is not None:
                return bool(active)
            started = getattr(stream, "started", None)
            return True if started is None else bool(started)
        except Exception:
            return False

    def health_issue(self, now=None):
        """Return a recoverable live-stream issue, or None when healthy."""
        should_run = self.virtual_output_device is not None or self.monitor_enabled
        if not should_run:
            return None
        if self.stream is None:
            return "primary audio stream stopped"
        if not self._stream_is_active(self.stream):
            return "primary audio stream inactive"
        now = time.monotonic() if now is None else now
        if self._stream_started_at and now - self._stream_started_at > 2.0:
            if not self._callback_last_seen or now - self._callback_last_seen > 2.0:
                return "primary audio callback stalled"
        if self.virtual_mic_active and self.monitor_enabled:
            if self.monitor_stream is None:
                return "headphone return stream stopped"
            if not self._stream_is_active(self.monitor_stream):
                return "headphone return stream inactive"
        return None

    def poll_error(self):
        try:
            return self._callback_error.get_nowait()
        except queue.Empty:
            return None


class VoxRescueStudio(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Vox Rescue")
        self.geometry("432x480")
        self.minsize(432, 480)
        self.maxsize(432, 480)
        self.resizable(False, False)
        self.configure(bg=COLORS["bg"])
        self.settings = AudioSettings()
        project_root = application_root()
        self.project_root = project_root
        self.icon_path = project_root / "desktop" / "VOX RESCUE  LOGO.png"
        self.brand_path = project_root / "desktop" / "VOX RESCUE.png"
        self._window_icon = None
        self._header_icon = None
        self._brand_image = None
        self._tray_source = None
        if PILImage is not None and ImageTk is not None and self.icon_path.is_file():
            icon_source = PILImage.open(self.icon_path).convert("RGBA")
            self._tray_source = square_icon_source(icon_source)
            self._window_icon = ImageTk.PhotoImage(
                self._tray_source.resize((256, 256), PILImage.Resampling.LANCZOS)
            )
            self._header_icon = ImageTk.PhotoImage(
                self._tray_source.resize((38, 38), PILImage.Resampling.LANCZOS)
            )
            self.iconphoto(True, self._window_icon)
        if PILImage is not None and ImageTk is not None and self.brand_path.is_file():
            brand_source = PILImage.open(self.brand_path).convert("RGBA")
            brand_bounds = brand_source.getbbox()
            if brand_bounds:
                brand_source = brand_source.crop(brand_bounds)
            brand_source.thumbnail((222, 44), PILImage.Resampling.LANCZOS)
            self._brand_image = ImageTk.PhotoImage(brand_source)
        universal_checkpoint = (
            project_root
            / "models"
            / "protected"
            / "vox_rescue_engine.vrm"
        )
        if not universal_checkpoint.is_file():
            raise FileNotFoundError(f"Production AI engine not found: {universal_checkpoint}")
        if file_sha256(universal_checkpoint) != PROTECTED_MODEL_SHA256:
            raise RuntimeError("Production model integrity check failed")
        selected_checkpoint = universal_checkpoint
        self.selected_checkpoint = selected_checkpoint
        self.engine = AudioEngine(
            self.settings,
            self.update_meter,
            self.set_status,
            project_root / "models" / "DeepFilterNet3",
            selected_checkpoint,
        )
        self._model_ready_announced = False
        self.monitor_var = tk.BooleanVar(value=False)
        self.ai_var = tk.BooleanVar(value=False)
        self.input_var = tk.StringVar(value="Detecting microphone…")
        self.output_var = tk.StringVar(value="Detecting headphones…")
        self.virtual_mic_var = tk.StringVar(value="VIRTUAL MIC • CHECKING")
        self.status_var = tk.StringVar(value="READY — connect a microphone to begin")
        self.latency_var = tk.StringVar(value="48 kHz  •  10 ms host path")
        self.performance_var = tk.StringVar(value="Preparing realtime audio…")
        self.input_device_map = {}
        self.output_device_map = {}
        self._audio_warning_until = 0.0
        self._next_health_check = time.monotonic() + 3.0
        self._recovery_count = 0
        self._tray_commands = queue.Queue()
        self._tray_icon = None
        self._tray_notified = False
        self._quitting = False
        self.meter_value = 0.0
        self._build_style()
        self._build_ui()
        self.refresh_devices()
        self._start_tray()
        self.protocol("WM_DELETE_WINDOW", self.hide_to_tray)
        self.after(50, self._poll)

    def _build_style(self):
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure(
            "Compact.TCombobox",
            fieldbackground=COLORS["panel2"],
            background=COLORS["panel2"],
            foreground=COLORS["text"],
            bordercolor=COLORS["line"],
            lightcolor=COLORS["line"],
            darkcolor=COLORS["line"],
            arrowsize=14,
            padding=(6, 4),
        )
        style.map(
            "Compact.TCombobox",
            fieldbackground=[("readonly", COLORS["panel2"])],
            foreground=[("readonly", COLORS["text"]), ("focus", COLORS["text"])],
            selectbackground=[("readonly", COLORS["panel2"])],
            selectforeground=[("readonly", COLORS["text"])],
        )

    @staticmethod
    def _font(size, weight="normal"):
        return ("Segoe UI Variable", size, weight)

    def _card(self, parent):
        return tk.Frame(
            parent,
            bg=COLORS["panel"],
            highlightbackground=COLORS["line"],
            highlightthickness=1,
        )

    def _build_ui(self):
        try:
            from glass_ui import build_ui
        except ImportError:
            from desktop.glass_ui import build_ui
        build_ui(self, COLORS)

    def refresh_devices(self):
        if not self.engine.available:
            self.set_status("Install: pip install numpy sounddevice", COLORS["warn"])
            return
        try:
            devices = list(sd.query_devices())
            host_apis = list(sd.query_hostapis())

            def supports_48k(index, is_input):
                try:
                    if is_input:
                        sd.check_input_settings(
                            device=index, channels=1, dtype="float32", samplerate=48_000
                        )
                    else:
                        sd.check_output_settings(
                            device=index, channels=2, dtype="float32", samplerate=48_000
                        )
                    return True
                except Exception:
                    return False

            input_by_host = {}
            output_by_host = {}
            virtual_output_by_host = {}
            virtual_capture_by_host = {}
            for host_index in range(len(host_apis)):
                playback, capture = endpoints_for_host(devices, host_index)
                playback = [index for index in playback if supports_48k(index, False)]
                capture = [index for index in capture if supports_48k(index, True)]
                if playback:
                    virtual_output_by_host[host_index] = playback
                if capture:
                    virtual_capture_by_host[host_index] = capture

            for index, device in enumerate(devices):
                host = int(device["hostapi"])
                name = str(device["name"])
                if (
                    device["max_input_channels"] > 0
                    and not is_virtual_capture(name)
                    and supports_48k(index, True)
                ):
                    input_by_host.setdefault(host, []).append(index)
                if (
                    device["max_output_channels"] >= 2
                    and not is_virtual_playback(name)
                    and supports_48k(index, False)
                ):
                    output_by_host.setdefault(host, []).append(index)

            common_hosts = set(input_by_host).intersection(output_by_host)
            virtual_pair_hosts = (
                common_hosts
                .intersection(virtual_output_by_host)
                .intersection(virtual_capture_by_host)
            )

            def host_priority(host_index):
                name = host_apis[host_index]["name"].lower()
                if "wasapi" in name:
                    return 0
                if "wdm-ks" in name:
                    return 1
                if "directsound" in name:
                    return 2
                return 3

            if common_hosts:
                selected_host = min(
                    common_hosts,
                    key=lambda host: (
                        0 if host in virtual_pair_hosts else 1,
                        host_priority(host),
                    ),
                )
                input_candidates = input_by_host[selected_host]
                output_candidates = output_by_host[selected_host]
                host_name = host_apis[selected_host]["name"].replace("Windows ", "")
            else:
                defaults = sd.default.device
                input_candidates = [int(defaults[0])]
                output_candidates = [int(defaults[1])]
                selected_host = int(devices[input_candidates[0]]["hostapi"])
                host_name = host_apis[selected_host]["name"].replace("Windows ", "")

            defaults = sd.default.device
            default_input_name = (
                devices[int(defaults[0])]["name"] if int(defaults[0]) >= 0 else ""
            )
            default_output_name = (
                devices[int(defaults[1])]["name"] if int(defaults[1]) >= 0 else ""
            )

            def preferred(candidates, default_name, current):
                if current in candidates:
                    return current
                for index in candidates:
                    if devices[index]["name"] == default_name:
                        return index
                return candidates[0]

            input_device = preferred(
                input_candidates, default_input_name, self.engine.input_device
            )
            output_device = preferred(
                output_candidates, default_output_name, self.engine.output_device
            )
            virtual_output_device = None
            virtual_capture_name = None
            if selected_host in virtual_pair_hosts:
                virtual_outputs = virtual_output_by_host[selected_host]
                virtual_output_device = (
                    self.engine.virtual_output_device
                    if self.engine.virtual_output_device in virtual_outputs
                    else virtual_outputs[0]
                )
                capture_device = virtual_capture_by_host[selected_host][0]
                virtual_capture_name = str(devices[capture_device]["name"])
            input_labels = [f"{index}: {devices[index]['name']}" for index in input_candidates]
            output_labels = [f"{index}: {devices[index]['name']}" for index in output_candidates]
            self.input_device_map = dict(zip(input_labels, input_candidates))
            self.output_device_map = dict(zip(output_labels, output_candidates))
            self.input_combo["values"] = input_labels
            self.output_combo["values"] = output_labels

            self.input_var.set(input_labels[input_candidates.index(input_device)])
            self.output_var.set(output_labels[output_candidates.index(output_device)])
            self.latency_var.set(f"{host_name}  •  48 kHz  •  10 ms")
            self.engine.set_devices(
                input_device,
                output_device,
                virtual_output_device,
                virtual_capture_name,
            )
            if self.engine.virtual_route_ready:
                short_name = virtual_capture_name.split("(", 1)[0].strip()
                self.virtual_mic_var.set("MICROPHONE READY • SETUP & GUIDE")
                self.virtual_status_label.configure(
                    fg=COLORS["accent2"],
                    disabledforeground=COLORS["accent2"],
                    state="normal",
                    cursor="hand2",
                )
                self.set_status(
                    f"VIRTUAL MIC LIVE — select {short_name} in your app",
                    COLORS["accent2"],
                )
            else:
                self.virtual_mic_var.set("USE IN OTHER APPS • SETUP & GUIDE")
                self.virtual_status_label.configure(
                    fg=COLORS["warn"], state="normal", cursor="hand2"
                )
                self.set_status(
                    "Choose Setup & guide to use your voice in other apps",
                    COLORS["warn"],
                )
        except Exception as exc:
            self.set_status(f"DEVICE ERROR: {exc}", COLORS["danger"])

    def open_virtual_cable_setup(self):
        """Open the bundled introduction and microphone-routing instructions."""
        guide = application_root() / "help" / "help.html"
        if not guide.is_file():
            guide = application_root() / "website" / "help.html"
        target = guide.as_uri() if guide.is_file() else VB_CABLE_DOWNLOAD_URL
        opened = webbrowser.open(target, new=2)
        if opened:
            self.set_status(
                "SETUP GUIDE OPENED — follow the microphone steps",
                COLORS["accent"],
            )
        else:
            self.set_status(
                "Read RELEASE_README.txt for microphone setup",
                COLORS["warn"],
            )

    def change_device(self, is_input, value):
        device_map = self.input_device_map if is_input else self.output_device_map
        device = device_map.get(value)
        if device is None:
            return
        input_device = device if is_input else self.engine.input_device
        output_device = self.engine.output_device if is_input else device
        try:
            self.engine.set_devices(
                input_device,
                output_device,
                self.engine.virtual_output_device,
                self.engine.virtual_capture_name,
            )
            self._sync_control_state()
        except Exception as exc:
            self.set_status(f"AUDIO ERROR: {exc}", COLORS["danger"])

    def toggle_monitor(self):
        enabled = bool(self.monitor_var.get())
        self.engine.set_monitor(enabled)
        if enabled and not self.engine.monitor_enabled:
            self.monitor_var.set(False)
            return
        self._sync_control_state()

    def toggle_ai(self):
        enabled = bool(self.ai_var.get())
        if enabled and not self.engine.model_processor.ready:
            self.ai_var.set(False)
            if self.engine.model_processor.error:
                self.set_status(f"AI MODEL ERROR: {self.engine.model_processor.error}", COLORS["danger"])
            else:
                self.set_status("AI MODEL IS STILL LOADING", COLORS["warn"])
            return
        self.engine.set_ai(enabled)
        self._sync_control_state()

    def _sync_control_state(self):
        monitor_enabled = bool(self.monitor_var.get() and self.engine.monitor_enabled)
        ai_enabled = bool(self.ai_var.get() and self.engine.ai_enabled)
        if self.engine.virtual_route_ready and monitor_enabled and ai_enabled:
            self.model_status_label.configure(text="AI ENHANCEMENT ACTIVE", fg=COLORS["accent2"])
            self.set_status("VIRTUAL MIC LIVE — AI + headphone return", COLORS["accent2"])
        elif self.engine.virtual_route_ready and ai_enabled:
            self.model_status_label.configure(text="AI ENHANCEMENT ACTIVE", fg=COLORS["accent2"])
            self.set_status("VIRTUAL MIC LIVE — AI clarity active", COLORS["accent2"])
        elif self.engine.virtual_route_ready and monitor_enabled:
            self.model_status_label.configure(text="AI ENHANCEMENT OFF", fg=COLORS["muted"])
            self.set_status("VIRTUAL MIC LIVE — dry signal + headphone return", COLORS["accent"])
        elif self.engine.virtual_route_ready:
            self.model_status_label.configure(text="AI ENGINE READY", fg=COLORS["accent2"])
            self.set_status("VIRTUAL MIC LIVE — AI is off (dry signal)", COLORS["muted"])
        elif monitor_enabled and ai_enabled:
            self.model_status_label.configure(text="AI ENHANCEMENT ACTIVE", fg=COLORS["accent2"])
            self.set_status("LIVE — AI clarity and return active", COLORS["accent2"])
        elif monitor_enabled:
            self.model_status_label.configure(text="AI ENHANCEMENT OFF", fg=COLORS["muted"])
            self.set_status("LIVE — clean return, AI is off", COLORS["accent"])
        elif ai_enabled:
            self.model_status_label.configure(text="AI ENGINE ARMED", fg=COLORS["accent"])
            self.set_status("AI READY — enable return when you want to listen", COLORS["accent"])
        else:
            self.model_status_label.configure(text="AI ENGINE READY", fg=COLORS["accent2"])
            self.set_status("READY — background tray is active", COLORS["muted"])
        if self._tray_icon is not None:
            try:
                self._tray_icon.update_menu()
            except Exception:
                pass

    def set_status(self, text, color):
        self.status_var.set(text)
        self.status_pill.configure(fg=color)

    def update_meter(self, value):
        self.meter_value = value

    def _paint_meter(self, value):
        self.signal_fill.configure(bg=COLORS["accent2"] if value < 0.85 else COLORS["warn"])
        self.signal_fill.place(relwidth=min(1.0, value))

    def _queue_tray_command(self, command):
        self._tray_commands.put(command)

    def _start_tray(self):
        """Run the Windows notification-area icon without touching Tk off-thread."""
        if pystray is None or self._tray_source is None:
            return
        menu = pystray.Menu(
            pystray.MenuItem(
                "Open Vox Rescue",
                lambda _icon, _item: self._queue_tray_command("show"),
                default=True,
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(
                "Hear my return",
                lambda _icon, _item: self._queue_tray_command("toggle_monitor"),
                checked=lambda _item: bool(self.engine.monitor_enabled),
            ),
            pystray.MenuItem(
                "AI enhancement",
                lambda _icon, _item: self._queue_tray_command("toggle_ai"),
                checked=lambda _item: bool(self.engine.ai_enabled),
                enabled=lambda _item: bool(self.engine.model_processor.ready),
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(
                "Exit",
                lambda _icon, _item: self._queue_tray_command("quit"),
            ),
        )
        tray_image = self._tray_source.resize((64, 64), PILImage.Resampling.LANCZOS)
        self._tray_icon = pystray.Icon(
            "vox_rescue",
            tray_image,
            "Vox Rescue",
            menu,
        )
        threading.Thread(
            target=self._tray_icon.run,
            name="vox-rescue-tray",
            daemon=True,
        ).start()

    def _show_from_tray(self):
        self.deiconify()
        self.state("normal")
        self.lift()
        self.attributes("-topmost", True)
        self.after(250, lambda: self.attributes("-topmost", False))

    def hide_to_tray(self):
        """Hide the window while keeping live audio and the AI worker running."""
        if self._tray_icon is None:
            self.iconify()
            return
        self.withdraw()
        if self._tray_icon is not None and not self._tray_notified:
            self._tray_notified = True
            try:
                self._tray_icon.notify(
                    "Vox Rescue is still running in the background.",
                    "Vox Rescue",
                )
            except Exception:
                pass

    def _drain_tray_commands(self):
        while True:
            try:
                command = self._tray_commands.get_nowait()
            except queue.Empty:
                return True
            if command == "show":
                self._show_from_tray()
            elif command == "toggle_monitor":
                self.monitor_var.set(not self.engine.monitor_enabled)
                self.toggle_monitor()
            elif command == "toggle_ai":
                self.ai_var.set(not self.engine.ai_enabled)
                self.toggle_ai()
            elif command == "quit":
                self.close()
                return False

    def _poll(self):
        if not self._drain_tray_commands():
            return
        processor = self.engine.model_processor
        if processor.error:
            self.model_status_label.configure(text="AI MODEL LOAD ERROR", fg=COLORS["danger"])
            self.performance_var.set(processor.error)
            self.ai_var.set(False)
            if self.engine.ai_enabled:
                self.engine.set_ai(False)
            self.ai_check.configure(state="disabled")
        elif processor.ready and not self._model_ready_announced:
            self._model_ready_announced = True
            self.performance_var.set("REALTIME  •  READY")
            self.ai_check.configure(state="normal")
            self._sync_control_state()
        elif processor.ready and self.ai_var.get():
            self.performance_var.set(
                f"{processor.last_process_ms:.0f} ms  •  "
                f"{processor.dropped_chunks} drops  •  "
                f"{self.engine._ai_underruns} gaps"
            )
        error = self.engine.poll_error()
        if error:
            warning = str(error).replace("priming output", "").strip(" ,")
            if warning:
                self._audio_warning_until = time.monotonic() + 2.0
                self.set_status(f"AUDIO: {warning}", COLORS["warn"])
        elif (
            self.ai_var.get()
            and time.monotonic() >= self._audio_warning_until
            and self.status_var.get().startswith("AUDIO:")
        ):
            self.set_status("LIVE — natural clarity processing active", COLORS["accent2"])
        now = time.monotonic()
        if now >= self._next_health_check:
            self._next_health_check = now + 3.0
            health_issue = self.engine.health_issue(now)
            if health_issue:
                try:
                    self.engine.restart()
                    self._recovery_count += 1
                    self.set_status("AUDIO RECONNECTED AUTOMATICALLY", COLORS["accent2"])
                except Exception:
                    # Re-enumeration also handles unplugged/replugged devices
                    # whose Windows PortAudio index has changed.
                    self.refresh_devices()
        self._paint_meter(
            self.meter_value
            if self.monitor_var.get() or self.engine.virtual_mic_active
            else 0
        )
        if not self._quitting:
            self.after(50, self._poll)

    def close(self):
        if self._quitting:
            return
        self._quitting = True
        if self._tray_icon is not None:
            try:
                self._tray_icon.stop()
            except Exception:
                pass
        self.engine.shutdown()
        self.destroy()


def main():
    if os.name == "nt":
        try:
            import ctypes

            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
                "VoxRescue.Desktop.1"
            )
        except Exception:
            pass
    if sd is None or np is None:
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror("Vox Rescue Studio", "Install dependencies first:\n\npip install numpy sounddevice")
        root.destroy()
        return 1
    if not acquire_single_instance():
        root = tk.Tk()
        root.withdraw()
        messagebox.showinfo(
            "Vox Rescue",
            "Vox Rescue is already running. Check the Windows notification area.",
        )
        root.destroy()
        return 0
    try:
        app = VoxRescueStudio()
        # Explicitly map and briefly raise the window when launched from a
        # background terminal. Some Windows launch paths otherwise leave Tk
        # behind the currently focused application.
        app.update_idletasks()
        app.deiconify()
        app.lift()
        app.attributes("-topmost", True)
        app.after(900, lambda: app.attributes("-topmost", False))
        app.mainloop()
        return 0
    except Exception:
        details = traceback.format_exc()
        try:
            crash_log = app_data_dir() / "crash.log"
            crash_log.write_text(details, encoding="utf-8")
        except Exception:
            crash_log = None
        try:
            root = tk.Tk()
            root.withdraw()
            suffix = f"\n\nDetails: {crash_log}" if crash_log is not None else ""
            messagebox.showerror(
                "Vox Rescue",
                f"Vox Rescue could not start.{suffix}",
            )
            root.destroy()
        except Exception:
            pass
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
