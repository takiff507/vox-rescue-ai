# Vox Rescue RunPod Final Handoff

Created before deleting the RunPod workspace.

## Archive

- File: `vox_rescue_final_handoff_20260808.tar.gz`
- Size: 1,382,873,162 bytes
- SHA-256: `c99cb206c5f191024a9d2a99d303bdad0bd8df13944117215ed0e08918ac6374`
- Verified entries: 6,439

The archive contains the complete `/workspace/vox_rescue_clean` project,
including production and experimental checkpoints, raw resume checkpoints,
evaluations, manifests, benchmark outputs, logs, scripts, configs, source code,
and the production-ready state markers from `/workspace/vox_datasets_v2/state`.

Large raw training datasets stored outside the project are intentionally not
included. They can be downloaded again if future full retraining is required.
Python caches and nested Git metadata were excluded.

## Restore

```powershell
tar -xzf vox_rescue_final_handoff_20260808.tar.gz
```

Verify before restoring:

```powershell
Get-FileHash -Algorithm SHA256 vox_rescue_final_handoff_20260808.tar.gz
```

