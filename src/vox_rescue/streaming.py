"""Low-latency frame-by-frame adapter for the causal enhancement model."""

from __future__ import annotations


class StreamingEnhancer:
    """Process microphone chunks while preserving GRU and overlap-add state.

    This class deliberately has no microphone/network dependency. A later
    WebRTC, sounddevice, or application callback can pass PCM chunks to
    ``process`` and send the returned PCM chunk to its output device.
    """

    def __init__(self, model, *, n_fft: int, hop_length: int):
        import torch

        self.model = model.eval()
        self.n_fft = n_fft
        self.hop_length = hop_length
        self.device = next(model.parameters()).device
        self.window = torch.hann_window(n_fft, device=self.device)
        self.input_buffer = torch.empty(0, device=self.device)
        self.ola = torch.zeros(n_fft, device=self.device)
        self.norm = torch.zeros(n_fft, device=self.device)
        self.hidden = None

    def reset(self) -> None:
        import torch

        self.input_buffer = torch.empty(0, device=self.device)
        self.ola.zero_()
        self.norm.zero_()
        self.hidden = None

    @staticmethod
    def _empty(device):
        import torch

        return torch.empty(0, device=device)

    def process(self, chunk):
        import torch

        with torch.no_grad():
            chunk = chunk.to(self.device).float().flatten()
            if chunk.numel():
                self.input_buffer = torch.cat((self.input_buffer, chunk))
            emitted = []
            while self.input_buffer.numel() >= self.n_fft:
                frame = self.input_buffer[: self.n_fft]
                self.input_buffer = self.input_buffer[self.hop_length :]
                spectrum = torch.fft.rfft(frame * self.window, n=self.n_fft)
                magnitude = spectrum.abs().clamp_min(1e-5)
                gain, self.hidden = self.model(
                    torch.log1p(magnitude).reshape(1, 1, -1), self.hidden
                )
                enhanced = torch.fft.irfft(
                    spectrum * gain[0, 0], n=self.n_fft
                )
                self.ola += enhanced * self.window
                self.norm += self.window.square()
                emitted.append(
                    self.ola[: self.hop_length]
                    / self.norm[: self.hop_length].clamp_min(1e-4)
                )
                self.ola[:-self.hop_length] = self.ola[self.hop_length :]
                self.ola[-self.hop_length :] = 0
                self.norm[:-self.hop_length] = self.norm[self.hop_length :]
                self.norm[-self.hop_length :] = 0
            return torch.cat(emitted) if emitted else self._empty(self.device)

    def flush(self):
        """Flush buffered audio; returned tail may be longer than one chunk."""

        import torch

        with torch.no_grad():
            padding = torch.zeros(self.n_fft, device=self.device)
            return self.process(padding)
