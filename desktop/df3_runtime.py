"""Threaded CPU runtime for the protected Vox Rescue engine."""

from __future__ import annotations

import os
import queue
import contextlib
import threading
import time
from pathlib import Path

try:
    from model_guard_loader import load_protected_checkpoint
except ImportError:  # imported as desktop.df3_runtime during tests
    from desktop.model_guard_loader import load_protected_checkpoint


class DF3ChunkProcessor:
    """Load DF3 once and process fixed audio chunks away from the audio callback."""

    def __init__(
        self,
        model_dir: Path,
        checkpoint: Path,
        sample_rate: int = 48_000,
        chunk_ms: int = 20,
        context_ms: int = 120,
        atten_lim_db: float | None = 24.0,
    ):
        self.model_dir = Path(model_dir)
        self.checkpoint = Path(checkpoint)
        self.sample_rate = sample_rate
        self.chunk_size = round(sample_rate * chunk_ms / 1000)
        self.context_chunks = max(3, round(context_ms / chunk_ms))
        self.context_size = self.context_chunks * self.chunk_size
        self.lookahead_chunks = 1
        self.crossfade_size = max(16, round(sample_rate * 0.002))
        self.atten_lim_db = atten_lim_db
        self.input_queue: queue.Queue = queue.Queue(maxsize=12)
        self.output_queue: queue.Queue = queue.Queue(maxsize=12)
        self.stop_event = threading.Event()
        self.reset_event = threading.Event()
        self._generation = 0
        self.ready = False
        self.error: str | None = None
        self.checkpoint_step: int | None = None
        self.load_seconds = 0.0
        self.last_process_ms = 0.0
        self.max_process_ms = 0.0
        self.processed_chunks = 0
        self.dropped_chunks = 0
        self._log_sink = None
        self._thread = threading.Thread(target=self._run, name="vox-df3-cpu", daemon=True)

    def start(self):
        if not self._thread.is_alive():
            self._thread.start()

    def stop(self):
        self.stop_event.set()
        try:
            self.input_queue.put_nowait(None)
        except queue.Full:
            pass
        if self._thread.is_alive():
            self._thread.join(timeout=2.0)

    @staticmethod
    def _clear_queue(target: queue.Queue):
        while True:
            try:
                target.get_nowait()
            except queue.Empty:
                return

    def flush(self):
        self._generation += 1
        self._clear_queue(self.input_queue)
        self._clear_queue(self.output_queue)
        self.reset_event.set()

    def submit(self, chunk) -> bool:
        if not self.ready or self.error:
            return False
        try:
            self.input_queue.put_nowait((self._generation, chunk.copy()))
            return True
        except queue.Full:
            self.dropped_chunks += 1
            return False

    def pop_output(self):
        while True:
            try:
                generation, output = self.output_queue.get_nowait()
            except queue.Empty:
                return None
            if generation == self._generation:
                return output

    def _publish_latest(self, output):
        """Keep realtime output current instead of allowing stale audio to build up."""
        try:
            self.output_queue.put_nowait(output)
            return
        except queue.Full:
            self.dropped_chunks += 1
        try:
            self.output_queue.get_nowait()
        except queue.Empty:
            pass
        try:
            self.output_queue.put_nowait(output)
        except queue.Full:
            self.dropped_chunks += 1

    def _open_log_sink(self):
        """Open the optional runtime log without making audio depend on it."""
        try:
            configured = os.environ.get("VOX_RESCUE_LOG_DIR")
            if configured:
                log_dir = Path(configured)
            else:
                local_root = Path(
                    os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")
                )
                log_dir = local_root / "VoxRescue" / "logs"
            log_dir.mkdir(parents=True, exist_ok=True)
            return (log_dir / "runtime.log").open(
                "a", encoding="utf-8", buffering=1
            )
        except OSError:
            # Sandboxed or locked-down Windows profiles can deny LocalAppData.
            # DeepFilterNet still needs a real file-like sink, so use NUL and
            # keep the audio engine fully operational.
            return open(os.devnull, "w", encoding="utf-8")

    def _run(self):
        try:
            import numpy as np
            import torch
            from df.enhance import enhance, init_df

            if not self.model_dir.is_dir():
                raise FileNotFoundError(f"Model directory not found: {self.model_dir}")
            if not self.checkpoint.is_file():
                raise FileNotFoundError(f"Checkpoint not found: {self.checkpoint}")
            torch.set_num_threads(max(1, min(8, os.cpu_count() or 4)))
            started = time.perf_counter()
            # Production startup needs no Git metadata. DF's logger probes Git
            # using inherited process pipes, which can stall a headless worker.
            # NONE also avoids trying to attach Loguru to pythonw's None stdout.
            # Report runtime failures through self.error and our own log file.
            self._log_sink = self._open_log_sink()
            initialized = init_df(
                model_base_dir=str(self.model_dir), log_file=None, log_level="NONE"
            )
            model, df_state = initialized[0], initialized[1]
            state = load_protected_checkpoint(self.checkpoint)
            if "model" not in state or "step" not in state:
                raise RuntimeError("Checkpoint is missing model/step metadata")
            for name, value in state["model"].items():
                if (value.is_floating_point() or value.is_complex()) and not torch.isfinite(
                    value
                ).all():
                    raise RuntimeError(f"Checkpoint tensor is not finite: {name}")
            model.load_state_dict(state["model"])
            model.eval()
            self.checkpoint_step = int(state["step"])
            # Warm up kernels before live audio starts.
            reset = getattr(df_state, "reset", None)
            if reset is not None:
                reset()
            history = torch.zeros(1, self.context_size)
            with torch.inference_mode():
                enhance(
                    model,
                    df_state,
                    history,
                    pad=True,
                    atten_lim_db=self.atten_lim_db,
                )
            if reset is not None:
                reset()
            history_np = np.zeros(self.context_size, dtype=np.float32)
            primed_chunks = 0
            provisional_head = None
            self.load_seconds = time.perf_counter() - started
            self.ready = True

            while not self.stop_event.is_set():
                try:
                    chunk = self.input_queue.get(timeout=0.1)
                except queue.Empty:
                    continue
                if chunk is None:
                    break
                chunk_generation, chunk = chunk
                if chunk_generation != self._generation:
                    continue
                if self.reset_event.is_set():
                    if reset is not None:
                        reset()
                    history_np.fill(0.0)
                    primed_chunks = 0
                    provisional_head = None
                    self.reset_event.clear()
                chunk_np = np.asarray(chunk, dtype=np.float32)
                if chunk_np.shape[0] < self.chunk_size:
                    chunk_np = np.pad(chunk_np, (0, self.chunk_size - chunk_np.shape[0]))
                history_np[:-self.chunk_size] = history_np[self.chunk_size:]
                history_np[-self.chunk_size:] = chunk_np[:self.chunk_size]
                if reset is not None:
                    reset()
                process_started = time.perf_counter()
                tensor = torch.from_numpy(history_np.copy()).unsqueeze(0)
                with torch.inference_mode():
                    window = (
                        enhance(
                            model,
                            df_state,
                            tensor,
                            pad=True,
                            atten_lim_db=self.atten_lim_db,
                        )
                        .squeeze(0)
                        .cpu()
                        .numpy()
                    )
                self.last_process_ms = (time.perf_counter() - process_started) * 1000.0
                self.max_process_ms = max(self.max_process_ms, self.last_process_ms)
                self.processed_chunks += 1
                end = window.shape[0] - self.lookahead_chunks * self.chunk_size
                output = window[max(0, end - self.chunk_size):end]
                if output.shape[0] < self.chunk_size:
                    output = np.pad(output, (0, self.chunk_size - output.shape[0]))
                output = output[: self.chunk_size].astype(np.float32, copy=False)
                # The previous inference window already predicted the first
                # 2 ms of this chunk. Blend that contiguous preview into the
                # current, lookahead-backed result to hide window seams without
                # blurring the rest of the speech frame.
                blend_size = min(self.crossfade_size, output.shape[0])
                if provisional_head is not None and blend_size:
                    ramp = 0.5 - 0.5 * np.cos(
                        np.linspace(0.0, np.pi, blend_size, dtype=np.float32)
                    )
                    output[:blend_size] = (
                        provisional_head[:blend_size] * (1.0 - ramp)
                        + output[:blend_size] * ramp
                    )
                provisional_head = window[
                    end : min(window.shape[0], end + self.crossfade_size)
                ].astype(np.float32, copy=True)
                # Do not publish partial-context startup frames. The live host
                # stays on its clean dry path while this rolling window fills,
                # avoiding the quiet/rough first frames that sound like a cut.
                primed_chunks += 1
                if primed_chunks < self.context_chunks:
                    continue
                if not np.isfinite(output).all():
                    raise RuntimeError("Model produced non-finite realtime output")
                self._publish_latest((chunk_generation, output))
        except Exception as exc:  # surfaced by the UI status poll
            self.error = f"{type(exc).__name__}: {exc}"
            self.ready = False
            if self._log_sink is not None:
                try:
                    self._log_sink.write(self.error + "\n")
                except OSError:
                    pass
        finally:
            if self._log_sink is not None:
                try:
                    self._log_sink.close()
                except OSError:
                    pass
