# Vox Rescue native development client

A compact light Windows UI with native Acrylic where Windows supports it.
The client uses the single protected production engine, separate AI/return
switches, live metering and matching virtual-driver endpoints. It has no model
selection controls. Close hides the window to the tray; Exit shuts down the worker.

This build relies on an installed Python 3.11 runtime and the dependencies from
`desktop/requirements-windows.txt`. The standalone portable Python client in
`dist/VoxRescue` is the primary distributable.

Build the solution with Visual Studio C++ tools and Windows SDK 10.0.28000.0.
The project copies the protected model, native extension, DF config and all worker
helpers into its output. `python desktop/validate_native_package.py` checks that
these packaging dependencies exist.

See `release/PRODUCTION_HANDOFF.md` for Store preparation and virtual-cable setup.
