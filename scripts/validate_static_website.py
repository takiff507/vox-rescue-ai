"""Validate the deployable static Vox Rescue website without network access."""

from __future__ import annotations

from collections import Counter
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit


ROOT = Path(__file__).resolve().parents[1] / "website"


class PageParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.ids = []
        self.links = []
        self.assets = []
        self.title_count = 0
        self.h1_count = 0

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if "id" in values:
            self.ids.append(values["id"])
        if tag == "title":
            self.title_count += 1
        if tag == "h1":
            self.h1_count += 1
        if tag == "a" and values.get("href"):
            self.links.append(values)
        if tag in {"img", "script", "link"}:
            location = values.get("src") or values.get("href")
            if location:
                self.assets.append(location)


def local_target(page: Path, location: str) -> tuple[Path, str]:
    parsed = urlsplit(location)
    target = page if not parsed.path else (page.parent / unquote(parsed.path)).resolve()
    return target, unquote(parsed.fragment)


def main() -> int:
    html_files = sorted(ROOT.glob("*.html"))
    pages = {}
    errors = []
    for page in html_files:
        parser = PageParser()
        parser.feed(page.read_text(encoding="utf-8"))
        parser.close()
        pages[page.resolve()] = parser
        if parser.title_count != 1:
            errors.append(f"{page.name}: expected one title element")
        if parser.h1_count != 1:
            errors.append(f"{page.name}: expected one h1 element")
        duplicate_ids = [name for name, count in Counter(parser.ids).items() if count > 1]
        if duplicate_ids:
            errors.append(f"{page.name}: duplicate ids {duplicate_ids}")

    for page, parser in pages.items():
        for values in parser.links:
            location = values["href"]
            parsed = urlsplit(location)
            if parsed.scheme in {"http", "https"}:
                if parsed.scheme != "https":
                    errors.append(f"{page.name}: external link is not HTTPS: {location}")
                if values.get("target") == "_blank":
                    rel = set((values.get("rel") or "").split())
                    if not {"noopener", "noreferrer"}.issubset(rel):
                        errors.append(f"{page.name}: unsafe new-tab link: {location}")
                continue
            if parsed.scheme or location.startswith(("mailto:", "tel:")):
                continue
            target, fragment = local_target(page, location)
            if not target.exists():
                errors.append(f"{page.name}: missing link target {location}")
                continue
            if fragment and target.suffix.casefold() == ".html":
                target_page = pages.get(target.resolve())
                if target_page is not None and fragment not in target_page.ids:
                    errors.append(f"{page.name}: missing fragment {location}")

        for location in parser.assets:
            parsed = urlsplit(location)
            if parsed.scheme or location.startswith("data:"):
                continue
            target, _ = local_target(page, location)
            if not target.is_file():
                errors.append(f"{page.name}: missing asset {location}")

    required_vb_pages = ["index.html", "download.html", "help.html", "terms.html", "privacy.html"]
    for name in required_vb_pages:
        text = (ROOT / name).read_text(encoding="utf-8")
        if "https://vb-audio.com/Cable/" not in text:
            errors.append(f"{name}: official VB-CABLE link missing")
    complete_text = "\n".join(page.read_text(encoding="utf-8") for page in html_files)
    for stale in ("production installer includes", "select Vox Rescue as the recording input"):
        if stale.casefold() in complete_text.casefold():
            errors.append(f"stale bundled-driver claim remains: {stale}")

    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1
    print(f"VALID_HTML_PAGES={len(html_files)}")
    print("LOCAL_LINKS_AND_ASSETS=PASS")
    print("VB_CABLE_DISCLOSURE=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
