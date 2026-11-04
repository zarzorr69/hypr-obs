# hypr-obs

**Use your existing OBS hotkeys from any Hyprland workspace.**

Set shortcuts in OBS or Aitum Stream Suite. `hypr-obs` reads the saved settings
and forwards those key combinations to the running OBS window. Moving OBS to
another workspace requires no changes.

It discovers the active Hyprland configuration rather than guessing filenames
for Ryoku, HyDE, Hyprdots or another rice. Native, Flatpak and Snap OBS settings
are detected from the running process.

## Install

Run from a terminal in your Hyprland desktop, as your normal user:

```sh
curl -fsSL https://raw.githubusercontent.com/zarzorr69/hypr-obs/main/install.sh | sh
```

The installer adds `hypr-obs` to `~/.local/bin` and enables forwarding at login.
Keep OBS's main window open on any workspace. In OBS, choose **Settings →
Advanced → Hotkeys → Hotkey Focus Behavior → Never disable hotkeys**.

Requirements: **Linux, Python 3.9+, Hyprland and `hyprctl`**. The standalone
command has no pip dependencies and does not require sudo, an OBS plugin,
WebSocket credentials or systemd. `curl` or `wget` is needed only for downloading.

If `~/.local/bin` is not on your PATH, the installer reports it. On fish:

```fish
fish_add_path ~/.local/bin
```

For Bash or Zsh, add `export PATH="$HOME/.local/bin:$PATH"` to your shell's
startup file, then open another terminal. The full path
`~/.local/bin/hypr-obs` works immediately.

### Install from a checkout

```sh
git clone https://github.com/zarzorr69/hypr-obs.git
cd hypr-obs
sh install.sh
```

To install the command outside a running Hyprland session:

```sh
sh install.sh --no-enable
# Later, inside Hyprland:
hypr-obs enable
```

For a downloaded installer, flags can be passed through `sh -s --`:

```sh
curl -fsSL https://raw.githubusercontent.com/zarzorr69/hypr-obs/main/install.sh | sh -s -- --no-enable
```

Python packaging is also supported:

```sh
pipx install git+https://github.com/zarzorr69/hypr-obs.git
hypr-obs enable
```

## Commands

| Command | Result |
| --- | --- |
| `hypr-obs enable` | Discover OBS, install forwarding, and start it at login |
| `hypr-obs status` | Show running state, discovered files, shortcuts and conflicts |
| `hypr-obs status --json` | Show machine-readable status |
| `hypr-obs doctor` | Preview discovery and conflicts without changing anything |
| `hypr-obs disable` | Stop forwarding and remove its startup hook; keep the command |
| `hypr-obs uninstall` | Disable forwarding and remove the standalone command |
| `hypr-obs --version` | Print the version |
| `hypr-obs --help` | Show available commands |

The `install` subcommand is an alias for `enable` for compatibility with the
original script. `setup` installs the command itself and is normally called by
`install.sh`.

## What it reads

- The active OBS profile's frontend hotkeys, including recording, streaming,
  replay buffer, virtual camera and paired start/stop bindings.
- Source, scene, filter and quick-transition hotkeys in the active scene collection.
- **Aitum Stream Suite** shortcuts in the active profile's `aitum.json`: individual
  and all-output controls, pause/unpause, backtrack, split and chapter shortcuts,
  and nested canvas/source hotkeys.

Click **Apply/OK** in OBS or save Aitum's settings after editing shortcuts.
Saved changes are checked every three seconds by default. OBS window launches,
closes and Hyprland configuration reloads also trigger refreshes.

Newer `.json` collection filenames and older filename stems are both supported.
If collection discovery is ambiguous, readable profile/Aitum shortcuts remain
available and scene/source shortcuts are marked pending. The bridge does not
combine unrelated collections or silently select the newest file.

## Configuration

Normal setups need no flags. For customized locations or ambiguous instances:

```sh
hypr-obs enable --hypr-config /path/to/active/hyprland.lua
hypr-obs enable --obs-config /path/to/obs-studio
hypr-obs enable --profile Work --collection Gaming.json
hypr-obs enable --interval 5
```

`--obs-config` points to the directory ending in `obs-studio`. The collection
argument accepts its filename, stem or exact saved display name. Re-enabling
preserves saved overrides unless a new value is provided. Disable and enable
again to return to default discovery.

When two OBS processes use the same shortcut, the ambiguous shortcut is skipped.
Use `--obs-config` to select a configuration, or `--obs-pid PID` for one launch.
A pinned PID changes when OBS restarts; disable and re-enable without the pin
to return to automatic discovery.

Fresh installations keep settings in `~/.config/hypr-obs` and logs/backups in
`~/.local/state/hypr-obs`, respecting XDG overrides. Upgrades from the
`obs-hotkey-bridge.py` prototype reuse its directories, token and startup
markers to avoid running two forwarding daemons.

## Updates and removal

Rerun the installer to update its managed executable and refresh forwarding.
For a checkout, pull changes and rerun `sh install.sh`. For pipx, use
`pipx upgrade hypr-obs`, then `hypr-obs enable` to refresh the cached daemon.

```sh
hypr-obs disable    # retain the command for later use
hypr-obs uninstall  # remove a standalone installation
```

For pipx installations, run `hypr-obs disable` followed by
`pipx uninstall hypr-obs`. Package-managed launchers are not deleted by the
standalone uninstaller. Original config backups and logs are retained.

## Compatibility and validation

This uses Hyprland's `pass` dispatcher and supports both Lua and older
Hyprlang configurations. Native Wayland OBS is the intended delivery path.
XWayland forwarding has compositor limitations, and hiding OBS to the tray
removes its window target. Existing rice shortcuts are skipped and reported.

The automated suite covers parsing, Aitum storage, native/Flatpak/Snap paths,
config hooks, upgrades, command installation, uninstall, and real daemon
subprocesses against a simulated Hyprland IPC interface. **Actual keyboard
delivery in a live Hyprland/OBS desktop has not yet been verified for this
public release.** Packaging support does not imply every downstream build has
been tested.

See [Troubleshooting](docs/troubleshooting.md) for conflicts, incomplete discovery,
input inhibition, keyboard layouts and custom paths. See [How it works](docs/architecture.md)
for file changes and daemon behavior, and [Contributing](CONTRIBUTING.md) for tests.

Licensed under the [MIT License](LICENSE).
