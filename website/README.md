# Vox Rescue website

Static website with a classic single-page product layout: fixed navigation,
solid violet header, Information, Help, FAQ, About, Contact and a three-column
footer. Download, the full setup guide and legal pages remain separate pages.

The reference was https://clownfish-translator.com/voicechanger/. Its HTML and
CSS were inspected for structure, typography, spacing and navigation. This site
uses Vox Rescue's own copy and existing brand assets. The accent colour is
`#6550ad`. No canvas, UI mockup, external font, framework or animation library
is required.

## Preview

From the project root:

```powershell
python -m http.server 8765 --bind 127.0.0.1 --directory website
```

Open http://127.0.0.1:8765/.

## Contact

The support address is hello@ksnxrl.dev. The contact form prepares an encoded
mailto draft in the browser. The visitor opens the draft in their email app,
reviews it and sends it. No SMTP service or form backend is configured, and the
website itself does not send or store messages. The direct email link also works
without JavaScript. Inputs have no submission names, so a JavaScript-disabled
fallback does not put message contents into a website URL.

## Hosting

Upload the contents of this directory to the website's document root. Keep
assets and page filenames in their existing locations. The included .htaccess
sets headers and a 404 page for compatible Apache hosting. Replace the pending
public download/Store links only when real release URLs are available.

CSS and JavaScript URLs include a revision query to refresh cached assets.
Change that revision when publishing future asset updates.

Validate links and HTML from the project root:

```powershell
python scripts/validate_static_website.py
```

This website revision does not modify the desktop application or its model.

## Motion

Headings, setup steps and the hero reveal once with a small vertical fade.
Buttons and navigation use short hover transitions. Content stays visible when
JavaScript or IntersectionObserver is unavailable. The visitor's reduced-motion
setting disables reveals, hover movement and smooth scrolling, including when
the setting changes while the page is open. No animation library is used.
