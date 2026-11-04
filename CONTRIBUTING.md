# Contributing

Use Python 3.9 or newer on Linux. Runtime and test code use only the standard
library. Keep changes compatible with both supported configuration providers.

```sh
python3 -m unittest discover -s tests -v
sh -n install.sh
python3 -m pip wheel --no-deps .
```

Run `python3 hypr_obs.py doctor` from a Hyprland terminal for read-only discovery.
`python3 hypr_obs.py enable` writes a startup hook and registers runtime binds;
use an isolated desktop/test account when developing changes to installation.

Tests use temporary directories and a simulated `hyprctl`. Daemon tests use an
event socket when permitted; otherwise they exercise the periodic repair path.
They do not establish that Qt receives an actual physical keyboard event.

For a live verification report, include:

- Linux distribution, Hyprland version and Lua/Hyprlang config type.
- OBS version, packaging and native Wayland/XWayland status.
- Whether Aitum Stream Suite is active.
- Whether a test hotkey works focused, on another workspace, after moving or
  restarting OBS, after saving a changed shortcut, and after `hyprctl reload`.
- Any conflict or partial-discovery report from `hypr-obs doctor`/`status`.

Use a harmless test scene/recording setup. Do not publish full OBS profiles or
service configuration files; hotkey-only examples are sufficient for parsing bugs.

Preserve unrelated user configuration. Never replace a complete parent config
with a generated template, override a rice shortcut silently, or choose an
ambiguous OBS collection by modification time. Add a regression test for a real
parsing, install, upgrade or daemon behavior change.
