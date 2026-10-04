"""Iterable DNS5 dataset that streams clean speech directly from archives."""

from __future__ import annotations

import bz2
import gzip
import hashlib
import io
import json
import random
import subprocess
import tarfile
from contextlib import contextmanager
from pathlib import Path

from .audio import load_mono_segment

try:
    import soundfile as sf
    import torch
    import torch.nn.functional as functional
    from torch.utils.data import IterableDataset, get_worker_info
except ImportError as exc:  # pragma: no cover - RunPod runtime dependency
    raise RuntimeError("Archive streaming requires torch and soundfile") from exc


class ConcatenatedReader(io.RawIOBase):
    """Sequentially expose split archive parts as one readable stream."""

    def __init__(self, paths: list[Path]):
        self.paths = paths
        self.index = 0
        self.handle = paths[0].open("rb") if paths else None

    def readable(self):
        return True

    def readinto(self, buffer):
        if self.handle is None:
            return 0
        view = memoryview(buffer)
        written = 0
        while written < len(view) and self.handle is not None:
            count = self.handle.readinto(view[written:])
            if count:
                written += count
                continue
            self.handle.close()
            self.index += 1
            self.handle = self.paths[self.index].open("rb") if self.index < len(self.paths) else None
        return written

    def close(self):
        if self.handle is not None:
            self.handle.close()
            self.handle = None
        super().close()


@contextmanager
def open_archive(source: dict, rapidgzip: Path):
    paths = [Path(path) for path in source["paths"]]
    kind = source["kind"]
    process = None
    stream = None
    decompressor = None
    archive = None
    try:
        if kind == "tar_bzip2":
            decompressor = bz2.BZ2File(paths[0], mode="rb")
            archive = tarfile.open(fileobj=decompressor, mode="r|")
        elif kind == "tar_gzip":
            process = subprocess.Popen(
                [str(rapidgzip), "-d", "-c", "-P", "1", str(paths[0])],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            if process.stdout is None:
                raise RuntimeError("rapidgzip stdout pipe was not created")
            stream = process.stdout
            archive = tarfile.open(fileobj=stream, mode="r|")
        elif kind == "split_tar_gzip":
            stream = io.BufferedReader(ConcatenatedReader(paths), buffer_size=4 * 1024 * 1024)
            decompressor = gzip.GzipFile(fileobj=stream, mode="rb")
            archive = tarfile.open(fileobj=decompressor, mode="r|")
        else:
            raise ValueError(f"Unsupported archive kind: {kind}")
        yield archive
    finally:
        if archive is not None:
            archive.close()
        if decompressor is not None:
            decompressor.close()
        if stream is not None:
            stream.close()
        if process is not None:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
            elif process.returncode not in (0, -13, -15):
                stderr = process.stderr.read().decode("utf-8", errors="replace") if process.stderr else ""
                raise RuntimeError(f"rapidgzip failed for {paths[0]}: {stderr}")


def decode_wav_segment(payload: bytes, sample_rate: int, segment_length: int):
    samples, source_rate = sf.read(io.BytesIO(payload), dtype="float32", always_2d=True)
    source_frames = max(1, round(segment_length * source_rate / sample_rate))
    if samples.shape[0] > source_frames:
        start = random.randint(0, samples.shape[0] - source_frames)
        samples = samples[start : start + source_frames]
    waveform = torch.from_numpy(samples.T).mean(dim=0)
    if source_rate != sample_rate and waveform.numel() > 0:
        output_length = max(1, round(waveform.numel() * sample_rate / source_rate))
        waveform = functional.interpolate(
            waveform[None, None, :], size=output_length, mode="linear", align_corners=False
        )[0, 0]
    if waveform.numel() < segment_length:
        waveform = functional.pad(waveform, (0, segment_length - waveform.numel()))
    return waveform[:segment_length]


def read_path_list(path: Path) -> list[Path]:
    with path.open(encoding="utf-8") as handle:
        return [Path(line.strip()) for line in handle if line.strip()]


def stable_bucket(value: str, modulo: int) -> int:
    digest = hashlib.sha1(value.encode("utf-8", errors="replace")).digest()
    return int.from_bytes(digest[:8], "big") % modulo


def usable_clean(waveform) -> bool:
    """Conservative runtime guard; rejected source files remain untouched."""
    if waveform.numel() == 0 or not torch.isfinite(waveform).all():
        return False
    peak = float(waveform.abs().max())
    rms = float(waveform.square().mean().sqrt())
    active = float((waveform.abs() > 1e-4).float().mean())
    return 1e-5 <= rms <= 0.8 and peak <= 1.05 and active >= 0.01


def load_aligned_rir(path: Path, sample_rate: int, max_seconds: float):
    samples, source_rate = sf.read(path, dtype="float32", always_2d=True)
    rir = torch.from_numpy(samples.T).mean(dim=0)
    if source_rate != sample_rate and rir.numel() > 0:
        output_length = max(1, round(rir.numel() * sample_rate / source_rate))
        rir = functional.interpolate(
            rir[None, None, :], size=output_length, mode="linear", align_corners=False
        )[0, 0]
    max_length = max(1, round(sample_rate * max_seconds))
    if rir.numel() > max_length:
        rir = rir[:max_length]
    if rir.numel() == 0 or not torch.isfinite(rir).all() or rir.abs().max() < 1e-8:
        raise RuntimeError(f"Invalid RIR: {path}")
    # Remove recording pre-delay so the direct path stays aligned with the target.
    direct_index = int(rir.abs().argmax())
    rir = rir[direct_index:]
    return rir / rir.square().sum().sqrt().clamp_min(1e-8)


def fft_convolve_same(waveform, impulse, output_length: int):
    convolution_length = waveform.numel() + impulse.numel() - 1
    fft_length = 1 << (convolution_length - 1).bit_length()
    convolved = torch.fft.irfft(
        torch.fft.rfft(waveform, fft_length) * torch.fft.rfft(impulse, fft_length),
        fft_length,
    )
    return convolved[:output_length]


def balanced_partition(sources: list[dict], workers: int) -> list[list[dict]]:
    buckets = [[] for _ in range(workers)]
    loads = [0 for _ in range(workers)]
    for source in sorted(sources, key=lambda item: int(item["compressed_bytes"]), reverse=True):
        target = min(range(workers), key=loads.__getitem__)
        buckets[target].append(source)
        loads[target] += int(source["compressed_bytes"])
    return buckets


class DNS5ArchiveDataset(IterableDataset):
    def __init__(
        self,
        manifest_path: Path,
        rapidgzip: Path,
        sample_rate: int,
        segment_seconds: float,
        snr_min_db: float = -5.0,
        snr_max_db: float = 20.0,
        rir_probability: float = 0.0,
        rir_max_seconds: float = 1.0,
        early_reflection_ms: float = 50.0,
        interferer_probability: float = 0.0,
        sir_min_db: float = 3.0,
        sir_max_db: float = 15.0,
        clean_probability: float = 0.0,
        clean_type_weights: dict[str, float] | None = None,
        virtual_samples: int = 1_000_000,
    ):
        super().__init__()
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.archive_sources = manifest.get("clean_archives", [])
        self.parquet_sources = manifest.get("clean_parquet", [])
        self.extracted_lists = [
            Path(item["path_list"]) for item in manifest.get("clean_extracted", [])
        ]
        self.clean_files = []
        for path_list in self.extracted_lists:
            self.clean_files.extend(read_path_list(path_list))
        self.interferer_files = list(self.clean_files)
        for item in manifest.get("interferer_extracted", []):
            self.interferer_files.extend(read_path_list(Path(item["path_list"])))
        # Keep sampling deterministic and avoid overweighting files that appear
        # in both the clean-replay and dedicated interferer manifests.
        self.interferer_files = list(dict.fromkeys(self.interferer_files))
        self.noise_files = read_path_list(Path(manifest["noise"]["path_list"]))
        self.rir_files = read_path_list(Path(manifest["rir"]["path_list"]))
        if not (self.archive_sources or self.parquet_sources or self.clean_files):
            raise ValueError("Canonical manifest has no clean speech sources")
        if not self.noise_files:
            raise ValueError("Canonical manifest has no noise files")
        if rir_probability > 0 and not self.rir_files:
            raise ValueError("RIR augmentation requested but canonical manifest has no RIR files")
        if interferer_probability > 0 and not self.interferer_files:
            raise ValueError("Interferer augmentation requested but no random-access clean files exist")
        self.rapidgzip = rapidgzip
        self.sample_rate = sample_rate
        self.segment_length = max(1, round(sample_rate * segment_seconds))
        self.snr_min_db = snr_min_db
        self.snr_max_db = snr_max_db
        self.rir_probability = min(1.0, max(0.0, rir_probability))
        self.rir_max_seconds = max(0.05, rir_max_seconds)
        self.early_reflection_length = max(1, round(sample_rate * early_reflection_ms / 1000.0))
        self.interferer_probability = min(1.0, max(0.0, interferer_probability))
        self.sir_min_db = sir_min_db
        self.sir_max_db = sir_max_db
        self.clean_probability = min(1.0, max(0.0, clean_probability))
        manifest_weights = manifest.get("clean_type_weights", {})
        requested_weights = clean_type_weights or {}
        self.clean_type_weights = {
            "archive": float(requested_weights.get("archive", manifest_weights.get("archive", 1.0))),
            "parquet": float(requested_weights.get("parquet", manifest_weights.get("parquet", 1.0))),
            "extracted": float(requested_weights.get("extracted", manifest_weights.get("extracted", 1.0))),
        }
        self.virtual_samples = virtual_samples

    def __len__(self):
        return self.virtual_samples

    @staticmethod
    def _rms(waveform, eps=1e-8):
        return torch.sqrt(torch.mean(waveform.square()).clamp_min(eps))

    def _reverberate(self, clean):
        rir = load_aligned_rir(
            random.choice(self.rir_files), self.sample_rate, self.rir_max_seconds
        )
        reverberant = fft_convolve_same(clean, rir, self.segment_length)
        early_rir = rir[: self.early_reflection_length]
        target = fft_convolve_same(clean, early_rir, self.segment_length)
        clean_rms = self._rms(clean)
        reverberant = reverberant * (clean_rms / self._rms(reverberant))
        target = target * (clean_rms / self._rms(target))
        return reverberant, target

    def _mix(self, clean):
        if self.clean_probability > 0 and random.random() < self.clean_probability:
            return clean.clone(), clean
        speech = clean
        target = clean
        if self.rir_probability > 0 and random.random() < self.rir_probability:
            speech, target = self._reverberate(clean)
        if self.interferer_probability > 0 and random.random() < self.interferer_probability:
            interferer = load_mono_segment(
                random.choice(self.interferer_files), self.sample_rate, self.segment_length
            )
            sir_db = random.uniform(self.sir_min_db, self.sir_max_db)
            desired_interferer_rms = self._rms(target) / (10 ** (sir_db / 20.0))
            speech = speech + interferer * (desired_interferer_rms / self._rms(interferer))
        noise = load_mono_segment(
            random.choice(self.noise_files), self.sample_rate, self.segment_length
        )
        snr_db = random.uniform(self.snr_min_db, self.snr_max_db)
        desired_noise_rms = self._rms(target) / (10 ** (snr_db / 20.0))
        noise = noise * (desired_noise_rms / self._rms(noise))
        mixture = speech + noise
        peak = torch.maximum(mixture.abs().max(), target.abs().max()).clamp_min(1e-6)
        if peak > 0.98:
            scale = 0.98 / peak
            mixture = mixture * scale
            target = target * scale
        return mixture, target

    def _archive_waveforms(self, source):
        with open_archive(source, self.rapidgzip) as archive:
            for member in archive:
                if not member.isfile() or not member.name.lower().endswith(".wav"):
                    continue
                extracted = archive.extractfile(member)
                if extracted is None:
                    raise RuntimeError(f"Could not stream {source['id']}:{member.name}")
                payload = extracted.read()
                waveform = decode_wav_segment(payload, self.sample_rate, self.segment_length)
                if usable_clean(waveform):
                    yield waveform

    def _cycle_archive_waveforms(self, sources):
        while True:
            shuffled = list(sources)
            random.shuffle(shuffled)
            yielded = 0
            for source in shuffled:
                for waveform in self._archive_waveforms(source):
                    yielded += 1
                    yield waveform
            if yielded == 0:
                raise RuntimeError("Assigned archive sources yielded no usable audio")

    @staticmethod
    def _parquet_row_allowed(row: dict, source: dict) -> bool:
        duration = float(row.get("duration") or 0.0)
        snr = float(row.get("snr") or -999.0)
        c50 = float(row.get("c50") or -999.0)
        if duration < float(source.get("min_duration_seconds", 1.0)):
            return False
        if duration > float(source.get("max_duration_seconds", 30.0)):
            return False
        if snr < float(source.get("min_snr_db", -999.0)):
            return False
        if c50 < float(source.get("min_c50_db", -999.0)):
            return False
        holdout_modulo = int(source.get("holdout_modulo", 0))
        if holdout_modulo > 0:
            speaker_id = str(row.get("speaker_id") or "")
            bucket = stable_bucket(speaker_id, holdout_modulo)
            holdout_bucket = int(source.get("holdout_bucket", 0))
            split = source.get("split", "train")
            if split == "train" and bucket == holdout_bucket:
                return False
            if split == "holdout" and bucket != holdout_bucket:
                return False
        return True

    def _parquet_waveforms(self, assigned_sources):
        try:
            import pyarrow.parquet as parquet
        except ImportError as exc:
            raise RuntimeError("clean_parquet sources require pyarrow") from exc

        while True:
            shuffled = list(assigned_sources)
            random.shuffle(shuffled)
            yielded = 0
            for source, path in shuffled:
                parquet_file = parquet.ParquetFile(path)
                columns = ["audio", "snr", "c50", "duration", "speaker_id"]
                for batch in parquet_file.iter_batches(batch_size=16, columns=columns):
                    rows = batch.to_pylist()
                    random.shuffle(rows)
                    for row in rows:
                        if not self._parquet_row_allowed(row, source):
                            continue
                        audio = row.get("audio") or {}
                        payload = audio.get("bytes") if isinstance(audio, dict) else None
                        if not payload:
                            continue
                        waveform = decode_wav_segment(
                            payload, self.sample_rate, self.segment_length
                        )
                        if usable_clean(waveform):
                            yielded += 1
                            yield waveform
            if yielded == 0:
                raise RuntimeError("Assigned Parquet sources yielded no usable audio")

    def _cycle_extracted_waveforms(self, paths, worker_id: int, worker_count: int):
        assigned = [path for index, path in enumerate(paths) if index % worker_count == worker_id]
        if not assigned:
            return
        while True:
            random.shuffle(assigned)
            yielded = 0
            for path in assigned:
                try:
                    waveform = load_mono_segment(
                        path, self.sample_rate, self.segment_length
                    )
                except Exception:
                    continue
                if usable_clean(waveform):
                    yielded += 1
                    yield waveform
            if yielded == 0:
                raise RuntimeError("Assigned extracted sources yielded no usable audio")

    def __iter__(self):
        worker = get_worker_info()
        worker_id = worker.id if worker else 0
        worker_count = worker.num_workers if worker else 1
        random.seed((torch.initial_seed() + worker_id) % (2**32))
        streams = []
        weights = []

        archive_sources = balanced_partition(self.archive_sources, worker_count)[worker_id]
        if archive_sources:
            streams.append(self._cycle_archive_waveforms(archive_sources))
            weights.append(max(0.0, self.clean_type_weights["archive"]))

        parquet_items = []
        for source in self.parquet_sources:
            for path in source.get("paths", []):
                parquet_items.append((source, Path(path)))
        assigned_parquet = [
            item for index, item in enumerate(parquet_items) if index % worker_count == worker_id
        ]
        if assigned_parquet:
            streams.append(self._parquet_waveforms(assigned_parquet))
            weights.append(max(0.0, self.clean_type_weights["parquet"]))

        if self.clean_files:
            extracted_stream = self._cycle_extracted_waveforms(
                list(self.clean_files), worker_id, worker_count
            )
            if extracted_stream is not None:
                streams.append(extracted_stream)
                weights.append(max(0.0, self.clean_type_weights["extracted"]))

        if not streams or sum(weights) <= 0:
            raise RuntimeError(f"Dataset worker {worker_id} has no weighted clean source")

        yielded = 0
        worker_limit = max(1, self.virtual_samples // worker_count)
        while yielded < worker_limit:
            stream = random.choices(streams, weights=weights, k=1)[0]
            clean = next(stream)
            yield self._mix(clean)
            yielded += 1
