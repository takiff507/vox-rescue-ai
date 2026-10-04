"""Verify the native project's shipped runtime dependencies without rebuilding."""
from pathlib import Path
import xml.etree.ElementTree as ET


def main():
    root = Path(__file__).resolve().parents[1]
    project = root / "windows/VoxRescueNative/VoxRescueNative.vcxproj"
    ns = {"m": "http://schemas.microsoft.com/developer/msbuild/2003"}
    items = ET.parse(project).findall(".//m:Content", ns)
    links = {}
    for item in items:
        link = item.find("m:Link", ns)
        if link is not None:
            source = (project.parent / item.attrib["Include"].replace("\\", "/")).resolve()
            assert source.is_file(), f"Missing source: {source}"
            links[link.text.replace("\\", "/").casefold()] = source
    required = ["scripts/" + name for name in (
        "audio_worker.py", "df3_runtime.py", "model_guard_loader.py",
        "model_guard.pyd", "vox_rescue_studio.py", "virtual_audio.py", "silence_gate.py", "glass_ui.py"
    )] + ["models/protected/vox_rescue_engine.vrm", "models/deepfilternet3/config.ini",
          "models/deepfilternet3/checkpoints/model_120.ckpt.best"]
    for name in required:
        assert name in links, f"Native packaging does not ship {name}"
    print(f"NATIVE_PACKAGE_DEPENDENCIES=PASS ({len(required)} files)")


if __name__ == "__main__":
    main()
