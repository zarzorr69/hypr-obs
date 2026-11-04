# Troubleshooting hypr-obs

Start with:

```sh
hypr-obs --version
hypr-obs doctor
hypr-obs status
```

`doctor` reads configuration and compositor information without installing
bindings or editing files. Its report includes the selected OBS root, profile,
collection, Aitum detection, translated keys and conflicting binds. `status`
reports the daemon's last result, including errors or partial discovery.

## Command not found

The default standalone command is `~/.local/bin/hypr-obs`. If that full path
works, add its directory to PATH. In fish:

```fish
fish_add_path ~/.local/bin
```

In Bash/Zsh, persist this in the appropriate startup file:

```sh
export PATH="$HOME/.local/bin:$PATH"
```

No shell configuration is edited automatically. A custom executable directory
can be chosen with `sh install.sh --bin-dir /your/bin`. Remove an existing
standalone installation before changing that directory.

## No OBS window is detected

Keep the main OBS window mapped on a workspace, and launch it normally.
Moving it to another workspace is fine. Hiding it to the system tray removes
the target this bridge needs. OBS should run as the same desktop user.

`hyprctl clients` shows its class, PID, address and Wayland/XWayland status.
The bridge groups windows by process and prefers the main OBS window over
dialogs/projectors. If another top-level OBS window is selected, include that
information in a bug report.

## Flatpak, native and Snap settings

The running OBS process's environment and mount-namespace metadata determine
candidate paths. Typical roots are:

| Installation | Typical OBS root |
| --- | --- |
| Native | `~/.config/obs-studio` |
| Flatpak | `~/.var/app/com.obsproject.Studio/config/obs-studio` |
| Snap | `~/snap/obs-studio/current/.config/obs-studio` |

Custom XDG variables and Snap names/revisions can change these. If detection
is wrong, use the exact root shown by OBS's configuration-folder command:

```sh
hypr-obs enable --obs-config /actual/path/to/obs-studio
```

The bridge does not run inside the Flatpak/Snap sandbox and does not change
the application's permissions. Host files still must be readable by your user.

## Active collection cannot be identified

Both `Gaming` and `Gaming.json` are accepted. A stale filename can fall back
to a unique saved collection display name. If selection remains ambiguous,
profile/Aitum shortcuts still load, while scene/source keys remain pending.
The available filenames appear in `doctor`.

```sh
hypr-obs enable --collection Gaming.json
```

Do not choose a random collection to suppress a warning: it can reserve keys
that the current collection does not use. Overrides pin the selection; they
stop following automatic profile/collection changes. To clear saved overrides:

```sh
hypr-obs disable
hypr-obs enable
```

## Aitum shortcuts are missing

Save Aitum Stream Suite's settings after editing a shortcut. Its per-output
and all-output hotkeys are saved in `aitum.json` beside the active profile's
`basic.ini`. The bridge reads that file and nested canvas/source hotkeys.
Look for `Aitum Stream Suite: aitum.json detected` in `status`.

If a JSON file is incomplete while OBS saves it, the affected portion is
reported as pending. Other readable hotkeys remain available, and the next
scan retries. Full settings files are not needed in a bug report; a small
hotkey-only example is usually enough.

## A shortcut is skipped

Existing Hyprland shortcuts are preserved. A conflicting key is reported with
the existing binding's description/dispatcher. Change that shortcut in OBS or
your rice to resolve it.

Physical `code:` bindings with the same modifiers are treated as possible
conflicts because this bridge does not reconstruct the active keyboard map.
Conflicts in submaps are also considered when protecting removal operations.
Multiple OBS processes using the same chord are ambiguous and skipped.

Modifier-only shortcuts, ordinary left/right mouse clicks and unknown saved
OBS keys are reported rather than guessed. Logical keysyms are used; unusual
layouts, shifted punctuation and keypad NumLock behavior need a live check.

## Shortcut is listed but OBS does not respond

1. Confirm it works with OBS focused.
2. Set OBS's hotkey focus behavior to **Never disable hotkeys**.
3. Check whether `status` reports XWayland. Hyprland documents limitations
   forwarding keys between XWayland applications.
4. Test in a normal terminal workspace. An application inhibiting compositor
   shortcuts or capturing input may prevent the bind from running.

The bridge does not enable shortcuts on the lock screen, bypass input
inhibition, force them into every submap, or implement a WebSocket/portal
fallback. A successful IPC response verifies binding registration, not that
the desired OBS action ran. Forwarded keys are reserved for OBS while its
target window exists.

## A rice update removed autostart

Some rice generators replace the parent configuration. Run `hypr-obs enable`
again to add the marked startup loader. Custom/read-only layouts need a writable
loaded entry point supplied through `--hypr-config`.

On older Hyprland, an unrelated runtime bind added on top of a bridge shortcut
can prevent safe removal. The report will request `hyprctl reload`. Reloading
clears runtime bridge bindings, after which the running daemon rechecks conflicts.

## Logs and uninstall

`hypr-obs status` prints the log location. Fresh installs use
the user journal for the systemd backend (`hypr-obs logs -f`). Detached-process
installs use `~/.local/state/hypr-obs/bridge.log`; upgraded prototypes may retain
`~/.local/state/obs-hotkey-bridge/bridge.log`.

## Daemon/service commands

Normal background use starts with `hypr-obs enable`. You do not need to provide
`daemon --settings`. `hypr-obs daemon` now discovers settings automatically and
runs in the foreground for debugging. Stop the background watcher first with
`hypr-obs stop` if you want to use that mode, then use `hypr-obs start` afterward.

If a systemd desktop reports the process fallback, run:

```sh
hypr-obs enable --supervisor systemd
systemctl --user status hypr-obs.service
```

The first command reports a missing/unreachable user manager directly. Run it
inside the normal desktop session without sudo. See [Background service](service.md).

Uninstall removes only the exact loader block originally added. If that block
was edited, it is left intact with an explanation. It does not restore an old
full config over later edits. Backups and logs are retained after removal.
