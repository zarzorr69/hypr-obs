# Background service

Run this once inside your Hyprland session:

```sh
hypr-obs enable
```

With a reachable systemd user manager, this creates and enables
`hypr-obs.service`. It is a user service: no sudo or system-wide installation
is involved. The worker remains running, reads saved OBS/Aitum shortcut
changes every three seconds by default, and waits if OBS or Hyprland is closed.
It reconnects when the compositor returns and finds a new OBS window after
OBS restarts.

The unit has `Restart=always` and `RestartSec=3`, so systemd restarts an
unexpectedly exited worker. A deliberate `stop` or `disable` stays stopped.
The service is enabled for the user's default target; it can start before
Hyprland and wait. It does not change systemd lingering settings.

## Controls

| Command | Effect |
| --- | --- |
| `hypr-obs enable` | Configure the watcher, enable login autostart, and start/restart it |
| `hypr-obs start` | Start the configured watcher immediately |
| `hypr-obs stop` | Stop now; retain login autostart and settings |
| `hypr-obs restart` | Restart now |
| `hypr-obs disable` | Stop and remove the autostart unit/hook and forwarding settings |
| `hypr-obs status` | Show the supervisor, phase, service PID/restarts and discovered shortcuts |
| `hypr-obs logs -f` | Follow service logs |

You can use systemd directly too:

```sh
systemctl --user status hypr-obs.service
systemctl --user restart hypr-obs.service
journalctl --user -u hypr-obs.service -f
systemctl --user cat hypr-obs.service
```

Do not add `sudo`: that would operate on the wrong user manager.

`status` distinguishes watching, waiting for Hyprland, retrying after a read/IPC
error, and stopped. Waiting for a desktop is a healthy service state, not an
instruction to repeatedly reinstall the program. If no OBS window exists,
the watcher remains ready but has no forwarding keys to reserve.

## What changes automatically

Save your changes in OBS or Aitum Stream Suite. New, removed or edited hotkeys
are discovered on the next scan. The interval can be changed with:

```sh
hypr-obs enable --interval 2
```

This watches saved shortcut configuration, not arbitrary new terminal commands.
Unsaved text in a settings dialog cannot be discovered yet. Existing Hyprland
shortcut conflicts and ambiguous OBS instances are still reported/skipped.

## Session environment

The Hyprland startup hook calls `hypr-obs start` through its cached program.
It saves only the current compositor signature, display/runtime variables and PATH
for this service, avoiding reliance on a terminal's environment being inherited
by systemd. It does not import the full shell environment into the user manager.

The running worker refreshes that snapshot when reconnecting. If an old
signature no longer exists and exactly one compositor remains, it can attach
to that new session. It does not guess between multiple unrelated sessions.

Fresh units live at `~/.config/systemd/user/hypr-obs.service`, respecting
`XDG_CONFIG_HOME`. Settings/cached worker are under `~/.config/hypr-obs`, and
session/status snapshots under `~/.local/state/hypr-obs`. Prototype upgrades
can retain the `obs-hotkey-bridge` settings/state directories. The generated
unit uses absolute, quoted interpreter and worker paths.

## Foreground debugging

The public daemon command no longer requires a settings argument:

```sh
hypr-obs stop
hypr-obs daemon
```

It runs in that terminal until Ctrl+C. Then return to the supervised watcher:

```sh
hypr-obs start
```

Running `daemon` while another worker is active reports that it is already
running, rather than starting another watcher. An explicit settings path is
still available for development, but normal use does not need one.

## Non-systemd fallback

The default supervisor choice is `auto`. If a user manager is unavailable,
Hyprland starts a detached process and `start`, `stop`, `restart`, `status`
and `logs` still work. That fallback has no external crash supervisor.

Use `hypr-obs enable --supervisor systemd` to require systemd and report an
unavailable manager instead of falling back. Use `--supervisor process` to
explicitly choose the detached process backend.

Updating through the installer automatically stops the older worker and
upgrades it. Disabling/uninstalling stops the unit before deleting its cached
program so a configured restart policy cannot resurrect a removed installation.
