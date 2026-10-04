# Vox Rescue virtual microphone release handoff

The production route exposes these Windows audio endpoints:

- `Vox Rescue Processor` — the private render endpoint the desktop app writes to.
- `Vox Rescue Microphone` — the capture endpoint selected in Discord, games, OBS,
  calls, and recording software.

## Build

Run `windows/build_release.ps1` from PowerShell. It compiles the x64 driver and
installer helper, validates the INF, creates a catalog, and writes the unsigned
submission artifacts to `windows/release`. It does not install or sign anything.

## Microsoft release gate

The catalog in the local release folder is intentionally unsigned. A normal
application or Store signature does not replace kernel-driver signing.

For a retail production release, register in Microsoft Hardware Dev Center, run
the applicable Windows Hardware Lab Kit tests, and submit the resulting signed
HLK package through the Windows Hardware Compatibility Program. Microsoft
attestation signing is reserved for supported testing scenarios and is not the
retail Windows Update path. Replace this local package with the package returned
and signed by Microsoft before distribution.

After Microsoft signing, the elevated installer calls:

```text
VoxRescueDeviceTool.exe install <fully-qualified-path>\VoxRescueVirtualAudio.inf
```

Uninstall calls `remove` with the same fully qualified INF path. Exit code `3010`
means Windows requires a restart. The desktop application itself remains unsigned
until the Microsoft Store identity/signing stage.

Do not enable Windows test-signing or distribute the unsigned catalog to users.
