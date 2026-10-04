# Vox Rescue desktop

The primary desktop client is a compact 360 × 420 white controller. It uses the
unchanged protected production engine at `models/protected/vox_rescue_engine.vrm`.
Model selection is not exposed in the UI.

Run from source after installing `desktop/requirements-windows.txt`:

```powershell
python desktop/vox_rescue_studio.py
```

The native model-guard extension must exist at
`desktop/native_model_guard/x64/Release/model_guard.pyd`; source launches discover
it automatically. Packaged releases include Python and the audio runtime.

AI Enhancement controls denoising. Hear My Return controls only headphone
monitoring. With a compatible virtual cable the microphone stays available to
receiving apps independently of return monitoring. Closing the window hides it to
the notification area; Exit stops the application.

Install standard VB-CABLE separately from https://vb-audio.com/Cable/ and restart
Windows. Select CABLE Output as the input in Discord, OBS, Teams, Zoom or another
app that lets you choose a microphone. This driver is third-party donationware;
it is not bundled. Use headphones for return monitoring.

Run existing regression tests with `python -m pytest desktop -q`.
`python desktop/verify_protected_runtime.py` performs real model inference;
`python desktop/validate_native_package.py` validates native build content.

Build with `desktop/build_release.ps1`; use `-Package` to create a ZIP. Future
Store packaging uses `desktop/package_store.ps1` with the real Partner Center
identity. See `release/PRODUCTION_HANDOFF.md` for the remaining release steps.
