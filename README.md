# Vox Rescue AI

Vox Rescue enhances microphone speech in real time on 64-bit Windows 10 and 11.
The compact white desktop controller selects the microphone and headphones,
switches AI noise reduction on or off, and provides optional headphone return.
The production engine preserves speech while reducing background noise.

## Project contents

| Directory | Purpose |
| --- | --- |
| `desktop/` | Primary Python desktop client, protected-model loader, audio routing, regression tests, EXE and Store packaging scripts |
| `website/` | Complete static product website, setup guide, download status, privacy and contact pages |
| `src/`, `configs/`, `scripts/` | Training, dataset preparation, streaming research and validation utilities |
| `windows/VoxRescueNative/` | Native Windows development client |
| `windows/VoxRescueVirtualAudio/`, `windows/VoxRescueDeviceTool/` | Virtual audio driver development sources and device utility |
| `release/` | Introduction, usage instructions, validation records and release handoff documentation |

The repository stores source code and required brand assets. Generated EXEs,
ZIPs, datasets, recordings, trained model weights and private encryption keys
are kept outside Git. The current production model has not been replaced or
retrained by this source upload. This private repository is not an open-source
license grant; third-party components retain their own notices and licenses.

## Website

No npm installation or build step is needed:

```powershell
python -m http.server 8765 --bind 127.0.0.1 --directory website
```

Open http://127.0.0.1:8765/. Validate pages with:

```powershell
python scripts/validate_static_website.py
```

The classic violet website uses small scroll reveals and hover transitions,
respects reduced-motion settings and requires no animation library.
Support: **hello@ksnxrl.dev**. The contact form prepares an email draft for the
visitor to review and send through their own email application.

## Desktop development

Use Python 3.11 x64 and the dependencies in `desktop/requirements-windows.txt`:

```powershell
python -m pip install -r desktop/requirements-windows.txt
python -m pip install pytest PyInstaller cryptography
python -m pytest desktop -q
```

Launching or packaging the current production app additionally requires the
existing protected model at `models/protected/vox_rescue_engine.vrm` and its
matching native model-guard extension. To rebuild that extension, restore the
matching private `desktop/native_model_guard/model_key.generated.h` from your
secure local backup and use Visual Studio C++ build tools. Never regenerate a
key over the current model or commit the generated key header.

After restoring the private production artifacts:

```powershell
python desktop/vox_rescue_studio.py
python desktop/verify_protected_runtime.py
pwsh -File desktop/build_release.ps1 -Package
```

The portable release contains `VoxRescue.exe` and its required `_internal`
directory. Keep the entire release folder together. See `desktop/README.md`
and `release/INTRODUCTION_AND_USAGE.md` for more details.

Routing audio into compatible games, Discord, Teams, Zoom or OBS currently uses
standard VB-CABLE installed separately from its official publisher. It is not
bundled. The receiving app must accept a selectable Windows microphone input.
The custom virtual audio driver sources are development work; see
`windows/VIRTUAL_MIC_RELEASE.md` before building or distributing them.

## Research and native projects

Research scripts live under `scripts/`; their configuration and dataset paths
are independent of the fixed desktop production model. Start with the local,
dataset-free checks:

```powershell
$env:PYTHONPATH = "src"
python scripts/self_check.py
python scripts/smoke_test.py
python scripts/train.py --dry-run
```

The WIL dependency for the upstream driver samples is pinned as a submodule:

```powershell
git submodule update --init windows/driver-samples/wil
```

The custom driver builds through `windows/build_release.ps1` with the Windows
Driver Kit and Visual Studio installed. The main driver build does not include
the optional upstream APO sample projects; their legacy WIL include paths may
need configuration if you choose to build the complete sample solution.
The native development client has its own README and requires an installed
Python runtime plus the same private model artifacts.

## Microsoft Store

`desktop/package_store.ps1` prepares Store packaging after the real Partner
Center identity and publisher values are available. No Store submission or
public download has been made by this source upload. Listing and usage notes
are in `release/MICROSOFT_STORE_LISTING.txt` and `release/PRODUCTION_HANDOFF.md`.
