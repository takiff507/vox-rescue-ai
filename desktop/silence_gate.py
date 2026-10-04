"""Realtime adaptive silence gate for the Vox Rescue output path."""

from __future__ import annotations

import math

import numpy as np


def _db_to_amplitude(db: float) -> float:
    return 10.0 ** (db / 20.0)


class AdaptiveSilenceGate:
    """Mute a stationary microphone noise floor without clipping normal speech.

    The gate learns only while closed. A separate open/close threshold, speech
    hold, and short gain ramps prevent noise chatter and click discontinuities.
    """

    def __init__(
        self,
        sample_rate: int = 48_000,
        *,
        minimum_open_db: float = -35.0,
        minimum_close_db: float = -41.0,
        instant_open_db: float = -24.0,
        open_margin_db: float = 7.0,
        close_margin_db: float = 3.0,
        open_confirmation_ms: float = 30.0,
        hold_ms: float = 240.0,
        attack_ms: float = 3.0,
        release_ms: float = 12.0,
    ):
        self.sample_rate = int(sample_rate)
        self.minimum_open_rms = _db_to_amplitude(minimum_open_db)
        self.minimum_close_rms = _db_to_amplitude(minimum_close_db)
        self.instant_open_rms = _db_to_amplitude(instant_open_db)
        self.open_ratio = _db_to_amplitude(open_margin_db)
        self.close_ratio = _db_to_amplitude(close_margin_db)
        self.open_confirmation_samples = max(
            1, round(self.sample_rate * open_confirmation_ms / 1000.0)
        )
        self.hold_samples = max(1, round(self.sample_rate * hold_ms / 1000.0))
        self.attack_samples = max(1, round(self.sample_rate * attack_ms / 1000.0))
        self.release_samples = max(1, round(self.sample_rate * release_ms / 1000.0))
        self.reset()

    def reset(self):
        # A conservative starting floor keeps common analogue microphone idle
        # noise muted immediately; it then converges to the attached device.
        self.noise_rms = _db_to_amplitude(-50.0)
        self.last_input_rms = 0.0
        self.is_open = False
        self._hold_remaining = 0
        self._candidate_samples = 0
        self._gain = 0.0
        self._target_gain = 0.0
        self._ramp_remaining = 0

    @property
    def gain(self) -> float:
        return self._gain

    @property
    def open_threshold_rms(self) -> float:
        return max(self.minimum_open_rms, self.noise_rms * self.open_ratio)

    @property
    def close_threshold_rms(self) -> float:
        return max(self.minimum_close_rms, self.noise_rms * self.close_ratio)

    def _update_activity(self, reference: np.ndarray):
        if reference.size:
            finite = np.nan_to_num(reference, nan=0.0, posinf=0.0, neginf=0.0)
            rms = float(math.sqrt(float(np.mean(finite * finite)) + 1e-30))
        else:
            rms = 0.0
        self.last_input_rms = rms

        if self.is_open and rms >= self.open_threshold_rms:
            self._hold_remaining = self.hold_samples
        elif self.is_open:
            self._hold_remaining = max(0, self._hold_remaining - reference.size)
            if self._hold_remaining == 0 and rms < self.close_threshold_rms:
                self.is_open = False
        elif rms >= self.instant_open_rms:
            # Unambiguously strong close-mic speech and the emergency dry
            # bypass must never lose their first block.
            self.is_open = True
            self._hold_remaining = self.hold_samples
            self._candidate_samples = 0
        elif rms >= self.open_threshold_rms:
            # Real speech persists across several 10 ms host blocks. A cable
            # bump, analogue heartbeat, or a model/input impulse usually does
            # not. Confirm activity before opening so one idle transient cannot
            # expose hundreds of milliseconds of processed residual noise. The
            # AI path already has more lookahead than this confirmation window,
            # so the start of speech is still present when output gain opens.
            self._candidate_samples += reference.size
            if self._candidate_samples >= self.open_confirmation_samples:
                self.is_open = True
                self._hold_remaining = self.hold_samples
                self._candidate_samples = 0
        else:
            self._candidate_samples = 0

        if not self.is_open:
            # Fall quickly when a quieter device is attached, but rise slowly so
            # a short speech onset can never be learned as the new noise floor.
            bounded = min(max(rms, _db_to_amplitude(-90.0)), self.minimum_open_rms)
            alpha = 0.08 if bounded < self.noise_rms else 0.01
            self.noise_rms += (bounded - self.noise_rms) * alpha

        target = 1.0 if self.is_open else 0.0
        if target != self._target_gain:
            self._target_gain = target
            self._ramp_remaining = (
                self.attack_samples if target > self._gain else self.release_samples
            )

    def _gain_envelope(self, length: int) -> np.ndarray:
        envelope = np.empty(length, dtype=np.float32)
        offset = 0
        if self._ramp_remaining > 0 and length > 0:
            count = min(length, self._ramp_remaining)
            start = self._gain
            fraction = count / self._ramp_remaining
            end = start + (self._target_gain - start) * fraction
            envelope[:count] = np.linspace(
                start, end, count, endpoint=True, dtype=np.float32
            )
            self._gain = end
            self._ramp_remaining -= count
            offset = count
            if self._ramp_remaining == 0:
                self._gain = self._target_gain
        if offset < length:
            envelope[offset:] = self._gain
        return envelope

    def process(self, reference_input, output):
        reference = np.asarray(reference_input, dtype=np.float32).reshape(-1)
        signal = np.asarray(output, dtype=np.float32).reshape(-1)
        self._update_activity(reference)
        if self._gain == 0.0 and self._target_gain == 0.0:
            return np.zeros_like(signal)
        gated = signal * self._gain_envelope(signal.size)
        if self._gain == 0.0 and self._target_gain == 0.0:
            gated[np.abs(gated) < 1e-12] = 0.0
        return gated.astype(np.float32, copy=False)
