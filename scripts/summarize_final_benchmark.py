"""Combine final benchmark reports and checkpoint provenance into one scorecard."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path


PROJECT = Path("/workspace/vox_rescue_clean")
OUTPUT = PROJECT / "outputs" / "clarity_v2" / "final_benchmark"
CHECKPOINT = PROJECT / "checkpoints" / "clarity_v2" / "best_production_candidate.pt"
MANIFEST = PROJECT / "manifests" / "clarity_v2" / "canonical.json"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(4 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    report_paths = {
        "hindi_normal": PROJECT / "outputs/clarity_v2/stage_a2/hindi_noisy/report.json",
        "dns_normal": PROJECT / "outputs/clarity_v2/stage_a2/dns_noisy/report.json",
        "hindi_clean": PROJECT / "outputs/clarity_v2/stage_a2/hindi_clean/report.json",
        "hindi_hard": OUTPUT / "hindi_hard/report.json",
        "dns_hard": OUTPUT / "dns_hard/report.json",
        "hindi_reverb": OUTPUT / "hindi_reverb/report.json",
        "dns_reverb": OUTPUT / "dns_reverb/report.json",
        "hindi_interferer": OUTPUT / "hindi_interferer/report.json",
        "dns_interferer": OUTPUT / "dns_interferer/report.json",
    }
    reports = {
        name: json.loads(path.read_text(encoding="utf-8"))
        for name, path in report_paths.items()
    }
    metrics = ("delta_si_sdr_db", "delta_stoi", "delta_pesq_wb")
    aggregate = {}
    for metric in metrics:
        values = [report.get(metric) for report in reports.values()]
        available = [float(value) for value in values if value is not None]
        aggregate[metric] = {
            "mean": sum(available) / len(available),
            "positive_cases": sum(value > 0 for value in available),
            "total_cases": len(available),
            "minimum": min(available),
            "maximum": max(available),
        }
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    scorecard = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "production_candidate_pending_external_same_audio_krisp_ab",
        "candidate": str(CHECKPOINT),
        "candidate_sha256": sha256(CHECKPOINT),
        "candidate_step": 6500,
        "baseline": str(PROJECT / "checkpoints/df3_stage1_5000.pt"),
        "baseline_step": 5000,
        "manifest": str(MANIFEST),
        "manifest_sha256": sha256(MANIFEST),
        "license_policy": manifest["license_policy"],
        "aggregate": aggregate,
        "cases": {
            name: {
                "delta_si_sdr_db": report.get("delta_si_sdr_db"),
                "delta_stoi": report.get("delta_stoi"),
                "delta_pesq_wb": report.get("delta_pesq_wb"),
                "base_si_sdr_db": report.get("base_si_sdr_db"),
                "candidate_si_sdr_db": report.get("tuned_si_sdr_db"),
            }
            for name, report in reports.items()
        },
    }
    OUTPUT.mkdir(parents=True, exist_ok=True)
    destination = OUTPUT / "scorecard.json"
    destination.write_text(json.dumps(scorecard, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(scorecard, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
