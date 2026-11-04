import argparse
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / "hypr_obs.py"
spec = importlib.util.spec_from_file_location("bridge", SCRIPT)
b = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = b
spec.loader.exec_module(b)


def binding(key="OBS_KEY_F9", **kwargs):
    return {"key": key, **kwargs}


def window(pid=90, address="0xabc", **kwargs):
    return {"pid": pid, "address": address, "class": "com.obsproject.Studio",
            "title": "OBS 32.0.1 - Profile: Work - Scenes: Gaming", "size": [1000, 700],
            "workspace": {"id": 7, "name": "7"}, "xwayland": False, **kwargs}


class FakeHypr:
    pid = 123
    signature = "test_123"
    pass_table = True

    def __init__(self, backend="hyprlang", entries=None, clients=None):
        self.backend = backend
        self.entries = entries or []
        self.clients = clients or []
        self.operations = []

    def query(self, command):
        if command == "binds":
            return self.entries
        if command == "clients":
            return self.clients
        raise AssertionError(command)

    def mutate(self, *args):
        self.operations.append(args)


class FilesystemTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.base = Path(self.temporary.name)
        self.addCleanup(self.temporary.cleanup)

    def write(self, path, text):
        path = self.base / path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def obs(self):
        self.write("config/obs-studio/user.ini", "[Basic]\nProfileDir=Work\nSceneCollectionFile=Gaming\n")
        ini = "[General]\nName=Work\n[Hotkeys]\n"
        ini += "OBSBasic.StartRecording=" + json.dumps({"bindings": [binding(control=True, shift=True)]}) + "\n"
        ini += "OBSBasic.StopRecording=" + json.dumps({"bindings": [binding(control=True, shift=True)]}) + "\n"
        ini += "ReplayBuffer=" + json.dumps({"ReplayBuffer.Save": [binding("OBS_KEY_F10")]}) + "\n"
        self.write("config/obs-studio/basic/profiles/Work/basic.ini", ini)
        self.write("config/obs-studio/basic/profiles/Inactive/basic.ini",
                   "[Hotkeys]\nIgnored=" + json.dumps({"bindings": [binding("OBS_KEY_F12")]}) + "\n")
        scene = {"name": "Gaming", "sources": [
            {"name": "Mic", "hotkeys": {"libobs.push-to-talk": [binding("OBS_KEY_MOUSE5")]}},
            {"name": "Scene 2", "hotkeys": {"OBSBasic.SelectScene": [binding("OBS_KEY_F11")]}},
        ], "quick_transitions": [{"name": "Cut", "hotkeys": [binding("OBS_KEY_F8")]}]}
        self.write("config/obs-studio/basic/scenes/Gaming.json", json.dumps(scene))
        self.write("config/obs-studio/basic/scenes/Inactive.json",
                   json.dumps({"name": "Inactive", "hotkeys": {"Ignored": [binding("OBS_KEY_F7")]}}))
        return self.base / "config/obs-studio"


class Keys(unittest.TestCase):
    def test_ctrl_shift(self):
        self.assertEqual(str(b.convert_binding(binding(control=True, shift=True))), "SHIFT + CTRL + F9")

    def test_all_modifiers(self):
        self.assertEqual(b.convert_binding(binding(shift=True, control=True, alt=True, command=True)).mods, 77)

    def test_xkb_aliases_and_case(self):
        self.assertEqual(b.KEY_NAMES.canonical("A"), b.KEY_NAMES.canonical("a"))
        if b.KEY_NAMES.lib:
            self.assertEqual(b.KEY_NAMES.canonical("Page_Up"), b.KEY_NAMES.canonical("Prior"))

    def test_keypad_enter(self):
        self.assertEqual(b.convert_binding(binding("OBS_KEY_ENTER")).key, "KP_Enter")
        self.assertEqual(b.convert_binding(binding("OBS_KEY_RETURN")).key, "Return")

    def test_mouse(self):
        self.assertEqual(b.convert_binding(binding("OBS_KEY_MOUSE4")).key, "mouse:275")
        self.assertEqual(b.convert_binding(binding("OBS_KEY_MOUSE5")).key, "mouse:276")
        with self.assertRaises(b.BridgeError):
            b.convert_binding(binding("OBS_KEY_MOUSE1"))

    def test_keypad_and_punctuation(self):
        self.assertEqual(b.convert_binding(binding("OBS_KEY_NUM0")).key, "KP_0")
        self.assertEqual(b.convert_binding(binding("OBS_KEY_COMMA")).key, "comma")
        self.assertEqual(b.convert_binding(binding("OBS_KEY_PLUS")).key, "plus")

    def test_empty(self):
        self.assertIsNone(b.convert_binding(binding("OBS_KEY_NONE")))

    def test_modifier_only_is_reported(self):
        with self.assertRaisesRegex(b.BridgeError, "Modifier-only"):
            b.convert_binding(binding("OBS_KEY_NONE", control=True))

    def test_input_cannot_be_config_code(self):
        for key in ('OBS_KEY_F9,exec,rm', 'OBS_KEY_F9;exec bad', 'OBS_KEY_UNKNOWN'):
            with self.assertRaises(b.BridgeError):
                b.convert_binding(binding(key))

    def test_invalid_boolean(self):
        with self.assertRaises(b.BridgeError):
            b.convert_binding(binding(control="false"))

    def test_media(self):
        self.assertEqual(b.convert_binding(binding("OBS_KEY_VK_VOLUME_DOWN")).key, "XF86AudioLowerVolume")


class OBS(FilesystemTest):
    def test_active_profile_and_all_scene_hotkeys(self):
        root = self.obs()
        saved = b.load_hotkeys(root)
        self.assertEqual(saved.profile, "Work")
        self.assertEqual(saved.collection, "Gaming")
        self.assertEqual({chord.key for chord in saved.hotkeys}, {"F8", "F9", "F10", "F11", "mouse:276"})
        record = next(actions for chord, actions in saved.hotkeys.items() if chord.key == "F9")
        self.assertEqual(len(record), 2)  # one forwarded physical press for a start/stop pair

    def test_global_ini_older_obs(self):
        root = self.obs()
        (root / "user.ini").rename(root / "global.ini")
        self.assertEqual(b.load_hotkeys(root).profile, "Work")

    def test_profile_switch(self):
        root = self.obs()
        (root / "user.ini").write_text("[Basic]\nProfileDir=Inactive\nSceneCollectionFile=Inactive\n")
        saved = b.load_hotkeys(root)
        self.assertEqual({chord.key for chord in saved.hotkeys}, {"F7", "F12"})

    def test_ambiguous_profile_is_not_picked_by_mtime(self):
        root = self.obs()
        (root / "user.ini").write_text("[Basic]\nSceneCollectionFile=Gaming\n")
        with self.assertRaisesRegex(b.BridgeError, "active OBS profile"):
            b.load_hotkeys(root)

    def test_explicit_profile(self):
        root = self.obs()
        saved = b.load_hotkeys(root, profile="Inactive", collection="Inactive")
        self.assertEqual(saved.profile, "Inactive")
        self.assertEqual(saved.collection, "Inactive")

    def test_incomplete_scene_json_is_retryable(self):
        root = self.obs()
        (root / "basic/scenes/Gaming.json").write_text('{"sources":[')
        saved = b.load_hotkeys(root)
        self.assertTrue(saved.partial)
        self.assertEqual({chord.key for chord in saved.hotkeys}, {"F9", "F10"})
        self.assertIn("incomplete or invalid", saved.issues[0])

    def test_incomplete_binding_is_retryable(self):
        root = self.obs()
        (root / "basic/profiles/Work/basic.ini").write_text("[Hotkeys]\nRecording={\n")
        with self.assertRaisesRegex(b.BridgeError, "Incomplete saved hotkey"):
            b.load_hotkeys(root)

    def test_focus_setting_reported_without_modifying_obs(self):
        root = self.obs()
        path = root / "user.ini"
        with path.open("a") as handle:
            handle.write("[General]\nHotkeyFocusType=DisableHotkeysOutOfFocus\n")
        before = path.read_bytes()
        self.assertTrue(b.load_hotkeys(root).issues)
        self.assertEqual(before, path.read_bytes())

    def test_unknown_keys_reported(self):
        root = self.obs()
        profile = root / "basic/profiles/Work/basic.ini"
        with profile.open("a") as handle:
            handle.write('Unsupported={"bindings":[{"key":"OBS_KEY_NEW_FUTURE_KEY"}]}\n')
        saved = b.load_hotkeys(root)
        self.assertEqual(len(saved.hotkeys), 5)
        self.assertIn("OBS_KEY_NEW_FUTURE_KEY", saved.issues[0])

    def test_obs_33_location_overrides(self):
        root = self.obs()
        external = self.base / "external"
        external.mkdir()
        (root / "user.ini").rename(external / "user-temp.ini")
        (external / "obs-studio").mkdir()
        (external / "user-temp.ini").rename(external / "obs-studio/user.ini")
        (root / "global.ini").write_text("[Locations]\nConfiguration=" + str(external) + "\n")
        self.assertEqual(b.load_hotkeys(root).profile, "Work")

    def test_recent_obs_scene_collection_filename_includes_json(self):
        root = self.obs()
        (root / "user.ini").write_text("[Basic]\nProfileDir=Work\nSceneCollectionFile=Gaming.json\n")
        saved = b.load_hotkeys(root)
        self.assertEqual(saved.collection, "Gaming")
        self.assertFalse(saved.partial)
        self.assertIn("mouse:276", {chord.key for chord in saved.hotkeys})

    def test_explicit_collection_accepts_filename(self):
        saved = b.load_hotkeys(self.obs(), collection="Gaming.json")
        self.assertEqual(saved.collection, "Gaming")

    def test_stale_scene_filename_falls_back_to_display_name(self):
        root = self.obs()
        (root / "user.ini").write_text("[Basic]\nProfileDir=Work\nSceneCollectionFile=Old.json\nSceneCollection=Gaming\n")
        self.assertEqual(b.load_hotkeys(root).collection, "Gaming")

    def test_display_name_used_with_json_filename_rename(self):
        root = self.obs()
        (root / "basic/scenes/Gaming.json").rename(root / "basic/scenes/Gaming_2.json")
        (root / "user.ini").write_text("[Basic]\nProfileDir=Work\nSceneCollectionFile=Old.json\nSceneCollection=Gaming\n")
        self.assertEqual(b.load_hotkeys(root).collection, "Gaming_2")

    def test_ambiguous_scene_does_not_block_profile_shortcuts(self):
        root = self.obs()
        (root / "user.ini").write_text("[Basic]\nProfileDir=Work\nSceneCollectionFile=No-longer-exists.json\n")
        saved = b.load_hotkeys(root)
        self.assertTrue(saved.partial)
        self.assertEqual(saved.collection, "")
        self.assertEqual({chord.key for chord in saved.hotkeys}, {"F9", "F10"})
        self.assertEqual(saved.collection_candidates, ["Gaming.json", "Inactive.json"])

    def test_inactive_malformed_scene_does_not_block_name_lookup(self):
        root = self.obs()
        (root / "basic/scenes/Inactive.json").write_text('{')
        (root / "user.ini").write_text("[Basic]\nProfileDir=Work\nSceneCollection=Gaming\nSceneCollectionFile=Stale.json\n")
        self.assertEqual(b.load_hotkeys(root).collection, "Gaming")

    def test_explicit_missing_collection_is_an_error(self):
        with self.assertRaisesRegex(b.BridgeError, "Requested scene collection"):
            b.load_hotkeys(self.obs(), collection="Not-present")

    def aitum(self, root):
        data = {
            "start_all_outputs_hotkey": [binding("OBS_KEY_F13", control=True)],
            "stop_all_outputs_hotkey": [binding("OBS_KEY_F13", control=True)],
            "start_all_streams_hotkey": [binding("OBS_KEY_F14")],
            "start_all_recordings_hotkey": [binding("OBS_KEY_F15")],
            "outputs": [{"name": "Game Recording", "type": "record",
                         "start_hotkey": [binding("OBS_KEY_F16")],
                         "stop_hotkey": [binding("OBS_KEY_F16")],
                         "pause_hotkey": [binding("OBS_KEY_F17")],
                         "unpause_hotkey": [binding("OBS_KEY_F18")],
                         "split_hotkey": [binding("OBS_KEY_F19")],
                         "chapter_hotkey": [binding("OBS_KEY_F20")]},
                        {"name": "Backtrack", "type": "backtrack",
                         "extra_hotkey": [binding("OBS_KEY_F21")]}],
            "canvas": [{"name": "Vertical", "sources": [
                {"name": "Vertical Scene", "hotkeys": {"OBSBasic.SelectScene": [binding("OBS_KEY_F22")]}}
            ]}]
        }
        path = root / "basic/profiles/Work/aitum.json"
        path.write_text(json.dumps(data))
        return path

    def test_aitum_per_output_all_output_backtrack_and_canvas_keys(self):
        root = self.obs()
        path = self.aitum(root)
        before = path.read_bytes()
        saved = b.load_hotkeys(root)
        self.assertTrue(saved.aitum)
        keys = {chord.key for chord in saved.hotkeys}
        self.assertTrue({"F" + str(x) for x in range(13, 23)}.issubset(keys))
        group = next(v for chord, v in saved.hotkeys.items() if chord.key == "F16")
        self.assertEqual(len(group), 2)
        self.assertIn(str(path), saved.files)
        self.assertEqual(before, path.read_bytes())

    def test_aitum_keys_still_load_with_unresolved_scene_collection(self):
        root = self.obs()
        self.aitum(root)
        (root / "user.ini").write_text("[Basic]\nProfileDir=Work\nSceneCollectionFile=Missing.json\n")
        saved = b.load_hotkeys(root)
        self.assertTrue(saved.partial)
        self.assertTrue(saved.aitum)
        self.assertIn("F21", {chord.key for chord in saved.hotkeys})
        self.assertNotIn("F11", {chord.key for chord in saved.hotkeys})

    def test_aitum_changes_are_read_on_next_scan(self):
        root = self.obs()
        path = self.aitum(root)
        first = b.load_hotkeys(root)
        path.write_text(json.dumps({"outputs": [{"name": "Game", "start_hotkey": [binding("OBS_KEY_F23")]}]}))
        second = b.load_hotkeys(root)
        self.assertIn("F13", {chord.key for chord in first.hotkeys})
        self.assertIn("F23", {chord.key for chord in second.hotkeys})
        self.assertNotIn("F13", {chord.key for chord in second.hotkeys})

    def test_aitum_invalid_json_leaves_standard_hotkeys_available(self):
        root = self.obs()
        path = self.aitum(root)
        path.write_text('{"outputs":')
        saved = b.load_hotkeys(root)
        self.assertTrue(saved.partial)
        self.assertTrue(saved.aitum)
        self.assertIn("Aitum hotkeys pending", saved.issues[0])
        self.assertIn("F9", {chord.key for chord in saved.hotkeys})


class Discovery(FilesystemTest):
    def test_custom_parent_from_process_not_rice_name(self):
        root = self.write("Ryoku/custom.lua", 'require("ryoku")\n')
        hypr = FakeHypr("lua")
        with patch.object(b, "proc_args", return_value=["Hyprland", "--config", str(root)]):
            self.assertEqual(b.detect_config(hypr), root)

    def test_custom_equal_and_short_config_options(self):
        root = self.write("HyDE/main.conf", "# my config\n")
        for args in (["Hyprland", "--config=" + str(root)], ["Hyprland", "-c" + str(root)]):
            with patch.object(b, "proc_args", return_value=args):
                self.assertEqual(b.detect_config(FakeHypr()), root)

    def test_relative_config_resolves_against_hyprland_cwd(self):
        root = self.write("Rice/root.conf", "# config\n")
        with patch.object(b, "proc_args", return_value=["Hyprland", "-c", "root.conf"]), \
             patch.object(b, "proc_link", return_value=root.parent):
            self.assertEqual(b.detect_config(FakeHypr()), root)

    def test_default_lua_and_hyprlang(self):
        for backend, suffix in (("lua", "lua"), ("hyprlang", "conf")):
            root = self.write("config/hypr/hyprland." + suffix, "-- config\n")
            with patch.object(b, "proc_args", return_value=["Hyprland"]), \
                 patch.object(b, "proc_env", return_value={"XDG_CONFIG_HOME": str(root.parent.parent)}):
                self.assertEqual(b.detect_config(FakeHypr(backend)), root)

    def test_symlink_parent_resolved(self):
        root = self.write("dotfiles/hyprland.conf", "# my rice\n")
        link = self.base / "linked.conf"
        link.symlink_to(root)
        self.assertEqual(b.detect_config(FakeHypr(), str(link)), root)

    def test_flatpak_uses_process_xdg_not_stale_native_profile(self):
        flat = self.base / "flatpak/config/obs-studio"
        self.write("flatpak/config/obs-studio/user.ini", "[Basic]\n")
        native = self.obs()
        with patch.object(b, "proc_env", return_value={"XDG_CONFIG_HOME": str(flat.parent), "HOME": str(self.base)}), \
             patch.object(b, "proc_args", return_value=["/app/bin/obs"]):
            self.assertEqual(b.obs_root(window()), flat)
            self.assertNotEqual(b.obs_root(window()), native)

    def test_snap_config_uses_process_env(self):
        root = self.write("snap/obs-studio/44/.config/obs-studio/user.ini", "[Basic]\n").parent
        with patch.object(b, "proc_env", return_value={"SNAP_USER_DATA": str(self.base / "snap/obs-studio/44")}), \
             patch.object(b, "proc_args", return_value=["obs"]):
            self.assertEqual(b.obs_root(window()), root)

    def test_declared_flatpak_does_not_choose_inherited_host_xdg(self):
        self.obs()
        flat = self.write("home/.var/app/com.obsproject.Studio/config/obs-studio/user.ini", "[Basic]\n").parent
        with patch.object(b.Path, "home", return_value=self.base / "home"), \
             patch.object(b, "proc_env", return_value={"FLATPAK_ID": "com.obsproject.Studio",
                                                       "XDG_CONFIG_HOME": str(self.base / "home/.config")}), \
             patch.object(b, "proc_args", return_value=["/app/bin/obs"]):
            self.assertEqual(b.obs_root(window()), flat)

    def test_flatpak_info_identifies_package_when_environment_is_incomplete(self):
        self.write("proc/90/root/.flatpak-info", "[Application]\nname=com.obsproject.Studio\n")
        flat = self.write("home/.var/app/com.obsproject.Studio/config/obs-studio/user.ini", "[Basic]\n").parent
        with patch.object(b, "PROC", self.base / "proc"), \
             patch.object(b.Path, "home", return_value=self.base / "home"), \
             patch.object(b, "proc_env", return_value={"HOME": str(self.base / "home")}), \
             patch.object(b, "proc_args", return_value=["/app/bin/obs"]):
            self.assertEqual(b.obs_root(window()), flat)

    def test_moving_workspaces_keeps_same_target(self):
        one = window(workspace={"id": 1})
        two = window(workspace={"id": 8})
        self.assertEqual(b.obs_client_groups([one])[0]["address"],
                         b.obs_client_groups([two])[0]["address"])

    def test_main_window_over_settings_dialog_or_projector(self):
        main = window(size=[900, 600])
        dialog = window(address="0xdef", title="Settings", size=[1000, 700])
        projector = window(address="0x123", title="Fullscreen Projector", size=[1920, 1080])
        self.assertEqual(b.obs_client_groups([dialog, projector, main])[0]["address"], "0xabc")

    def test_other_app_title_cannot_impersonate_obs(self):
        with patch.object(b, "proc_link", return_value=Path("/usr/bin/firefox")):
            self.assertFalse(b.obs_client_groups([window(**{"class": "firefox"})]))

    def test_pid_selection(self):
        result = b.obs_client_groups([window(), window(pid=99, address="0xdef")], only_pid=99)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["pid"], 99)


class Runtime(unittest.TestCase):
    token = "testowner"

    def request(self, key="F9", address="0xabc", mods=5):
        return b.Request(b.Chord(mods, key), address, {"OBSBasic.StartRecording", "OBSBasic.StopRecording"})

    def entry(self, request, **kwargs):
        return {"key": request.chord.key, "keycode": 0, "modmask": request.chord.mods,
                "description": request.description(self.token), "dispatcher": "pass",
                "arg": "address:" + request.address, "submap": "", **kwargs}

    def test_legacy_runtime_bind_is_pass_to_exact_window(self):
        hypr = FakeHypr()
        result = b.reconcile(hypr, [self.request()], self.token)
        self.assertEqual(len(result["forwarded"]), 1)
        self.assertIn("keyword bindd SHIFT CTRL, F9, OBS Hotkey Bridge testowner", hypr.operations[0][1])
        self.assertTrue(hypr.operations[0][1].endswith(", pass, address:0xabc"))

    def test_lua_runtime_bind(self):
        hypr = FakeHypr("lua")
        b.reconcile(hypr, [self.request()], self.token)
        self.assertEqual(hypr.operations[0][0], "eval")
        self.assertIn('hl.bind("SHIFT + CTRL + F9",hl.dsp.pass({window="address:0xabc"})', hypr.operations[0][1])

    def test_older_lua_pass_constructor(self):
        hypr = FakeHypr("lua")
        hypr.pass_table = False
        b.reconcile(hypr, [self.request()], self.token)
        self.assertIn('hl.dsp.pass("address:0xabc")', hypr.operations[0][1])

    def test_repeat_reconcile_is_idempotent(self):
        request = self.request()
        hypr = FakeHypr(entries=[self.entry(request)])
        result = b.reconcile(hypr, [request], self.token)
        self.assertEqual(result["updates"], 0)
        self.assertFalse(hypr.operations)

    def test_rice_conflict_is_skipped_without_removing_it(self):
        hypr = FakeHypr(entries=[{"key": "F9", "modmask": 5, "description": "Ryoku screenshot", "dispatcher": "exec"}])
        result = b.reconcile(hypr, [self.request()], self.token)
        self.assertFalse(result["forwarded"])
        self.assertIn("Ryoku screenshot", result["issues"][0])
        self.assertFalse(hypr.operations)

    def test_submap_conflicts_also_protect_unbind(self):
        request = self.request()
        hypr = FakeHypr(entries=[self.entry(request), {"key": "F9", "modmask": 5, "submap": "resize", "dispatcher": "exec"}])
        result = b.reconcile(hypr, [], self.token)
        self.assertFalse(hypr.operations)
        self.assertIn("reload", result["issues"][0])

    def test_physical_key_conflicts_are_conservative(self):
        hypr = FakeHypr(entries=[{"key": "", "keycode": 82, "modmask": 5, "dispatcher": "exec"}])
        result = b.reconcile(hypr, [self.request()], self.token)
        self.assertIn("physical-key conflict", result["issues"][0])
        self.assertFalse(hypr.operations)

    def test_closed_obs_removes_own_bind(self):
        hypr = FakeHypr(entries=[self.entry(self.request())])
        b.reconcile(hypr, [], self.token)
        self.assertEqual(hypr.operations, [("--batch", "keyword submap reset ; keyword unbind SHIFT CTRL, F9")])

    def test_restart_retargets_new_address(self):
        hypr = FakeHypr(entries=[self.entry(self.request())])
        b.reconcile(hypr, [self.request(address="0xdef")], self.token)
        operations = hypr.operations[0][1]
        self.assertLess(operations.index("keyword unbind"), operations.index("keyword bindd"))
        self.assertIn("pass, address:0xdef", operations)

    def test_same_chord_in_two_obs_processes_is_ambiguous(self):
        hypr = FakeHypr()
        result = b.reconcile(hypr, [self.request(), self.request(address="0xdef")], self.token)
        self.assertFalse(hypr.operations)
        self.assertIn("multiple OBS instances", result["issues"][0])

    def test_read_only_preview(self):
        hypr = FakeHypr()
        result = b.reconcile(hypr, [self.request()], self.token, apply=False)
        self.assertEqual(len(result["forwarded"]), 1)
        self.assertFalse(hypr.operations)

    def test_exact_lua_handle_used_for_removal(self):
        hypr = FakeHypr("lua", entries=[self.entry(self.request())])
        b.reconcile(hypr, [], self.token)
        self.assertIn("h:remove()", hypr.operations[0][1])


class HookLifecycle(FilesystemTest):
    def test_conf_install_uninstall_preserves_missing_final_newline(self):
        root = self.write("hyprland.conf", "source = ./HyDE/keybindings.conf")
        original = root.read_bytes()
        block = b.bootstrap_block("hyprlang", self.base / "startup.conf")
        _, added = b.install_hook(root, block, "hyprlang")
        b.remove_hook(root, added.decode())
        self.assertEqual(root.read_bytes(), original)

    def test_lua_hook_precedes_top_level_return(self):
        root = self.write("hyprland.lua", 'return require("ryoku")\n')
        original = root.read_bytes()
        block = b.bootstrap_block("lua", self.base / "startup.lua")
        _, added = b.install_hook(root, block, "lua")
        self.assertLess(root.read_text().index("dofile("), root.read_text().index("return require"))
        b.remove_hook(root, added.decode())
        self.assertEqual(root.read_bytes(), original)

    def test_bom_preserved(self):
        root = self.write("hyprland.lua", '\ufeffreturn require("ryoku")\n')
        original = root.read_bytes()
        block = b.bootstrap_block("lua", self.base / "startup.lua")
        _, added = b.install_hook(root, block, "lua")
        self.assertTrue(root.read_bytes().startswith(b"\xef\xbb\xbf"))
        b.remove_hook(root, added.decode())
        self.assertEqual(root.read_bytes(), original)

    def test_symlink_not_replaced(self):
        root = self.write("repo/hyprland.conf", "# user config\n")
        root.chmod(0o640)
        link = self.base / "hyprland.conf"
        link.symlink_to(root)
        block = b.bootstrap_block("hyprlang", self.base / "startup.conf")
        b.install_hook(link, block, "hyprlang")
        self.assertTrue(link.is_symlink())
        self.assertIn(b.BEGIN, root.read_text())
        self.assertEqual(root.stat().st_mode & 0o777, 0o640)

    def test_reinstall_does_not_duplicate_hook(self):
        root = self.write("hyprland.conf", "# user config\n")
        block = b.bootstrap_block("hyprlang", self.base / "startup.conf")
        b.install_hook(root, block, "hyprlang")
        before = root.read_bytes()
        _, added = b.install_hook(root, block, "hyprlang")
        self.assertEqual(added, b"")
        self.assertEqual(root.read_bytes(), before)

    def test_uninstall_preserves_unrelated_concurrent_edits(self):
        root = self.write("hyprland.conf", "# user config\n")
        block = b.bootstrap_block("hyprlang", self.base / "startup.conf")
        _, added = b.install_hook(root, block, "hyprlang")
        with root.open("a") as handle:
            handle.write("bind = SUPER, X, exec, terminal\n")
        b.remove_hook(root, added.decode())
        self.assertEqual(root.read_text(), "# user config\nbind = SUPER, X, exec, terminal\n")

    def test_edited_hook_is_not_deleted(self):
        root = self.write("hyprland.conf", "# user config\n")
        block = b.bootstrap_block("hyprlang", self.base / "startup.conf")
        _, added = b.install_hook(root, block, "hyprlang")
        root.write_text(root.read_text().replace("startup.conf", "custom.conf"))
        before = root.read_bytes()
        with self.assertRaises(b.BridgeError):
            b.remove_hook(root, added.decode())
        self.assertEqual(root.read_bytes(), before)

    def test_install_and_uninstall_in_isolated_home(self):
        root = self.write("config/hypr/hyprland.conf", "# config\n")
        original = root.read_bytes()
        config, state = self.base / "config/obs-hotkey-bridge", self.base / "state/obs-hotkey-bridge"
        args = argparse.Namespace(hypr_config=str(root), obs_config=None, obs_pid=None,
                                  profile=None, collection=None, interval=3.0)
        with patch.object(b, "paths", return_value=(config, state)), \
             patch.object(b, "Hyprland", return_value=FakeHypr()), \
             patch.object(b.os, "geteuid", return_value=1000), \
             patch.object(b, "detect_config", return_value=root), \
             patch.object(b, "start_daemon") as start, contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(b.install(args), 0)
            self.assertTrue((config / "hypr-obs.py").is_file())
            self.assertTrue(start.called)
            b.install(args)
            self.assertEqual(root.read_text().count(b.BEGIN), 1)
            self.assertEqual(b.uninstall(None), 0)
        self.assertEqual(root.read_bytes(), original)
        self.assertFalse(config.exists())
        self.assertTrue(list(state.glob("hyprland-before-*")))

    def test_failed_install_restores_root(self):
        root = self.write("hyprland.conf", "# config\n")
        original = root.read_bytes()
        config, state = self.base / "config/obs-hotkey-bridge", self.base / "state/obs-hotkey-bridge"
        args = argparse.Namespace(hypr_config=str(root), obs_config=None, obs_pid=None,
                                  profile=None, collection=None, interval=3.0)
        with patch.object(b, "paths", return_value=(config, state)), \
             patch.object(b, "Hyprland", return_value=FakeHypr()), \
             patch.object(b.os, "geteuid", return_value=1000), \
             patch.object(b, "detect_config", return_value=root), \
             patch.object(b, "start_daemon", side_effect=OSError("simulated launch failure")):
            with self.assertRaises(OSError):
                b.install(args)
        self.assertEqual(root.read_bytes(), original)


if __name__ == "__main__":
    unittest.main()
