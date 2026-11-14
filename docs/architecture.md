# How hypr-obs works

`hypr-obs` is one Python module with no external Python dependencies. The
standalone installer copies that module to a normal executable on PATH;
the Python package exposes the same `main()` through a console entry point.

## Discovery

The bridge selects the current Hyprland session, reads its compositor PID and
startup arguments, and resolves `--config`/`-c` or the appropriate XDG default.
A read-only Lua capability probe chooses Lua or Hyprlang commands. This avoids
hardcoding rice-specific include chains.

OBS clients are identified by process/application identity and grouped by PID.
The main window's address is used as the forwarding target. Workspace IDs are
reported for inspection, but are not part of the binding: an OBS workspace move
therefore does not invalidate the target. XWayland OBS is discovered by
the same process and address mechanism (including the X11 `obs` window class).
The XWayland dispatcher can be `auto`, `pass`, or `sendshortcut`.
The default `auto` uses keyboard-only `sendshortcut` for XWayland
clients and `pass` for native Wayland; mouse buttons always use `pass`.
Switching window-system mode or dispatcher
changes the desired bind plan, so the daemon removes stale runtime bindings
and installs the new ones. This does not overcome Hyprland's XWayland
input-forwarding limitations.

Process XDG, Flatpak and Snap information locates OBS settings. The selected
profile and collection are read from `user.ini` or older `global.ini`. OBS's
custom configuration/profile/collection locations are respected.

## Saved hotkeys

Frontend hotkeys come from the active profile's `basic.ini`. Scene/source
bindings are read recursively from the active scene collection. Aitum Stream
Suite's `aitum.json` is read from the same profile directory; standard nested
hotkeys and Aitum's `*_hotkey` arrays are translated.

OBS key names are mapped to XKB names, with modifier flags converted to
Hyprland modifiers. A key combination shared by paired start/stop actions
produces one forwarding binding. OBS receives the event and decides which
registered action applies.

## Runtime and persistence

Enabling creates an internal daemon copy, settings and a small startup file.
The parent config receives one marked loader block and is backed up first.
Lua loaders are placed before a possible top-level return. Symlinks are
resolved without replacing them.

The daemon runs outside compositor callbacks, observes socket2 window/reload
events when available, and polls saved settings periodically. A global worker
lock prevents duplicates, and a session lock is retained for prototype compatibility.
Its outer loop waits for Hyprland and reconnects across compositor restarts.
Binding queries
and mutations happen on a changed plan, relevant event, or a periodic repair
check. Mutations are batched.

On a systemd desktop, `enable` installs a user unit with a restart policy and
starts it through `systemctl --user`. A small allowlisted session snapshot lets
the service attach to the desktop without copying the full shell environment
into the user manager. Other desktops retain the detached-process backend.
The same start/stop/restart interface controls either backend. Service output
goes to the journal; detached-process output goes to the bridge log.

Only the bridge's described runtime bindings are managed. Existing binds are
checked before additions/removals. Lua bind handles allow exact removal on
versions that support them; older removal commands use conservative conflict
checks. Closing OBS releases its forwarding keys.

The prototype's runtime descriptions and startup markers are retained for
upgrade compatibility. Existing prototype settings/storage are reused rather
than creating a second independent installation.

## Boundaries

This is event forwarding, not a remote OBS controller. It does not inspect
stream credentials, use OBS WebSockets, install OBS plugins, synthesize input
through a virtual keyboard, focus OBS, or move windows/workspaces. It does not
verify that a recording/streaming action occurred after IPC registration.

The IPC simulator tests process and file behavior. Live keyboard delivery,
input inhibition, layout-specific interpretation and downstream compositor
differences require desktop testing.

## Primary references

- [Hyprland global keybinds](https://wiki.hypr.land/configuring/core/binds/globals/)
- [Hyprland configuration entry points](https://wiki.hypr.land/configuring/core/)
- [Hyprland IPC](https://wiki.hypr.land/ipc/)
- [OBS hotkey serialization](https://github.com/obsproject/obs-studio/blob/master/libobs/obs-hotkey.c)
- [OBS frontend hotkeys](https://github.com/obsproject/obs-studio/blob/master/frontend/widgets/OBSBasic_Hotkeys.cpp)
- [OBS scene collection names](https://github.com/obsproject/obs-studio/blob/master/frontend/models/SceneCollection.cpp)
- [Aitum profile storage](https://github.com/Aitum/obs-aitum-stream-suite/blob/main/src/aitum-stream-suite.cpp)
- [Aitum output hotkeys](https://github.com/Aitum/obs-aitum-stream-suite/blob/main/src/utils/widgets/output-widget.cpp)
- [Aitum all-output hotkeys](https://github.com/Aitum/obs-aitum-stream-suite/blob/main/src/docks/output-dock.cpp)

The implementation is original Python code; the key-name mappings describe
OBS/XKB identifiers and the storage parsing follows these upstream formats.
