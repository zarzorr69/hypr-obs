"""Standalone command installation, removal, and prototype upgrade checks."""
import argparse
import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

from test_bridge import b, FilesystemTest, FakeHypr


class CommandInstall(FilesystemTest):
    def setUp(self):
        super().setUp()
        self.config = self.base / "config/hypr-obs"
        self.state = self.base / "state/hypr-obs"
        self.bin_dir = self.base / "bin"
        self.args = argparse.Namespace(bin_dir=str(self.bin_dir), no_enable=True,
                                       hypr_config=None, obs_config=None, obs_pid=None,
                                       profile=None, collection=None, interval=None)
        self.path_patch = patch.object(b, "paths", return_value=(self.config, self.state))
        self.root_patch = patch.object(b, "require_desktop_user")
        self.path_patch.start()
        self.root_patch.start()
        self.addCleanup(self.path_patch.stop)
        self.addCleanup(self.root_patch.stop)

    def setup_command(self):
        with contextlib.redirect_stdout(io.StringIO()):
            return b.setup(self.args)

    def test_installs_executable_command_and_receipt(self):
        self.assertEqual(self.setup_command(), 0)
        command = self.bin_dir / "hypr-obs"
        self.assertEqual(command.stat().st_mode & 0o777, 0o755)
        receipt = b.read_json(self.config / "command.json")
        self.assertEqual(receipt["path"], str(command))
        self.assertEqual(receipt["sha256"], hashlib.sha256(command.read_bytes()).hexdigest())
        result = subprocess.run([str(command), "--version"], text=True, capture_output=True, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), b.VERSION)

    def test_reinstall_updates_only_managed_copy(self):
        self.setup_command()
        self.assertEqual(self.setup_command(), 0)
        self.assertEqual(len(list(self.bin_dir.iterdir())), 1)

    def test_unrelated_existing_command_is_untouched(self):
        command = self.write("bin/hypr-obs", "#!/bin/sh\necho unrelated\n")
        before = command.read_bytes()
        with self.assertRaisesRegex(b.BridgeError, "different or modified"):
            self.setup_command()
        self.assertEqual(command.read_bytes(), before)

    def test_existing_symlink_is_untouched(self):
        original = self.write("user-tool", "original")
        self.bin_dir.mkdir()
        (self.bin_dir / "hypr-obs").symlink_to(original)
        with self.assertRaisesRegex(b.BridgeError, "symlink"):
            self.setup_command()
        self.assertTrue((self.bin_dir / "hypr-obs").is_symlink())
        self.assertEqual(original.read_text(), "original")

    def test_modified_managed_copy_is_not_overwritten_or_removed(self):
        self.setup_command()
        command = self.bin_dir / "hypr-obs"
        with command.open("a") as handle:
            handle.write("\n# user changes\n")
        with self.assertRaises(b.BridgeError):
            self.setup_command()
        with contextlib.redirect_stdout(io.StringIO()), self.assertRaisesRegex(b.BridgeError, "changed outside"):
            b.uninstall(None)
        self.assertTrue(command.is_file())

    def test_disable_keeps_command_and_receipt(self):
        self.setup_command()
        with contextlib.redirect_stdout(io.StringIO()):
            b.disable(None)
        self.assertTrue((self.bin_dir / "hypr-obs").is_file())
        self.assertTrue((self.config / "command.json").is_file())

    def test_bare_command_enables_without_flags(self):
        with patch.object(b, "install", return_value=0) as enable:
            self.assertEqual(b.main([]), 0)
        self.assertEqual(enable.call_args.args[0].command, "enable")
        self.assertIsNone(enable.call_args.args[0].xwayland_dispatcher)

    def test_remove_command_dispatches_to_cleanup(self):
        with patch.object(b, "remove", return_value=0) as remove:
            self.assertEqual(b.main(["remove"]), 0)
        remove.assert_called_once()

    def test_remove_purges_only_managed_files(self):
        self.setup_command()
        self.write("state/hypr-obs/status.json", "{}")
        self.write("state/hypr-obs/bridge.log", "log")
        self.write("state/hypr-obs/worker.lock", "")
        self.write("state/hypr-obs/session-0123456789abcdef.lock", "")
        self.write("state/hypr-obs/hyprland-before-0123456789abcdef.conf", "backup")
        foreign = self.write("state/hypr-obs/keep-me.txt", "user data")
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(b.remove(None), 0)
        self.assertFalse((self.bin_dir / "hypr-obs").exists())
        self.assertFalse((self.state / "bridge.log").exists())
        self.assertFalse((self.state / "hyprland-before-0123456789abcdef.conf").exists())
        self.assertTrue(foreign.exists())

    def test_remove_cleans_state_dir_when_only_managed_files_exist(self):
        self.setup_command()
        self.write("state/hypr-obs/status.json", "{}")
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(b.remove(None), 0)
        self.assertFalse(self.state.exists())

    def test_uninstall_removes_only_managed_command(self):
        self.setup_command()
        other = self.write("bin/another-command", "not ours")
        backup = self.write("state/hypr-obs/backup.conf", "backup")
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(b.uninstall(None), 0)
        self.assertFalse((self.bin_dir / "hypr-obs").exists())
        self.assertFalse((self.config / "command.json").exists())
        self.assertTrue(other.exists())
        self.assertTrue(backup.exists())

    def test_bare_enable_uses_auto_even_after_older_saved_pass_setting(self):
        self.setup_command()
        # Installation settings are normally built inside install(); verify
        # its default selection without creating any real daemon.
        root = self.write("hyprland.conf", "# user config\n")
        self.write("config/hypr-obs/settings.json",
                   json.dumps({"version": "0.2.1", "xwayland_dispatcher": "pass",
                               "token": "oldtoken", "hypr_config": str(root),
                               "supervisor": "process"}))
        args = argparse.Namespace(hypr_config=str(root), obs_config=None, obs_pid=None,
                                  profile=None, collection=None, interval=None,
                                  supervisor="process", xwayland_dispatcher=None)
        with patch.object(b, "Hyprland", return_value=FakeHypr()), \
             patch.object(b, "start_daemon"), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(b.install(args), 0)
        settings = b.read_json(self.config / "settings.json")
        self.assertEqual(settings["xwayland_dispatcher"], "auto")

    def test_enable_failure_leaves_a_usable_installed_command(self):
        self.args.no_enable = False
        with patch.object(b, "install", side_effect=b.BridgeError("no compositor")), \
             contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(b.setup(self.args), 1)
        self.assertTrue((self.bin_dir / "hypr-obs").exists())

    def test_command_install_does_not_require_hyprland_when_disabled(self):
        with patch.object(b, "Hyprland", side_effect=AssertionError("must not query compositor")):
            self.assertEqual(self.setup_command(), 0)

    def test_setup_enables_by_default(self):
        self.args.no_enable = False
        with patch.object(b, "install", return_value=0) as enable:
            self.assertEqual(self.setup_command(), 0)
        enable.assert_called_once_with(self.args)

    def test_moving_an_existing_install_requires_uninstall(self):
        self.setup_command()
        self.args.bin_dir = str(self.base / "different-bin")
        with self.assertRaisesRegex(b.BridgeError, "elsewhere"):
            self.setup_command()
        self.assertFalse((self.base / "different-bin/hypr-obs").exists())


class LegacyUpgrade(FilesystemTest):
    def test_existing_prototype_paths_are_reused(self):
        base = self.base / "config"
        legacy = base / "obs-hotkey-bridge"
        self.write("config/obs-hotkey-bridge/settings.json", "{}")
        with patch.dict(os.environ, {"XDG_CONFIG_HOME": str(base), "XDG_STATE_HOME": str(self.base / "state")}):
            self.assertEqual(b.paths(), (legacy, self.base / "state/obs-hotkey-bridge"))

    def test_fresh_install_uses_hypr_obs_paths(self):
        with patch.dict(os.environ, {"XDG_CONFIG_HOME": str(self.base / "config"), "XDG_STATE_HOME": str(self.base / "state")}):
            self.assertEqual(b.paths(), (self.base / "config/hypr-obs", self.base / "state/hypr-obs"))

    def test_receipt_keeps_legacy_location_after_disabling(self):
        legacy = self.write("config/obs-hotkey-bridge/command.json", "{}").parent
        with patch.dict(os.environ, {"XDG_CONFIG_HOME": str(self.base / "config")}):
            self.assertEqual(b.paths()[0], legacy)

    def test_prototype_upgrade_retains_one_hook_and_existing_preferences(self):
        config, state = self.base / "config/obs-hotkey-bridge", self.base / "state/obs-hotkey-bridge"
        root = self.write("hyprland.conf", "# user's config\n")
        block = b.bootstrap_block("hyprlang", config / "startup.conf")
        _, added = b.install_hook(root, block, "hyprlang")
        b.save_json(config / "settings.json", {"version": "1.0.1", "token": "originaltoken",
            "hypr_config": str(root), "state_dir": str(state), "added_hook": added.decode(),
            "interval": 5.0, "obs_config": "/custom/obs-studio"})
        self.write("config/obs-hotkey-bridge/obs-hotkey-bridge.py", "# old managed cache\n")
        args = argparse.Namespace(hypr_config=str(root), obs_config=None, obs_pid=None,
                                  profile=None, collection=None, interval=None)
        with patch.object(b, "paths", return_value=(config, state)), \
             patch.object(b, "Hyprland", return_value=FakeHypr()), \
             patch.object(b, "require_desktop_user"), \
             patch.object(b, "start_daemon"), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(b.install(args), 0)
            settings = b.read_json(config / "settings.json")
            self.assertEqual(settings["token"], "originaltoken")
            self.assertEqual(settings["interval"], 5.0)
            self.assertEqual(settings["obs_config"], "/custom/obs-studio")
            self.assertEqual(root.read_text().count(b.BEGIN), 1)
            self.assertIn("hypr-obs.py", (config / "startup.conf").read_text())
            b.disable(None)
        self.assertEqual(root.read_text(), "# user's config\n")
        self.assertFalse((config / "obs-hotkey-bridge.py").exists())


if __name__ == "__main__":
    unittest.main()
