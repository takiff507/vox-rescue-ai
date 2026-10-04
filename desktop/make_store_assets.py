"""Render correctly sized Store tiles from Vox Rescue's existing brand mark."""
from pathlib import Path
from PIL import Image


def main():
    root = Path(__file__).resolve().parents[1]
    source = Image.open(root / "desktop" / "VOX RESCUE  LOGO.png").convert("RGBA")
    bounds = source.getbbox()
    if bounds:
        source = source.crop(bounds)
    folder = root / "release" / "store-assets"
    folder.mkdir(parents=True, exist_ok=True)
    for name, size in (("StoreLogo", 50), ("Square44x44Logo", 44), ("Square150x150Logo", 150)):
        mark = source.copy()
        mark.thumbnail((round(size * .8), round(size * .8)), Image.Resampling.LANCZOS)
        canvas = Image.new("RGBA", (size, size), "#e4ecf3")
        canvas.alpha_composite(mark, ((size-mark.width)//2, (size-mark.height)//2))
        canvas.save(folder / f"{name}.png")
    print(f"Store assets: {folder}")


if __name__ == "__main__":
    main()
