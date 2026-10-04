# Vox Rescue release handoff — 4 October 2026

The primary release is the compact white Python desktop client, packaged as a
standalone Windows x64 application. No model was retrained, replaced, or converted.

## Production model

- Protected container: `models/protected/vox_rescue_engine.vrm`
- SHA-256: `b42f1aed76ccd476b293f1bdf98d5acc289fb75d924581fb3c2bdc4b4a341301`
- Original checkpoint SHA-256: `301b15ed9328c91c19717c1a1265681bff3de56f95f00622392ff2c62b267f0a`
- The protected checkpoint remains byte-identical to the approved original.

## Audio changes

- AI OFF sends quiet speech through without the aggressive noise gate.
- AI ON uses a digital-mute gate; the existing trained model handles analogue noise.
- Playback and capture endpoints must belong to the same virtual driver family.
- Queue generations discard in-flight output after restart or an AI toggle.
- Audio buffer resets happen on the callback thread.
- Deployment logging no longer launches Git, preventing a headless startup hang.
- Native packaging now includes the protected loader, extension, model and helpers.

## Compatibility

Windows applications must allow choosing a recording device. For Discord, OBS,
Teams, Zoom and supported games: install the standard VB-CABLE separately and
select **CABLE Output** as the microphone in the receiving app. Vox Rescue writes
to **CABLE Input**. Hear My Return controls only local monitoring.

No compatible virtual cable was detected on this development PC during testing.
Physical device discovery and real model inference were tested. Cross-application
routing on this PC still requires the virtual driver; it is not an inferred pass.
The unsigned first-party development driver is excluded from public distribution.

## Microsoft Store preparation

The user will register/reserve the Store identity later. No Store submission or
certificate installation was performed. `desktop/package_store.ps1` accepts the
real Identity Name, Publisher CN and Publisher Display Name from Partner Center.
It stages the standalone app, existing brand assets, a desktop MSIX manifest and
creates an unsigned package using the installed Windows SDK. The identity-dependent
package has not been generated or certification-tested yet.

The app is intended to be free (price 0), with no trial, subscription or required
account. Set these options in Partner Center when creating the listing. VB-CABLE
is third-party donationware and its own publisher terms apply. The MSIX does not
install or redistribute a kernel driver. Publish a real privacy-policy URL and
support contact before submitting the listing.

Official packaging reference:
https://learn.microsoft.com/en-us/windows/msix/desktop/desktop-to-uwp-manual-conversion

## Native client

The C++ client has a compact light UI with Windows Acrylic where supported. It
is a development build that uses installed Python 3.11 and audio dependencies.
The portable Python client is the primary distributable; do not market the native
client as self-contained. Build with the installed Windows SDK 10.0.28000.0.

## Website

The website is a static, light product site with local assets and a mobile menu.
Public download and Store links remain labelled as pending until actually published.
The website was edited locally; no existing hosting account was changed.

## Simple interface and guide revision (2026-10-04)

The primary controller keeps its 360 × 420 white layout. The LOCAL AI badge is
removed. Its footer opens the included introduction and setup guide, including
Discord, Teams, Zoom, browser meetings, games, OBS and recording workflows.
The same guide is published in website/help.html and bundled at _internal/help.
The site now uses one white/green theme and three navigation links throughout.

Microsoft Store eligibility remains unresolved for the third-party driver route.
Policy 10.2.4 generally restricts non-Microsoft driver dependencies, permits
case-by-case consideration for WHCP-certified drivers and requires disclosure
in the beginning of the listing and in certification notes. WHCP eligibility or
an exception has not been verified. The listing draft records this issue; a UI
wording change does not resolve it. See MICROSOFT_STORE_LISTING.txt for sources.
No Store submission or driver installation was performed.
