# Vox Rescue — introduction and usage

Vox Rescue improves microphone clarity for Windows calls, games, streams
and recordings. No account is required for AI processing.

## Open the full guide
Click "Setup & guide" in the app. The included guide opens in your browser.
You can also open _internal/help/help.html directly. The guide is available
offline; links to third-party publisher documentation need internet access.

## Try your microphone
1. Run VoxRescue.exe. Choose your physical microphone under Microphone.
2. Choose headphones under Headphones / return.
3. Wait for the engine, then enable AI enhancement.
4. Enable Hear my return to check the sound. Switch return off afterward
   if you do not want to hear yourself. Use headphones to avoid feedback.
Return monitoring does not need a virtual audio driver.

## Use in other apps
1. Install standard VB-CABLE separately from https://vb-audio.com/Cable/
   Follow its publisher's installation instructions and restart Windows.
2. Reopen Vox Rescue or press Refresh. Keep your physical microphone selected.
3. In the other app, choose CABLE Output (VB-Audio Virtual Cable) as its mic.
4. Leave the other app's speaker/output set to your real headphones.
5. Keep Vox Rescue running and make a short microphone test.

Your mic -> Vox Rescue -> CABLE Input -> CABLE Output -> receiving app.
CABLE Input is the sending end; CABLE Output is the microphone other apps use.

## Calls and meetings
Discord: User Settings -> Voice & Video -> Input Device -> CABLE Output.
Teams: Settings -> Devices -> Microphone -> CABLE Output.
Zoom/browser meetings: choose CABLE Output in the microphone device selector.
Allow microphone access in the browser and check your meeting's input.
Keep real headphones as the speaker; test before joining.

## Games
Select CABLE Output in the game's voice/audio input selector when supported.
If it only uses the Windows default microphone, choose CABLE Output as the
Windows default input manually, then restart the game if needed. Restore your
physical input as the default when you stop using Vox Rescue.
Games may restrict virtual devices; compatibility needs checking per game.

## OBS and recording
Add an Audio Input Capture source in OBS and select CABLE Output. Avoid
capturing the same device again globally in Settings -> Audio.
Other recording apps can use CABLE Output when they support that input.
Check levels and make a short test recording before going live.

## Troubleshooting
No route: check standard VB-CABLE installation, reboot and press Refresh.
No voice: check the physical input, receiving app's input and Windows permissions.
Echo: use headphones; disable duplicate input monitoring/capture.
Unnatural voice: compare AI ON/OFF and try without duplicate noise suppression.
Crackles: check audio formats, use matching 48 kHz where supported and close
heavy background tasks. This route processes your microphone, not game sound.

## Background mode
Closing the window keeps the app in the notification area when tray support
is available. Double-click the tray icon to restore. Use Exit to stop the app.

## Third-party audio route
VB-CABLE is donationware by VB-Audio Software and is not included with Vox
Rescue. Its publisher's terms apply. Vox Rescue is independent of the named apps.
Download: https://vb-audio.com/Cable/
Licensing/donations: https://vb-audio.com/Services/licensing.htm

## Diagnostics
Runtime logs: %LOCALAPPDATA%\VoxRescue\logs\runtime.log
Startup errors: %LOCALAPPDATA%\VoxRescue\crash.log
