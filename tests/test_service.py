"""Service generation and lifecycle checks without touching a real user manager."""
import argparse
import contextlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
from unittest.mock import patch

from test_bridge import b, FilesystemTest, FakeHypr


class UserService(FilesystemTest):
    def setUp(self):
        super().setUp()
        self.config = self.base / "config/hypr-obs"
        self.state = self.base / "state/hypr-obs"
        self.root = self.write("config/hypr/hyprland.conf", "# user config\n")
        self.args = argparse.Namespace(hypr_config=str(self.root), obs_config=None, obs_pid=None,
                                       profile=None, collection=None, interval=None, supervisor=None)
        for patcher in (patch.object(b, "paths", return_value=(self.config, self.state)),
                        patch.object(b, "Hyprland", return_value=FakeHypr()),
                        patch.object(b, "require_desktop_user")):
            patcher.start()
            self.addCleanup(patcher.stop)
        self.manager = patch.object(b, "systemctl", return_value=subprocess.CompletedProcess([], 0, "", ""))
        self.systemctl = self.manager.start()
        self.addCleanup(self.manager.stop)

    def enable(self, manager=True):
        with patch.object(b, "systemd_available", return_value=manager), \
             contextlib.redirect_stdout(io.StringIO()):
            return b.install(self.args)

    def control(self, name):
        args = argparse.Namespace(command=name, settings=None, from_session=False)
        with patch.dict(os.environ, {}, clear=True), contextlib.redirect_stdout(io.StringIO()):
            return b.control_runtime(args)

    def test_enable_installs_restartable_user_service(self):
        self.assertEqual(self.enable(), 0)
        unit = b.unit_path(self.config)
        text = unit.read_text()
        self.assertIn("Restart=always\nRestartSec=3", text)
        self.assertIn("WantedBy=default.target", text)
        self.assertIn("--supervised", text)
        self.assertIn("StandardOutput=journal", text)
        self.assertIn(str(self.config / "settings.json"), text)
        self.assertEqual([c.args[0] for c in self.systemctl.call_args_list], ["daemon-reload", "enable", "restart"])
        self.assertEqual(self.systemctl.call_args_list[1].args, ("enable", str(unit)))
        self.assertEqual(b.read_json(self.config / "settings.json")["supervisor"], "systemd")
        self.assertIn("start", (self.config / "startup.conf").read_text())
        self.assertNotIn(" daemon ", (self.config / "startup.conf").read_text())

    def test_auto_falls_back_without_a_user_manager(self):
        with patch.object(b.subprocess, "Popen") as spawn:
            self.assertEqual(self.enable(manager=False), 0)
        self.assertTrue(spawn.called)
        self.assertEqual(b.read_json(self.config / "settings.json")["supervisor"], "process")
        self.assertFalse(b.unit_path(self.config).exists())
        self.systemctl.assert_not_called()

    def test_lua_autostart_does_not_undo_a_stop_on_config_reload(self):
        with patch.object(b, "Hyprland", return_value=FakeHypr("lua")):
            self.enable()
        text = (self.config / "startup.lua").read_text()
        self.assertIn('hl.on("hyprland.start", function()', text)
        self.assertIn("hl.exec_cmd(", text)

    def test_explicit_systemd_reports_unavailable_manager(self):
        self.args.supervisor = "systemd"
        with self.assertRaisesRegex(b.BridgeError, "user manager is unavailable"):
            self.enable(manager=False)
        self.assertEqual(self.root.read_text(), "# user config\n")
        self.assertFalse((self.config / "settings.json").exists())

    def test_foreign_unit_is_preserved(self):
        unit = b.unit_path(self.config)
        unit.parent.mkdir(parents=True)
        unit.write_text("# unrelated user unit\n")
        with self.assertRaisesRegex(b.BridgeError, "unmanaged service"):
            self.enable()
        self.assertEqual(unit.read_text(), "# unrelated user unit\n")
        self.systemctl.assert_not_called()

    def test_unit_argument_quoting(self):
        quoted = b.unit_quote('/a path/with"quote/$value/100%')
        self.assertEqual(quoted, '"/a path/with\\"quote/$$value/100%%"')
        with self.assertRaises(b.BridgeError):
            b.unit_quote("/bad\nExecStart=oops")

    def test_start_stop_restart_use_user_service_manager(self):
        self.enable()
        self.systemctl.reset_mock()
        for name in ("start", "stop", "restart"):
            self.assertEqual(self.control(name), 0)
        self.assertEqual([c.args for c in self.systemctl.call_args_list],
                         [("start", b.SERVICE), ("stop", b.SERVICE), ("restart", b.SERVICE)])
        self.assertTrue((self.config / "settings.json").exists())
        self.assertIn(b.BEGIN, self.root.read_text())

    def test_start_refreshes_hyprland_session(self):
        self.enable()
        self.systemctl.reset_mock()
        with patch.dict(os.environ, {"HYPRLAND_INSTANCE_SIGNATURE": "test_123", "WAYLAND_DISPLAY": "wayland-9"}):
            b.control_runtime(argparse.Namespace(command="start", settings=None, from_session=True))
        saved = b.read_json(self.state / "session.json")
        self.assertEqual(saved["HYPRLAND_INSTANCE_SIGNATURE"], "test_123")
        self.assertEqual(saved["WAYLAND_DISPLAY"], "wayland-9")

    def test_a_new_session_restarts_an_old_service_attachment(self):
        self.enable()
        b.save_json(self.state / "status.json", {"session": "previous-session", "daemon_pid": 0})
        self.systemctl.reset_mock()
        with patch.dict(os.environ, {"HYPRLAND_INSTANCE_SIGNATURE": "test_123"}), \
             contextlib.redirect_stdout(io.StringIO()):
            b.control_runtime(argparse.Namespace(command="start", settings=None, from_session=True))
        self.assertEqual(self.systemctl.call_args.args, ("restart", b.SERVICE))

    def test_disable_stops_service_before_removing_its_program(self):
        self.enable()
        self.systemctl.reset_mock()
        def inspect(*arguments, **_kwargs):
            if arguments == ("disable", "--now", b.SERVICE):
                self.assertTrue((self.config / "hypr-obs.py").exists())
                self.assertTrue((self.config / "settings.json").exists())
            return subprocess.CompletedProcess([], 0, "", "")
        self.systemctl.side_effect = inspect
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(b.disable(None), 0)
        self.assertEqual(self.systemctl.call_args_list[0].args, ("disable", "--now", b.SERVICE))
        self.assertFalse(b.unit_path(self.config).exists())
        self.assertFalse((self.config / "settings.json").exists())
        self.assertFalse((self.state / "session.json").exists())
        self.assertEqual(self.root.read_text(), "# user config\n")

    def test_failed_new_service_enable_rolls_back_hook_and_unit(self):
        def fail_restart(*arguments, **_kwargs):
            if arguments == ("restart", b.SERVICE):
                raise b.BridgeError("simulated service failure")
            return subprocess.CompletedProcess([], 0, "", "")
        self.systemctl.side_effect = fail_restart
        with self.assertRaisesRegex(b.BridgeError, "simulated service failure"):
            self.enable()
        self.assertEqual(self.root.read_text(), "# user config\n")
        self.assertFalse(b.unit_path(self.config).exists())
        self.assertFalse((self.config / "settings.json").exists())
        self.assertIn(("disable", b.SERVICE), [c.args for c in self.systemctl.call_args_list])

    def test_switching_to_process_backend_removes_service(self):
        self.enable()
        self.args.supervisor = "process"
        self.systemctl.reset_mock()
        with patch.object(b.subprocess, "Popen"):
            self.enable(manager=False)
        self.assertFalse(b.unit_path(self.config).exists())
        self.assertEqual(b.read_json(self.config / "settings.json")["supervisor"], "process")
        self.assertIn(("stop", b.SERVICE), [c.args for c in self.systemctl.call_args_list])
        self.assertIn(("disable", b.SERVICE), [c.args for c in self.systemctl.call_args_list])
        self.assertEqual(self.root.read_text().count(b.BEGIN), 1)

    def test_status_includes_service_and_waiting_state(self):
        self.enable()
        b.save_json(self.state / "status.json", {"daemon_pid": 0, "phase": "waiting_for_hyprland",
                                               "message": "No desktop yet", "instances": [], "forwarded": []})
        self.systemctl.return_value = subprocess.CompletedProcess([], 0, "ActiveState=active\nSubState=running\nMainPID=123\nNRestarts=2\n", "")
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(b.show_status(argparse.Namespace(json=True)), 0)
        status = json.loads(output.getvalue())
        self.assertTrue(status["running"])
        self.assertEqual(status["phase"], "waiting_for_hyprland")
        self.assertEqual(status["service"]["NRestarts"], "2")

    def test_service_logs_stream_through_journalctl(self):
        self.enable()
        with patch.object(b.shutil, "which", return_value="/usr/bin/journalctl"), \
             patch.object(b.subprocess, "run", return_value=subprocess.CompletedProcess([], 0)) as run:
            self.assertEqual(b.logs(argparse.Namespace(settings=None, lines=20, follow=True)), 0)
        self.assertIn("--follow", run.call_args.args[0])
        self.assertIn("--unit=hypr-obs.service", run.call_args.args[0])


class ForegroundDefaults(FilesystemTest):
    def test_console_entry_point_worker_can_be_identified(self):
        record = {"daemon_pid": 123, "script": "/venv/lib/hypr_obs.py", "launcher": "/venv/bin/hypr-obs"}
        with patch.object(b, "proc_args", return_value=["python3", "/venv/bin/hypr-obs", "daemon"]):
            self.assertEqual(b.running_daemon(record), 123)

    def test_daemon_no_longer_requires_a_settings_argument(self):
        with patch.object(b, "daemon", return_value=0) as daemon:
            self.assertEqual(b.main(["daemon"]), 0)
        self.assertIsNone(daemon.call_args.args[0].settings)

    def test_missing_settings_gives_actionable_message(self):
        with patch.object(b, "paths", return_value=(self.base / "config", self.base / "state")), \
             self.assertRaisesRegex(b.BridgeError, "Run hypr-obs enable"):
            b.resolve_settings(argparse.Namespace(settings=None))

    def test_default_and_explicit_settings_paths(self):
        path = self.write("config/settings.json", '{"state_dir":"/tmp/test"}')
        with patch.object(b, "paths", return_value=(path.parent, self.base / "state")):
            self.assertEqual(b.resolve_settings(argparse.Namespace(settings=None))[0], path)
        self.assertEqual(b.resolve_settings(argparse.Namespace(settings=str(path)))[0], path)

    def test_session_snapshot_contains_only_display_variables(self):
        state = self.base / "state"
        with patch.dict(os.environ, {"WAYLAND_DISPLAY": "wayland-7", "UNRELATED_TOKEN": "not-for-session-file"}):
            b.remember_session(FakeHypr(), state)
        values = b.read_json(state / "session.json")
        self.assertNotIn("UNRELATED_TOKEN", values)
        self.assertEqual(values["HYPRLAND_INSTANCE_SIGNATURE"], "test_123")
        self.assertEqual((state / "session.json").stat().st_mode & 0o777, 0o600)

    def test_session_refresh_does_not_import_arbitrary_environment(self):
        state = self.base / "state"
        b.save_json(state / "session.json", {"WAYLAND_DISPLAY": "wayland-new", "UNRELATED_TOKEN": "ignore"})
        with patch.dict(os.environ, {}, clear=True):
            b.refresh_session(state)
            self.assertEqual(os.environ["WAYLAND_DISPLAY"], "wayland-new")
            self.assertNotIn("UNRELATED_TOKEN", os.environ)

    def test_session_refresh_drops_stale_display_values(self):
        state = self.base / "state"
        b.save_json(state / "session.json", {"HYPRLAND_INSTANCE_SIGNATURE": "new", "PATH": "/custom/bin"})
        with patch.dict(os.environ, {"DISPLAY": ":old", "WAYLAND_DISPLAY": "old"}, clear=True):
            b.refresh_session(state)
            self.assertNotIn("DISPLAY", os.environ)
            self.assertNotIn("WAYLAND_DISPLAY", os.environ)
            self.assertEqual(os.environ["PATH"], "/custom/bin")
