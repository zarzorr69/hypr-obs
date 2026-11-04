# Changelog

## 0.2.0 — 2026-11-04

- Prefer an automatically enabled systemd user service with crash restart.
- Add start, stop, restart and live logs commands.
- Make `daemon` a usable foreground watcher with automatically discovered settings.
- Keep the worker alive while Hyprland is absent and reconnect after session restarts.
- Refresh only allowlisted session/display variables for the service.
- Report service activity, PID, restart count and watcher phase in status.
- Retain a detached-process fallback for desktops without a user manager.
- Stop/remove the service before disabling or uninstalling its cached worker.
- Add service lifecycle regression tests and generated-unit syntax verification.

## 0.1.0 — 2026-11-04

First public `hypr-obs` package, following the `obs-hotkey-bridge.py` prototype.

- Install a normal `hypr-obs` command without pip dependencies or sudo.
- Add a one-line installer and standard Python console-entry-point packaging.
- Add enable, disable, status, doctor and managed uninstall commands.
- Reuse prototype settings, runtime token and startup hook during upgrades.
- Discover native, Flatpak and Snap OBS configuration paths.
- Forward profile, scene/source and Aitum Stream Suite shortcuts.
- Accept scene collection filenames with or without `.json` and report partial
  discovery without blocking other readable shortcuts.
- Support Lua and older Hyprlang runtime/config syntax, with conflict checks,
  OBS restart handling and reload recovery.
- Include automated tests and document live desktop verification still needed.
