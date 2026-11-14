# Changelog

## 0.2.2 — 2026-11-14

- Let bare `hypr-obs` enable or refresh forwarding with automatic per-OBS
  Wayland/XWayland detection; explicit `enable` remains supported.
- Default to native Wayland `pass` and XWayland keyboard `sendshortcut`,
  while always keeping mouse hotkeys on `pass`; manual override remains.
- Add `hypr-obs remove` for managed command, service, config-hook and state
  cleanup, preserving unrelated files and leaving upstream OBS/Hyprland intact.
- Add tests for bare command, mode selection, removal and migration from
  previous saved `pass` default.

## 0.2.1 — 2026-11-14

- Add explicit XWayland OBS forwarding mode with a configurable `sendshortcut`
  keyboard fallback (`--xwayland-dispatcher`); preserve `pass` by default.
- Continue using press/release `pass` for mouse hotkeys and native Wayland OBS.
- Reconcile dispatcher changes automatically when OBS switches between native
  Wayland and XWayland; surface the selected dispatcher in status and doctor.
- Test both Lua/Hyprlang dispatcher generation and fallback selection; document
  why live XWayland delivery remains dependent on the compositor/application.

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
