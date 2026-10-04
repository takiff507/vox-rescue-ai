"""Build the explicit Vox Rescue v3 production bundle manifest."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path


PROJECT = Path("/workspace/vox_rescue_clean")
PRODUCTION = PROJECT / "checkpoints" / "production" / "v3"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(4 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def metrics(path: Path) -> dict:
    report = json.loads(path.read_text(encoding="utf-8"))
    return {
        "samples": report["samples"],
        "delta_si_sdr_db_vs_5k": report.get("delta_si_sdr_db"),
        "delta_stoi_vs_5k": report.get("delta_stoi"),
        "delta_pesq_wb_vs_5k": report.get("delta_pesq_wb"),
    }


def main() -> int:
    universal = PRODUCTION / "vox_rescue_universal_v3_step7000.pt"
    voice = PRODUCTION / "vox_rescue_voice_isolation_v3_step7250.pt"
    universal_root = PROJECT / "outputs" / "clarity_v3" / "stage_i_hard_noise"
    voice_root = PROJECT / "outputs" / "production_mode_benchmark" / "voice_isolation"
    manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "production_bundle_ready_internal_benchmarks",
        "default_mode": "universal_v3",
        "modes": {
            "universal_v3": {
                "checkpoint": str(universal),
                "sha256": sha256(universal),
                "step": 7000,
                "purpose": "default natural denoise, clarity, hard-noise and reverb",
                "benchmarks": {
                    name: metrics(universal_root / name / "report.json")
                    for name in (
                        "dns_normal",
                        "dns_hard",
                        "dns_reverb",
                        "dns_interferer",
                        "hindi_normal",
                        "hindi_hard",
                        "hindi_clean",
                        "hindi_interferer",
                    )
                },
            },
            "voice_isolation_v3": {
                "checkpoint": str(voice),
                "sha256": sha256(voice),
                "step": 7250,
                "purpose": "aggressive competing-speaker and background-voice suppression",
                "benchmarks": {
                    name: metrics(voice_root / name / "report.json")
                    for name in (
                        "dns_normal",
                        "dns_hard",
                        "dns_reverb",
                        "dns_interferer",
                    )
                },
            },
        },
        "legacy": {
            "step_5000_sha256": "c3246ebff189bd53109a219de122e5836fb2d2640d1b543e8bca8c52c17acda7",
            "step_6500_sha256": "eaad8d5da04b00429c163dd0e277744801b8195b93f7e68d02a5dd3c48f8d31d",
        },
        "training_data_policy": {
            "commercial": ["DNS5", "VCTK", "MUSAN", "RIRS_NOISES", "IndicVoices-R"],
            "excluded": ["EARS:CC-BY-NC-4.0"],
        },
        "claim_policy": "Do not claim superiority to an external product without matched external outputs.",
    }
    destination = PRODUCTION / "production_manifest.json"
    destination.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
