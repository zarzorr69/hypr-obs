#!/usr/bin/env python3
"""hypr-obs: automatic OBS hotkeys across Hyprland workspaces.

Python 3.9+; Linux, Hyprland and hyprctl. No pip packages, root, network,
OBS plugin, or OBS WebSocket access. See --help and the accompanying README.
"""
from __future__ import annotations

import argparse
import configparser
import ctypes
import ctypes.util
from dataclasses import dataclass, field
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import select
import shlex
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time
import uuid

VERSION = "0.2.0"
NAME = "hypr-obs"
LEGACY_NAME = "obs-hotkey-bridge"
SERVICE = "hypr-obs.service"
UNIT_MARKER = "# Managed by hypr-obs\n"
SESSION_VARIABLES = ("HYPRLAND_INSTANCE_SIGNATURE", "XDG_RUNTIME_DIR", "WAYLAND_DISPLAY", "DISPLAY", "PATH")
# Keep the prototype's markers and runtime descriptions compatible so upgrades
# can replace its daemon without leaving a second startup hook or duplicate binds.
BEGIN = "OBS-HOTKEY-BRIDGE BEGIN"
END = "OBS-HOTKEY-BRIDGE END"
PROC = Path("/proc")
MODIFIERS = (("shift", "SHIFT", 1), ("control", "CTRL", 4),
             ("alt", "ALT", 8), ("command", "SUPER", 64))
MAX_FILE = 64 * 1024 * 1024
# Public OBS key names paired with XKB key names (not physical scan codes).
KEY_MAP = {'OBS_KEY_0': '0',
 'OBS_KEY_1': '1',
 'OBS_KEY_2': '2',
 'OBS_KEY_3': '3',
 'OBS_KEY_4': '4',
 'OBS_KEY_5': '5',
 'OBS_KEY_6': '6',
 'OBS_KEY_7': '7',
 'OBS_KEY_8': '8',
 'OBS_KEY_9': '9',
 'OBS_KEY_A': 'A',
 'OBS_KEY_AACUTE': 'Aacute',
 'OBS_KEY_ACIRCUMFLEX': 'Acircumflex',
 'OBS_KEY_ACUTE': 'acute',
 'OBS_KEY_ADIAERESIS': 'Adiaeresis',
 'OBS_KEY_AE': 'AE',
 'OBS_KEY_AGRAVE': 'Agrave',
 'OBS_KEY_AMPERSAND': 'ampersand',
 'OBS_KEY_APOSTROPHE': 'apostrophe',
 'OBS_KEY_ARING': 'Aring',
 'OBS_KEY_ASCIICIRCUM': 'asciicircum',
 'OBS_KEY_ASCIITILDE': 'asciitilde',
 'OBS_KEY_ASTERISK': 'asterisk',
 'OBS_KEY_AT': 'at',
 'OBS_KEY_ATILDE': 'Atilde',
 'OBS_KEY_B': 'B',
 'OBS_KEY_BACKSLASH': 'backslash',
 'OBS_KEY_BACKSPACE': 'BackSpace',
 'OBS_KEY_BACKTAB': 'BackTab',
 'OBS_KEY_BAR': 'bar',
 'OBS_KEY_BRACELEFT': 'braceleft',
 'OBS_KEY_BRACERIGHT': 'braceright',
 'OBS_KEY_BRACKETLEFT': 'bracketleft',
 'OBS_KEY_BRACKETRIGHT': 'bracketright',
 'OBS_KEY_BROKENBAR': 'brokenbar',
 'OBS_KEY_C': 'C',
 'OBS_KEY_CANCEL': 'Cancel',
 'OBS_KEY_CCEDILLA': 'Ccedilla',
 'OBS_KEY_CEDILLA': 'cedilla',
 'OBS_KEY_CENT': 'cent',
 'OBS_KEY_CLEAR': 'Clear',
 'OBS_KEY_CODEINPUT': 'Codeinput',
 'OBS_KEY_COLON': 'colon',
 'OBS_KEY_COMMA': 'comma',
 'OBS_KEY_COPYRIGHT': 'copyright',
 'OBS_KEY_CURRENCY': 'currency',
 'OBS_KEY_D': 'D',
 'OBS_KEY_DEAD_ABOVEDOT': 'dead_abovedot',
 'OBS_KEY_DEAD_ABOVERING': 'dead_abovering',
 'OBS_KEY_DEAD_ACUTE': 'dead_acute',
 'OBS_KEY_DEAD_BELOWDOT': 'dead_belowdot',
 'OBS_KEY_DEAD_BREVE': 'dead_breve',
 'OBS_KEY_DEAD_CARON': 'dead_caron',
 'OBS_KEY_DEAD_CEDILLA': 'dead_cedilla',
 'OBS_KEY_DEAD_CIRCUMFLEX': 'dead_circumflex',
 'OBS_KEY_DEAD_DIAERESIS': 'dead_diaeresis',
 'OBS_KEY_DEAD_DOUBLEACUTE': 'dead_doubleacute',
 'OBS_KEY_DEAD_GRAVE': 'dead_grave',
 'OBS_KEY_DEAD_HOOK': 'dead_hook',
 'OBS_KEY_DEAD_HORN': 'dead_horn',
 'OBS_KEY_DEAD_IOTA': 'dead_iota',
 'OBS_KEY_DEAD_MACRON': 'dead_macron',
 'OBS_KEY_DEAD_OGONEK': 'dead_ogonek',
 'OBS_KEY_DEAD_SEMIVOICED_SOUND': 'dead_semivoiced_sound',
 'OBS_KEY_DEAD_TILDE': 'dead_tilde',
 'OBS_KEY_DEAD_VOICED_SOUND': 'dead_voiced_sound',
 'OBS_KEY_DEGREE': 'degree',
 'OBS_KEY_DELETE': 'Delete',
 'OBS_KEY_DIAERESIS': 'diaeresis',
 'OBS_KEY_DIVISION': 'division',
 'OBS_KEY_DOLLAR': 'dollar',
 'OBS_KEY_DOWN': 'Down',
 'OBS_KEY_E': 'E',
 'OBS_KEY_EACUTE': 'Eacute',
 'OBS_KEY_ECIRCUMFLEX': 'Ecircumflex',
 'OBS_KEY_EDIAERESIS': 'Ediaeresis',
 'OBS_KEY_EGRAVE': 'Egrave',
 'OBS_KEY_EISU_SHIFT': 'Eisu_Shift',
 'OBS_KEY_EISU_TOGGLE': 'Eisu_toggle',
 'OBS_KEY_END': 'End',
 'OBS_KEY_ENTER': 'KP_Enter',
 'OBS_KEY_EQUAL': 'equal',
 'OBS_KEY_ESCAPE': 'Escape',
 'OBS_KEY_ETH': 'ETH',
 'OBS_KEY_EXCLAM': 'exclam',
 'OBS_KEY_EXCLAMDOWN': 'exclamdown',
 'OBS_KEY_EXECUTE': 'Execute',
 'OBS_KEY_F': 'F',
 'OBS_KEY_F1': 'F1',
 'OBS_KEY_F10': 'F10',
 'OBS_KEY_F11': 'F11',
 'OBS_KEY_F12': 'F12',
 'OBS_KEY_F13': 'F13',
 'OBS_KEY_F14': 'F14',
 'OBS_KEY_F15': 'F15',
 'OBS_KEY_F16': 'F16',
 'OBS_KEY_F17': 'F17',
 'OBS_KEY_F18': 'F18',
 'OBS_KEY_F19': 'F19',
 'OBS_KEY_F2': 'F2',
 'OBS_KEY_F20': 'F20',
 'OBS_KEY_F21': 'F21',
 'OBS_KEY_F22': 'F22',
 'OBS_KEY_F23': 'F23',
 'OBS_KEY_F24': 'F24',
 'OBS_KEY_F25': 'F25',
 'OBS_KEY_F26': 'F26',
 'OBS_KEY_F27': 'F27',
 'OBS_KEY_F28': 'F28',
 'OBS_KEY_F29': 'F29',
 'OBS_KEY_F3': 'F3',
 'OBS_KEY_F30': 'F30',
 'OBS_KEY_F31': 'F31',
 'OBS_KEY_F32': 'F32',
 'OBS_KEY_F33': 'F33',
 'OBS_KEY_F34': 'F34',
 'OBS_KEY_F35': 'F35',
 'OBS_KEY_F4': 'F4',
 'OBS_KEY_F5': 'F5',
 'OBS_KEY_F6': 'F6',
 'OBS_KEY_F7': 'F7',
 'OBS_KEY_F8': 'F8',
 'OBS_KEY_F9': 'F9',
 'OBS_KEY_FIND': 'Find',
 'OBS_KEY_G': 'G',
 'OBS_KEY_GREATER': 'greater',
 'OBS_KEY_GUILLEMOTLEFT': 'guillemotleft',
 'OBS_KEY_GUILLEMOTRIGHT': 'guillemotright',
 'OBS_KEY_H': 'H',
 'OBS_KEY_HANGUL': 'Hangul',
 'OBS_KEY_HANGUL_BANJA': 'Hangul_Banja',
 'OBS_KEY_HANGUL_END': 'Hangul_End',
 'OBS_KEY_HANGUL_HANJA': 'Hangul_Hanja',
 'OBS_KEY_HANGUL_JAMO': 'Hangul_Jamo',
 'OBS_KEY_HANGUL_JEONJA': 'Hangul_Jeonja',
 'OBS_KEY_HANGUL_POSTHANJA': 'Hangul_PostHanja',
 'OBS_KEY_HANGUL_PREHANJA': 'Hangul_PreHanja',
 'OBS_KEY_HANGUL_ROMAJA': 'Hangul_Romaja',
 'OBS_KEY_HANGUL_SPECIAL': 'Hangul_Special',
 'OBS_KEY_HANGUL_START': 'Hangul_Start',
 'OBS_KEY_HANKAKU': 'Hankaku',
 'OBS_KEY_HELP': 'Help',
 'OBS_KEY_HENKAN': 'Henkan',
 'OBS_KEY_HIRAGANA': 'Hiragana',
 'OBS_KEY_HIRAGANA_KATAKANA': 'Hiragana_Katakana',
 'OBS_KEY_HOME': 'Home',
 'OBS_KEY_HYPER_L': 'Hyper_L',
 'OBS_KEY_HYPER_R': 'Hyper_R',
 'OBS_KEY_HYPHEN': 'hyphen',
 'OBS_KEY_I': 'I',
 'OBS_KEY_IACUTE': 'Iacute',
 'OBS_KEY_ICIRCUMFLEX': 'Icircumflex',
 'OBS_KEY_IDIAERESIS': 'Idiaeresis',
 'OBS_KEY_IGRAVE': 'Igrave',
 'OBS_KEY_INSERT': 'Insert',
 'OBS_KEY_J': 'J',
 'OBS_KEY_K': 'K',
 'OBS_KEY_KANA_LOCK': 'Kana_Lock',
 'OBS_KEY_KANA_SHIFT': 'Kana_Shift',
 'OBS_KEY_KANJI': 'Kanji',
 'OBS_KEY_KATAKANA': 'Katakana',
 'OBS_KEY_L': 'L',
 'OBS_KEY_LEFT': 'Left',
 'OBS_KEY_LESS': 'less',
 'OBS_KEY_M': 'M',
 'OBS_KEY_MACRON': 'macron',
 'OBS_KEY_MASCULINE': 'masculine',
 'OBS_KEY_MASSYO': 'Massyo',
 'OBS_KEY_MENU': 'Menu',
 'OBS_KEY_MINUS': 'minus',
 'OBS_KEY_MODE_SWITCH': 'Mode_switch',
 'OBS_KEY_MU': 'mu',
 'OBS_KEY_MUHENKAN': 'Muhenkan',
 'OBS_KEY_MULTIPLECANDIDATE': 'MultipleCandidate',
 'OBS_KEY_MULTIPLY': 'multiply',
 'OBS_KEY_MULTI_KEY': 'Multi_key',
 'OBS_KEY_N': 'N',
 'OBS_KEY_NOBREAKSPACE': 'nobreakspace',
 'OBS_KEY_NOTSIGN': 'notsign',
 'OBS_KEY_NTILDE': 'Ntilde',
 'OBS_KEY_NUM0': 'KP_0',
 'OBS_KEY_NUM1': 'KP_1',
 'OBS_KEY_NUM2': 'KP_2',
 'OBS_KEY_NUM3': 'KP_3',
 'OBS_KEY_NUM4': 'KP_4',
 'OBS_KEY_NUM5': 'KP_5',
 'OBS_KEY_NUM6': 'KP_6',
 'OBS_KEY_NUM7': 'KP_7',
 'OBS_KEY_NUM8': 'KP_8',
 'OBS_KEY_NUM9': 'KP_9',
 'OBS_KEY_NUMASTERISK': 'KP_Multiply',
 'OBS_KEY_NUMBERSIGN': 'numbersign',
 'OBS_KEY_NUMCOMMA': 'KP_Separator',
 'OBS_KEY_NUMEQUAL': 'KP_Equal',
 'OBS_KEY_NUMMINUS': 'KP_Subtract',
 'OBS_KEY_NUMPERIOD': 'KP_Decimal',
 'OBS_KEY_NUMPLUS': 'KP_Add',
 'OBS_KEY_NUMSLASH': 'KP_Divide',
 'OBS_KEY_O': 'O',
 'OBS_KEY_OACUTE': 'Oacute',
 'OBS_KEY_OCIRCUMFLEX': 'Ocircumflex',
 'OBS_KEY_ODIAERESIS': 'Odiaeresis',
 'OBS_KEY_OGRAVE': 'Ograve',
 'OBS_KEY_ONEHALF': 'onehalf',
 'OBS_KEY_ONEQUARTER': 'onequarter',
 'OBS_KEY_ONESUPERIOR': 'onesuperior',
 'OBS_KEY_OOBLIQUE': 'Ooblique',
 'OBS_KEY_ORDFEMININE': 'ordfeminine',
 'OBS_KEY_OTILDE': 'Otilde',
 'OBS_KEY_P': 'P',
 'OBS_KEY_PAGEDOWN': 'Page_Down',
 'OBS_KEY_PAGEUP': 'Page_Up',
 'OBS_KEY_PARAGRAPH': 'paragraph',
 'OBS_KEY_PARENLEFT': 'parenleft',
 'OBS_KEY_PARENRIGHT': 'parenright',
 'OBS_KEY_PAUSE': 'Pause',
 'OBS_KEY_PERCENT': 'percent',
 'OBS_KEY_PERIOD': 'period',
 'OBS_KEY_PERIODCENTERED': 'periodcentered',
 'OBS_KEY_PLUS': 'plus',
 'OBS_KEY_PLUSMINUS': 'plusminus',
 'OBS_KEY_PREVIOUSCANDIDATE': 'PreviousCandidate',
 'OBS_KEY_PRINT': 'Print',
 'OBS_KEY_Q': 'Q',
 'OBS_KEY_QUESTION': 'question',
 'OBS_KEY_QUESTIONDOWN': 'questiondown',
 'OBS_KEY_QUOTEDBL': 'quotedbl',
 'OBS_KEY_QUOTELEFT': 'quoteleft',
 'OBS_KEY_R': 'R',
 'OBS_KEY_REDO': 'Redo',
 'OBS_KEY_REGISTERED': 'registered',
 'OBS_KEY_RETURN': 'Return',
 'OBS_KEY_RIGHT': 'Right',
 'OBS_KEY_ROMAJI': 'Romaji',
 'OBS_KEY_S': 'S',
 'OBS_KEY_SECTION': 'section',
 'OBS_KEY_SELECT': 'Select',
 'OBS_KEY_SEMICOLON': 'semicolon',
 'OBS_KEY_SINGLECANDIDATE': 'SingleCandidate',
 'OBS_KEY_SLASH': 'slash',
 'OBS_KEY_SPACE': 'space',
 'OBS_KEY_SSHARP': 'ssharp',
 'OBS_KEY_STERLING': 'sterling',
 'OBS_KEY_T': 'T',
 'OBS_KEY_TAB': 'Tab',
 'OBS_KEY_THORN': 'THORN',
 'OBS_KEY_THREEQUARTERS': 'threequarters',
 'OBS_KEY_THREESUPERIOR': 'threesuperior',
 'OBS_KEY_TOUROKU': 'Touroku',
 'OBS_KEY_TWOSUPERIOR': 'twosuperior',
 'OBS_KEY_U': 'U',
 'OBS_KEY_UACUTE': 'Uacute',
 'OBS_KEY_UCIRCUMFLEX': 'Ucircumflex',
 'OBS_KEY_UDIAERESIS': 'Udiaeresis',
 'OBS_KEY_UGRAVE': 'Ugrave',
 'OBS_KEY_UNDERSCORE': 'underscore',
 'OBS_KEY_UNDO': 'Undo',
 'OBS_KEY_UP': 'Up',
 'OBS_KEY_V': 'V',
 'OBS_KEY_VK_MEDIA_NEXT_TRACK': 'XF86AudioNext',
 'OBS_KEY_VK_MEDIA_PLAY_PAUSE': 'XF86AudioPlay',
 'OBS_KEY_VK_MEDIA_PREV_TRACK': 'XF86AudioPrev',
 'OBS_KEY_VK_MEDIA_STOP': 'XF86AudioStop',
 'OBS_KEY_VK_VOLUME_DOWN': 'XF86AudioLowerVolume',
 'OBS_KEY_VK_VOLUME_MUTE': 'XF86AudioMute',
 'OBS_KEY_VK_VOLUME_UP': 'XF86AudioRaiseVolume',
 'OBS_KEY_W': 'W',
 'OBS_KEY_X': 'X',
 'OBS_KEY_Y': 'Y',
 'OBS_KEY_YACUTE': 'Yacute',
 'OBS_KEY_YDIAERESIS': 'Ydiaeresis',
 'OBS_KEY_YEN': 'yen',
 'OBS_KEY_Z': 'Z',
 'OBS_KEY_ZENKAKU': 'Zenkaku',
 'OBS_KEY_ZENKAKU_HANKAKU': 'Zenkaku_Hankaku'}


class BridgeError(Exception):
    pass


def stamp():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def digest(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def paths():
    home = Path.home()
    config_base = Path(os.environ.get("XDG_CONFIG_HOME", home / ".config"))
    state_base = Path(os.environ.get("XDG_STATE_HOME", home / ".local/state"))
    def occupied(path):
        return any((path / file).is_file() for file in ("settings.json", "command.json"))
    storage = LEGACY_NAME if (not occupied(config_base / NAME)
                              and occupied(config_base / LEGACY_NAME)) else NAME
    return config_base / storage, state_base / storage


def require_desktop_user():
    if os.geteuid() == 0:
        raise BridgeError("Run this as your normal desktop user, without sudo.")


def private_dir(path):
    path.mkdir(parents=True, exist_ok=True, mode=0o700)


def atomic_write(path, data, mode=0o600):
    """Follow an existing symlink without replacing it; preserve file mode."""
    path = path.resolve() if path.is_symlink() else path
    private_dir(path.parent)
    if isinstance(data, str):
        data = data.encode("utf-8")
    previous = path.stat() if path.exists() else None
    fd, temporary = tempfile.mkstemp(prefix=".obs-hotkeys-", dir=str(path.parent))
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, (previous.st_mode & 0o777) if previous else mode)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def save_json(path, value):
    atomic_write(path, json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def read_text(path):
    try:
        if path.stat().st_size > MAX_FILE:
            raise BridgeError(f"Configuration is unexpectedly large: {path}")
        return path.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeError) as exc:
        raise BridgeError(f"Cannot read {path}: {exc}") from exc


def read_json(path):
    try:
        return json.loads(read_text(path))
    except ValueError as exc:
        raise BridgeError(f"JSON is incomplete or invalid in {path}; retry after OBS saves it") from exc


def read_ini(path):
    parser = configparser.ConfigParser(interpolation=None, strict=False)
    parser.optionxform = str
    if path.is_file():
        try:
            parser.read_string(read_text(path))
        except configparser.Error as exc:
            raise BridgeError(f"INI is incomplete or invalid in {path}") from exc
    return parser


def proc_env(pid):
    try:
        entries = (PROC / str(pid) / "environ").read_bytes().split(b"\0")
        return dict(x.decode("utf-8", "surrogateescape").split("=", 1)
                    for x in entries if b"=" in x)
    except OSError:
        return {}


def proc_args(pid):
    try:
        return [(x.decode("utf-8", "surrogateescape"))
                for x in (PROC / str(pid) / "cmdline").read_bytes().split(b"\0") if x]
    except OSError:
        return []


def proc_link(pid, name):
    try:
        return Path(os.readlink(PROC / str(pid) / name))
    except OSError:
        return None


def option(args, *names):
    for i, arg in enumerate(args):
        for name in names:
            if arg == name and i + 1 < len(args):
                return args[i + 1]
            if arg.startswith(name + "="):
                return arg.split("=", 1)[1]
    return None


def expand_path(raw, env=None, cwd=None):
    env = os.environ if env is None else env
    value = str(raw)
    if value == "~" or value.startswith("~/"):
        value = env.get("HOME", str(Path.home())) + value[1:]
    value = re.sub(r"\$\{(\w+)\}|\$(\w+)",
                   lambda m: env.get(m.group(1) or m.group(2), m.group(0)), value)
    result = Path(value)
    return result if result.is_absolute() else (cwd or Path.cwd()) / result


class Hyprland:
    def __init__(self, allow_stale_session=False):
        self.binary = shutil.which("hyprctl")
        if not self.binary:
            raise BridgeError("hyprctl is missing. Run this on the host inside your Hyprland session.")
        self.signature = ""
        result = self.query("instances", instance=False)
        requested = os.environ.get("HYPRLAND_INSTANCE_SIGNATURE")
        candidates = [x for x in result if x.get("instance") == requested] if requested else result
        if not candidates and allow_stale_session and len(result) == 1:
            candidates = result  # a restarted compositor has a new instance signature
        if len(candidates) != 1:
            raise BridgeError("Cannot select one Hyprland session. Run from a terminal inside the intended session.")
        self.instance = candidates[0]
        self.signature = self.instance["instance"]
        self.pid = int(self.instance["pid"])
        self.backend = "lua" if self.ok("eval", "assert(hl and hl.bind and hl.dsp)") else "hyprlang"
        self.pass_table = True
        if self.backend == "lua":
            self.pass_table = self.ok("eval", 'hl.dsp.pass({window="address:0x0"})')

    def run(self, *args, instance=True):
        command = [self.binary]
        if instance and self.signature:
            command += ["-i", self.signature]
        try:
            return subprocess.run(command + list(args), capture_output=True, text=True,
                                  timeout=8, check=False)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise BridgeError(f"hyprctl failed: {exc}") from exc

    def query(self, command, instance=True):
        result = self.run("-j", command, instance=instance)
        try:
            if result.returncode:
                raise ValueError()
            return json.loads(result.stdout)
        except ValueError as exc:
            raise BridgeError(f"Cannot read Hyprland {command}: {result.stderr.strip() or result.stdout.strip()}") from exc

    def ok(self, *args):
        result = self.run(*args)
        return result.returncode == 0 and result.stdout.strip().lower() == "ok"

    def mutate(self, *args):
        result = self.run(*args)
        lines = [x.strip().lower() for x in result.stdout.splitlines() if x.strip()]
        if result.returncode or not lines or any(x != "ok" for x in lines):
            raise BridgeError(f"Hyprland rejected an update: {result.stderr.strip() or result.stdout.strip()}")


def detect_config(hypr, explicit=None):
    if explicit:
        target = expand_path(explicit)
    else:
        args = proc_args(hypr.pid)
        configured = option(args, "--config", "-c")
        # Hyprland also accepts -cPATH (getopt-style short option).
        configured = configured or next((x[2:] for x in args[1:]
                                         if x.startswith("-c") and not x.startswith("--") and len(x) > 2), None)
        env = proc_env(hypr.pid)
        if configured:
            target = expand_path(configured, env, proc_link(hypr.pid, "cwd"))
        else:
            base = Path(env.get("XDG_CONFIG_HOME", os.environ.get(
                "XDG_CONFIG_HOME", str(Path.home() / ".config")))) / "hypr"
            target = base / ("hyprland.lua" if hypr.backend == "lua" else "hyprland.conf")
    if not target.is_file():
        raise BridgeError(f"Active Hyprland config could not be resolved: {target}. Use --hypr-config PATH.")
    resolved = target.resolve(strict=True)
    if resolved.stat().st_uid != os.geteuid() or not os.access(resolved, os.W_OK):
        raise BridgeError(f"Config is not a writable user file: {target}. Use a writable --hypr-config entry point.")
    return resolved


class KeyNames:
    def __init__(self):
        self.lib = None
        try:
            self.lib = ctypes.CDLL(ctypes.util.find_library("xkbcommon") or "libxkbcommon.so.0")
            self.lib.xkb_keysym_from_name.argtypes = [ctypes.c_char_p, ctypes.c_int]
            self.lib.xkb_keysym_from_name.restype = ctypes.c_uint32
            self.lib.xkb_keysym_to_lower.argtypes = [ctypes.c_uint32]
            self.lib.xkb_keysym_to_lower.restype = ctypes.c_uint32
        except (OSError, AttributeError):
            self.lib = None

    def canonical(self, key):
        key = str(key)
        if key.startswith("mouse:"):
            return key.lower()
        if self.lib:
            sym = self.lib.xkb_keysym_from_name(key.encode("utf-8"), 1)
            if sym:
                return "sym:" + str(self.lib.xkb_keysym_to_lower(sym))
        return key.lower()


KEY_NAMES = KeyNames()


@dataclass(frozen=True)
class Chord:
    mods: int
    key: str

    @property
    def identity(self):
        return self.mods, KEY_NAMES.canonical(self.key)

    @property
    def mod_names(self):
        return " ".join(name for _, name, bit in MODIFIERS if self.mods & bit)

    @property
    def lua(self):
        return " + ".join([name for _, name, bit in MODIFIERS if self.mods & bit] + [self.key])

    def __str__(self):
        return self.lua


def convert_binding(value):
    if not isinstance(value, dict):
        raise BridgeError("Unrecognized OBS binding structure")
    token = value.get("key", "OBS_KEY_NONE")
    if token == "OBS_KEY_NONE":
        if any(value.get(name, False) for name, _, _ in MODIFIERS):
            raise BridgeError("Modifier-only shortcuts cannot be safely translated automatically")
        return None
    if not isinstance(token, str):
        raise BridgeError("Invalid OBS key name")
    key = KEY_MAP.get(token)
    mouse = re.fullmatch(r"OBS_KEY_MOUSE([0-9]+)", token)
    if mouse and 1 <= int(mouse[1]) <= 29:
        key = "mouse:" + str(271 + int(mouse[1]))
    if not key:
        raise BridgeError(f"Unsupported saved OBS key: {token}")
    mods = 0
    for field_name, _, bit in MODIFIERS:
        enabled = value.get(field_name, False)
        if type(enabled) is not bool:
            raise BridgeError(f"Invalid {field_name} modifier in {token}")
        if enabled:
            mods |= bit
    # OBS intentionally does not inject ordinary left/right clicks as hotkeys.
    if mouse and int(mouse[1]) <= 2:
        raise BridgeError(f"{token} cannot be reliably forwarded as an OBS hotkey")
    return Chord(mods, key)


def obs_client_groups(clients, only_pid=None):
    groups = {}
    for client in clients:
        pid = int(client.get("pid", 0))
        if pid <= 0 or (only_pid is not None and pid != only_pid):
            continue
        classes = [str(client.get(x, "")).lower() for x in ("class", "initialClass")]
        executable = proc_link(pid, "exe")
        obs_exe = executable and executable.name.removesuffix(" (deleted)") in ("obs", "obs-studio")
        if not obs_exe and not any(x in ("obs", "obs-studio", "com.obsproject.studio") for x in classes):
            continue
        if not re.fullmatch(r"0x[0-9a-fA-F]+", str(client.get("address", ""))):
            continue
        if client.get("mapped", True) is False:
            continue
        groups.setdefault(pid, []).append(client)
    windows = []
    for pid, candidates in groups.items():
        # Dialogs and projectors share OBS's app ID. The main title normally
        # begins with 'OBS <version>'; otherwise select the largest window.
        def rank(c):
            title = str(c.get("title", ""))
            initial = str(c.get("initialTitle", ""))
            main = bool(re.match(r"^OBS(?: Studio)?(?:\s+\d|\s*[-—])", title)
                        or re.match(r"^OBS(?: Studio)?(?:\s+\d|\s*[-—])", initial))
            size = c.get("size") or [0, 0]
            return main, int(size[0]) * int(size[1])
        windows.append(max(candidates, key=rank))
    return sorted(windows, key=lambda c: (c["pid"], c["address"]))


def config_candidates(pid=None):
    home = Path.home()
    if pid:
        env = proc_env(pid)
        args = proc_args(pid)
        runtime_home = Path(env.get("HOME", home))
        flatpak_id = env.get("FLATPAK_ID", "")
        if not flatpak_id:
            try:
                flatpak_id = read_ini(PROC / str(pid) / "root/.flatpak-info").get(
                    "Application", "name", fallback="")
            except (BridgeError, OSError):
                pass
        snapped = bool(env.get("SNAP_USER_DATA") or env.get("SNAP_USER_COMMON"))
        packaged = bool(flatpak_id or snapped)
        candidates = []
        # Portable paths take precedence when the process explicitly uses one.
        if any(a in ("--portable", "-p") for a in args):
            exe = proc_link(pid, "exe")
            if exe:
                candidates.append(exe.parent / "config/obs-studio")
            cwd = proc_link(pid, "cwd")
            if cwd:
                candidates.append(cwd / "config/obs-studio")
        host_xdg = Path(os.environ.get("XDG_CONFIG_HOME", home / ".config"))
        if env.get("XDG_CONFIG_HOME") and (not packaged or
                Path(env["XDG_CONFIG_HOME"]) not in (home / ".config", host_xdg)):
            candidates.append(Path(env["XDG_CONFIG_HOME"]) / "obs-studio")
        if flatpak_id:
            candidates.append(home / ".var/app" / flatpak_id / "config/obs-studio")
        for name in ("SNAP_USER_DATA", "SNAP_USER_COMMON"):
            if env.get(name):
                candidates += [Path(env[name]) / ".config/obs-studio",
                               Path(env[name]) / "config/obs-studio"]
        if env and not flatpak_id:
            candidates.append(runtime_home / ".config/obs-studio")
        # Process mount namespaces may expose paths not visible at host root.
        expanded = []
        for candidate in candidates:
            expanded.append(candidate)
            if candidate.is_absolute() and not candidate.exists():
                expanded.append(PROC / str(pid) / "root" / str(candidate).lstrip("/"))
        if expanded:
            return list(dict.fromkeys(expanded))
        exe = proc_link(pid, "exe")
        if exe and str(exe).startswith("/app/"):
            return [home / ".var/app/com.obsproject.Studio/config/obs-studio"]
        if exe and str(exe).startswith("/snap/"):
            name = exe.parts[2]
            return [home / "snap" / name / "current/.config/obs-studio",
                    home / "snap" / name / "common/.config/obs-studio"]
        # Do not silently associate another package's saved profile with OBS.
        return [Path(os.environ.get("XDG_CONFIG_HOME", home / ".config")) / "obs-studio"]
    candidates = [Path(os.environ.get("XDG_CONFIG_HOME", home / ".config")) / "obs-studio",
                  home / ".var/app/com.obsproject.Studio/config/obs-studio"]
    candidates += sorted((home / "snap").glob("*obs*/current/.config/obs-studio"))
    candidates += sorted((home / "snap").glob("*obs*/common/.config/obs-studio"))
    return list(dict.fromkeys(candidates))


def obs_root(window, explicit=None):
    if explicit:
        candidate = expand_path(explicit)
        if not candidate.is_dir():
            raise BridgeError(f"OBS config directory does not exist: {candidate}")
        return candidate.resolve()
    for candidate in config_candidates(int(window["pid"])):
        if candidate.is_dir() and any((candidate / n).exists()
                                      for n in ("user.ini", "global.ini", "basic/profiles")):
            return candidate.resolve()
    raise BridgeError(f"Could not locate OBS config for PID {window['pid']}. Use --obs-config PATH on install.")


@dataclass
class SavedHotkeys:
    root: Path
    profile: str = ""
    collection: str = ""
    hotkeys: dict = field(default_factory=dict)
    issues: list = field(default_factory=list)
    files: list = field(default_factory=list)
    aitum: bool = False
    partial: bool = False
    collection_candidates: list = field(default_factory=list)


def load_hotkeys(root, profile=None, collection=None):
    saved = SavedHotkeys(root)
    app_ini = read_ini(root / "global.ini")

    def location(name):
        raw = app_ini.get("Locations", name, fallback="")
        candidate = expand_path(raw) if raw else root.parent
        # OBS itself falls back to its normal base if the override is missing.
        return candidate if candidate.is_dir() else root.parent

    user_root = location("Configuration") / "obs-studio"
    settings_paths = [user_root / "user.ini", root / "global.ini"]
    settings = [read_ini(p) for p in settings_paths]
    saved.files.extend(str(p) for p in settings_paths if p.is_file())

    def setting(section, key):
        return next((s.get(section, key) for s in settings if s.has_option(section, key)), "")

    focus = setting("General", "HotkeyFocusType")
    if focus and focus != "NeverDisableHotkeys":
        saved.issues.append("In OBS Settings > Advanced > Hotkeys, choose 'Never disable hotkeys'.")

    profile_dir = location("Profiles") / "obs-studio/basic/profiles"
    scene_dir = location("SceneCollections") / "obs-studio/basic/scenes"
    profiles = sorted(p for p in profile_dir.glob("*/basic.ini") if p.is_file())
    profile_key = profile or setting("Basic", "ProfileDir")
    chosen_profile = None
    if profile_key:
        chosen_profile = next((p for p in profiles if p.parent.name == profile_key), None)
        if chosen_profile is None:
            # Explicit display names and older configurations may lack ProfileDir.
            chosen_profile = next((p for p in profiles
                                   if read_ini(p).get("General", "Name", fallback="") == profile_key), None)
    if not chosen_profile:
        display_name = profile or setting("Basic", "Profile")
        matches = [p for p in profiles if display_name and
                   read_ini(p).get("General", "Name", fallback="") == display_name]
        chosen_profile = matches[0] if len(matches) == 1 else (
            profiles[0] if not profile and len(profiles) == 1 else None)
    if profile and not chosen_profile:
        raise BridgeError(f"Requested OBS profile {profile!r} was not found under {profile_dir}.")
    if profiles and chosen_profile is None:
        raise BridgeError(f"Cannot identify the active OBS profile under {profile_dir}; use --profile NAME.")

    def add(binding, action):
        try:
            chord = convert_binding(binding)
            if chord:
                saved.hotkeys.setdefault(chord, set()).add(action)
        except BridgeError as exc:
            saved.issues.append(f"{action}: {exc}")

    def bindings(value, action):
        if isinstance(value, list):
            for binding in value:
                add(binding, action)
        elif isinstance(value, dict):
            # Profiles include wrappers and ReplayBuffer.Save in older OBS.
            for name, entry in value.items():
                if isinstance(entry, (list, dict)):
                    bindings(entry, action if name == "bindings" else action + "/" + name)

    if chosen_profile:
        saved.profile = chosen_profile.parent.name
        saved.files.append(str(chosen_profile))
        ini = read_ini(chosen_profile)
        if ini.has_section("Hotkeys"):
            for action, raw in ini.items("Hotkeys"):
                try:
                    value = json.loads(raw)
                except ValueError as exc:
                    raise BridgeError(f"Incomplete saved hotkey {action} in {chosen_profile}; waiting for OBS") from exc
                bindings(value, action)

    scene_key = collection or setting("Basic", "SceneCollectionFile")
    scenes = sorted(p for p in scene_dir.glob("*.json") if p.is_file())
    saved.collection_candidates = [p.name for p in scenes]
    # Recent OBS saves SceneCollectionFile as a full filename, older versions
    # used a stem. Never append '.json' blindly or require only one spelling.
    scene_name = Path(scene_key).name if scene_key else ""
    chosen_scene = next((p for p in scenes if scene_name in (p.name, p.stem)), None) if scene_key else None
    if not chosen_scene:
        display_name = collection or setting("Basic", "SceneCollection")
        matches = []
        for path in scenes:
            if display_name:
                try:
                    data = read_json(path)
                    if isinstance(data, dict) and data.get("name") == display_name:
                        matches.append(path)
                except BridgeError:
                    # Unselected/incomplete backups do not block the active profile.
                    continue
        chosen_scene = matches[0] if len(matches) == 1 else (
            scenes[0] if not collection and len(scenes) == 1 else None)
    if collection and chosen_scene is None:
        raise BridgeError(f"Requested scene collection {collection!r} was not found under {scene_dir}.")
    if scenes and chosen_scene is None:
        saved.partial = True
        saved.issues.append(f"Scene collection is unresolved under {scene_dir}; forwarding profile/Aitum hotkeys only. "
                            "Scene/source hotkeys are pending; doctor lists the available collection filenames.")

    def walk(value, label="scene collection", aitum=False):
        if isinstance(value, dict):
            label = str(value.get("name", label))
            hotkeys = value.get("hotkeys")
            if isinstance(hotkeys, dict):
                for action, entries in hotkeys.items():
                    bindings(entries, label + ": " + action)
            elif isinstance(hotkeys, list):
                bindings(hotkeys, label + ": hotkey")
            for key, child in value.items():
                if aitum and key.endswith(("_hotkey", "_hotkeys")) and isinstance(child, list):
                    bindings(child, label + ": " + key)
                    continue
                if key != "hotkeys" and isinstance(child, (dict, list)):
                    walk(child, label, aitum)
        elif isinstance(value, list):
            for child in value:
                walk(child, label, aitum)

    if chosen_scene:
        saved.collection = chosen_scene.stem
        saved.files.append(str(chosen_scene))
        try:
            data = read_json(chosen_scene)
            if not isinstance(data, dict):
                raise BridgeError(f"Scene collection is not a JSON object: {chosen_scene}")
            walk(data)
        except BridgeError as exc:
            saved.partial = True
            saved.issues.append(f"Scene/source hotkeys pending: {exc}. Profile/Aitum hotkeys remain available.")
    # Stream Suite saves output, all-output, pause, chapter, split and backtrack
    # shortcuts in aitum.json beside the active profile's basic.ini. Sources
    # nested there still use OBS's normal 'hotkeys' dictionaries.
    if chosen_profile:
        aitum_path = chosen_profile.parent / "aitum.json"
        if aitum_path.is_file():
            saved.aitum = True
            saved.files.append(str(aitum_path))
            try:
                data = read_json(aitum_path)
                if not isinstance(data, dict):
                    raise BridgeError(f"Aitum settings are not a JSON object: {aitum_path}")
                walk(data, "Aitum Stream Suite", aitum=True)
            except BridgeError as exc:
                saved.partial = True
                saved.issues.append(f"Aitum hotkeys pending: {exc}. Other saved hotkeys remain available.")
    if not chosen_profile and not chosen_scene:
        raise BridgeError(f"No saved OBS profiles or scene collections found under {root}.")
    return saved


@dataclass
class Request:
    chord: Chord
    address: str
    actions: set

    def description(self, token):
        return f"OBS Hotkey Bridge {token} " + digest(self.address + repr(self.chord.identity))[:16]


def foreign_conflicts(chord, entries, prefix):
    found = []
    for entry in entries:
        if str(entry.get("description", "")).startswith(prefix):
            continue
        # unbind affects every matching entry, including those in submaps.
        same_mods = int(entry.get("modmask", 0)) == chord.mods
        ignores_mods = bool(entry.get("ignoreMods", entry.get("ignore_mods", False)))
        if not same_mods and not ignores_mods:
            continue
        keycode = int(entry.get("keycode", 0) or 0)
        if keycode > 0:
            # A physical key could overlap a logical keysym. Do not guess a layout.
            found.append("possible physical-key conflict: " + str(entry.get("description") or keycode))
        elif KEY_NAMES.canonical(entry.get("key", "")) == chord.identity[1]:
            found.append(str(entry.get("description") or entry.get("dispatcher") or "existing bind"))
    return found


def lua_string(value):
    # JSON string escapes are Lua-compatible for ASCII generated payloads.
    # Non-ASCII is passed as literal UTF-8, rather than JSON's unsupported \\u.
    return json.dumps(value, ensure_ascii=False)


def add_operation(hypr, request, token):
    description = request.description(token)
    if hypr.backend == "lua":
        target = lua_string("address:" + request.address)
        argument = "{window=" + target + "}" if hypr.pass_table else target
        return ("__obs_hotkey_bridge=__obs_hotkey_bridge or {}; "
                f"__obs_hotkey_bridge[{lua_string(description)}]="
                f"hl.bind({lua_string(request.chord.lua)},hl.dsp.pass({argument}),"
                f"{{description={lua_string(description)}}})")
    return (f"keyword bindd {request.chord.mod_names}, {request.chord.key}, "
            f"{description}, pass, address:{request.address}")


def remove_operation(hypr, entry, allow_fallback):
    chord = Chord(int(entry.get("modmask", 0)), str(entry.get("key", "")))
    if hypr.backend == "lua":
        description = lua_string(str(entry["description"]))
        fallback = (f"hl.unbind({lua_string(chord.lua)})" if allow_fallback
                    else 'error("No exact bind handle; reload required to preserve another bind")')
        return (f"do local h=__obs_hotkey_bridge and __obs_hotkey_bridge[{description}]; "
                f"if h and type(h.remove)=='function' then h:remove() else {fallback} end; "
                f"if __obs_hotkey_bridge then __obs_hotkey_bridge[{description}]=nil end end")
    if not allow_fallback:
        return None
    return f"keyword unbind {chord.mod_names}, {chord.key}"


def execute_operations(hypr, operations):
    for start in range(0, len(operations), 40):
        batch = operations[start:start + 40]
        if hypr.backend == "lua":
            hypr.mutate("eval", ";\n".join(batch))
        else:
            # This is the config parser's binding scope, not the user's active
            # runtime submap. Always register these in the default scope.
            hypr.mutate("--batch", "keyword submap reset ; " + " ; ".join(batch))


def reconcile(hypr, requests, token, apply=True):
    entries = hypr.query("binds")
    prefix = f"OBS Hotkey Bridge {token} "
    grouped = {}
    for request in requests:
        grouped.setdefault(request.chord.identity, []).append(request)
    desired, issues = {}, []
    for group in grouped.values():
        targets = {request.address for request in group}
        chord = group[0].chord
        if len(targets) > 1:
            issues.append(f"{chord}: assigned in multiple OBS instances; skipped. Select --obs-pid or --obs-config.")
            continue
        conflicts = foreign_conflicts(chord, entries, prefix)
        if conflicts:
            issues.append(f"{chord}: skipped; already used by " + "; ".join(conflicts))
            continue
        request = group[0]
        desired[request.description(token)] = request
    own = [x for x in entries if str(x.get("description", "")).startswith(prefix)]
    operations = []
    existing = set()
    for entry in own:
        description = entry["description"]
        if description in desired:
            existing.add(description)
            continue
        chord = Chord(int(entry.get("modmask", 0)), str(entry.get("key", "")))
        safe = not foreign_conflicts(chord, entries, prefix)
        operation = remove_operation(hypr, entry, safe)
        if operation:
            operations.append(operation)
        else:
            issues.append(f"{chord}: cleanup overlaps another runtime bind; run hyprctl reload.")
    operations += [add_operation(hypr, request, token)
                   for description, request in desired.items() if description not in existing]
    if apply and operations:
        execute_operations(hypr, operations)
    return {
        "forwarded": [{"keys": str(request.chord), "target": request.address,
                       "actions": sorted(request.actions)} for request in desired.values()],
        "issues": issues,
        "updates": len(operations),
    }


def collect(hypr, settings):
    windows = obs_client_groups(hypr.query("clients"), settings.get("obs_pid"))
    requests, instances, issues = [], [], []
    for window in windows:
        root = obs_root(window, settings.get("obs_config"))
        # An explicit root selects only processes actually using that root,
        # unless --obs-pid explicitly identifies a custom installation.
        if settings.get("obs_config") and len(windows) > 1 and not settings.get("obs_pid"):
            detected = obs_root(window)
            if detected != root:
                continue
        saved = load_hotkeys(root, settings.get("profile"), settings.get("collection"))
        requests.extend(Request(chord, window["address"], actions)
                        for chord, actions in saved.hotkeys.items())
        issues.extend(saved.issues)
        if window.get("xwayland"):
            issues.append(f"OBS PID {window['pid']} runs through XWayland: cross-application forwarding may be unreliable.")
        instances.append({"pid": window["pid"], "address": window["address"],
                          "workspace": window.get("workspace"), "class": window.get("class"),
                          "xwayland": bool(window.get("xwayland")), "config": str(root),
                          "profile": saved.profile, "collection": saved.collection,
                          "aitum_stream_suite": saved.aitum, "partial": saved.partial,
                          "hotkey_files": saved.files, "collection_candidates": saved.collection_candidates,
                          "saved_chords": len(saved.hotkeys)})
    return requests, instances, issues


def bootstrap_block(backend, bootstrap_path):
    if backend == "lua":
        return f"-- {BEGIN}\ndofile({lua_string(str(bootstrap_path))})\n-- {END}\n"
    if any(x in str(bootstrap_path) for x in "\r\n#$"):
        raise BridgeError("Hyprlang source paths containing #, $ or newlines need a different XDG_CONFIG_HOME.")
    return f"# {BEGIN}\nsource = {bootstrap_path}\n# {END}\n"


def install_hook(root, block, backend, expected=None):
    original = root.read_bytes()
    if expected is not None and original != expected:
        raise BridgeError("Hyprland config changed during install. No hook was added; run install again.")
    text = original.decode("utf-8-sig")
    if BEGIN in text or END in text:
        if block.encode() in original and text.count(BEGIN) == 1 and text.count(END) == 1:
            return original, b""
        raise BridgeError(f"An edited or different {NAME} hook already exists in {root}; inspect it before installing.")
    encoded = block.encode("utf-8")
    # Prepending Lua is valid even for configs ending in a top-level return.
    # Keep a UTF-8 BOM as the first bytes, if the file contains one.
    if backend == "lua":
        bom = b"\xef\xbb\xbf" if original.startswith(b"\xef\xbb\xbf") else b""
        result = bom + encoded + original[len(bom):]
        added = encoded
    else:
        added = (b"" if not original or original.endswith(b"\n") else b"\n") + encoded
        result = original + added
    atomic_write(root, result)
    return original, added


def remove_hook(root, exact):
    if not exact:
        return
    original = root.read_bytes()
    block = exact.encode("utf-8")
    if original.count(block) != 1:
        raise BridgeError(f"The managed hook changed in {root}; it was left intact. Remove its marked block manually.")
    atomic_write(root, original.replace(block, b"", 1))


def running_daemon(record):
    pid = int(record.get("daemon_pid", 0))
    args = proc_args(pid) if pid > 0 else []
    installed = record.get("script", "")
    launcher = record.get("launcher", "")
    matches = (installed and installed in args) or (launcher and launcher in args)
    return pid if matches and "daemon" in args else None


def stop_daemon(state):
    status_path = state / "status.json"
    if not status_path.is_file():
        return
    pid = running_daemon(read_json(status_path))
    if not pid:
        return
    os.kill(pid, signal.SIGTERM)
    for _ in range(150):
        if not running_daemon(read_json(status_path)):
            return
        # A dead process may remain a zombie while its parent reaps it.
        try:
            if (PROC / str(pid) / "stat").read_text().split(") ", 1)[1].startswith("Z"):
                return
        except OSError:
            return
        time.sleep(0.1)
    raise BridgeError("Previous bridge daemon did not stop; no files were removed. Check its log.")


def systemd_available():
    binary = shutil.which("systemctl")
    if not binary:
        return False
    try:
        # Never capture or display the manager's environment; only check that
        # this user's manager/bus can be reached.
        result = subprocess.run([binary, "--user", "show-environment"],
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=3)
        return result.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def systemctl(*arguments, check=True):
    binary = shutil.which("systemctl")
    if not binary:
        raise BridgeError("systemctl is missing; use enable --supervisor process on a non-systemd desktop.")
    try:
        result = subprocess.run([binary, "--user", *arguments], capture_output=True,
                                text=True, timeout=25, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise BridgeError(f"Cannot contact the user service manager: {exc}") from exc
    if check and result.returncode:
        raise BridgeError("User service operation failed: " + (result.stderr.strip() or result.stdout.strip()))
    return result


def service_info():
    try:
        result = systemctl("show", SERVICE, "--no-pager",
                           "--property=ActiveState,SubState,MainPID,UnitFileState,FragmentPath,NRestarts", check=False)
        return dict(line.split("=", 1) for line in result.stdout.splitlines() if "=" in line)
    except BridgeError:
        return {}


def unit_path(config):
    return config.parent / "systemd/user" / SERVICE


def unit_quote(value):
    value = str(value)
    if any(ord(c) < 32 for c in value):
        raise BridgeError("Service paths cannot contain control characters.")
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"').replace("%", "%%").replace("$", "$$") + '"'


def service_unit(script, settings_file):
    command = " ".join(unit_quote(x) for x in
                       (sys.executable, script, "daemon", "--settings", settings_file, "--supervised"))
    return (UNIT_MARKER + "[Unit]\nDescription=Automatic OBS hotkeys for Hyprland\n\n"
            "[Service]\nType=simple\nExecStart=" + command + "\n"
            "Restart=always\nRestartSec=3\nTimeoutStopSec=20\n"
            "StandardOutput=journal\nStandardError=journal\nSyslogIdentifier=hypr-obs\n\n"
            "[Install]\nWantedBy=default.target\n")


def check_owned_unit(path):
    if path.is_symlink() or (path.exists() and (path.stat().st_uid != os.geteuid()
                                               or not read_text(path).startswith(UNIT_MARKER))):
        raise BridgeError(f"An unmanaged service file exists at {path}; it was left untouched.")


def remember_session(hypr, state):
    values = {name: os.environ[name] for name in SESSION_VARIABLES if os.environ.get(name)}
    values["HYPRLAND_INSTANCE_SIGNATURE"] = hypr.signature
    save_json(state / "session.json", values)


def refresh_session(state):
    path = state / "session.json"
    if not path.is_file():
        return
    values = read_json(path)
    for name in SESSION_VARIABLES:
        if name in values:
            value = values[name]
            if not isinstance(value, str) or any(ord(c) < 32 for c in value):
                raise BridgeError("Invalid saved session environment.")
            os.environ[name] = value
        elif name in ("HYPRLAND_INSTANCE_SIGNATURE", "WAYLAND_DISPLAY", "DISPLAY"):
            os.environ.pop(name, None)


def resolve_settings(args):
    path = Path(args.settings) if getattr(args, "settings", None) else paths()[0] / "settings.json"
    if not path.is_file():
        raise BridgeError("Forwarding is not configured yet. Run hypr-obs enable inside Hyprland.")
    return path, read_json(path)


def stop_runtime(settings):
    if settings.get("supervisor") == "systemd":
        systemctl("stop", SERVICE)
    stop_daemon(Path(settings["state_dir"]))


def start_daemon(config, state, script):
    settings = read_json(config / "settings.json")
    if settings.get("supervisor") == "systemd":
        path = Path(settings["unit_path"])
        check_owned_unit(path)
        atomic_write(path, service_unit(script, config / "settings.json"), mode=0o644)
        systemctl("daemon-reload")
        systemctl("enable", str(path))
        systemctl("restart", SERVICE)
        return
    private_dir(state)
    log = state / "bridge.log"
    if log.is_file() and log.stat().st_size > 1024 * 1024:
        atomic_write(log, b"")
    with log.open("ab") as output:
        subprocess.Popen([sys.executable, str(script), "daemon", "--settings", str(config / "settings.json")],
                         stdin=subprocess.DEVNULL, stdout=output, stderr=output,
                         start_new_session=True, cwd=str(Path.home()))


def install(args):
    require_desktop_user()
    hypr = Hyprland()
    root = detect_config(hypr, args.hypr_config)
    config, state = paths()
    private_dir(config)
    private_dir(state)
    settings_file = config / "settings.json"
    previous = read_json(settings_file) if settings_file.is_file() else None
    if previous and previous.get("hypr_config") != str(root):
        raise BridgeError("A different parent config is already installed. Uninstall it before switching entry points.")
    if previous and (state / "status.json").is_file():
        status = read_json(state / "status.json")
        if running_daemon(status) and status.get("session") != hypr.signature:
            raise BridgeError("A bridge is running in another Hyprland session. Install from that session.")
    def preference(name, default=None):
        supplied = getattr(args, name, None)
        return supplied if supplied is not None else (previous or {}).get(name, default)
    obs_config = preference("obs_config")
    preference_supervisor = getattr(args, "supervisor", None) or (previous or {}).get("supervisor_preference", "auto")
    manager = systemd_available() if preference_supervisor != "process" else False
    if preference_supervisor == "systemd" and not manager:
        raise BridgeError("The systemd user manager is unavailable. Run from your desktop session or use --supervisor process.")
    supervisor = "systemd" if manager else "process"
    service_path = unit_path(config)
    if supervisor == "systemd":
        check_owned_unit(service_path)
    unit_before = service_path.read_bytes() if service_path.is_file() else None
    was_service = previous and previous.get("supervisor") == "systemd"
    settings = {
        "version": VERSION, "token": previous["token"] if previous else uuid.uuid4().hex[:12],
        "hypr_config": str(root), "backend": hypr.backend,
        "obs_config": str(expand_path(obs_config).resolve()) if obs_config else None,
        "obs_pid": preference("obs_pid"), "profile": preference("profile"), "collection": preference("collection"),
        "interval": preference("interval", 3.0), "state_dir": str(state),
        "supervisor": supervisor, "supervisor_preference": preference_supervisor,
        "unit_path": str(service_path) if supervisor == "systemd" else None,
    }
    # Validate actual OBS files before installing when OBS is already running.
    requests, instances, issues = collect(hypr, settings)
    preview = reconcile(hypr, requests, settings["token"], apply=False)
    script = config / (NAME + ".py")
    bootstrap = config / ("startup.lua" if hypr.backend == "lua" else "startup.conf")
    command = shlex.join([sys.executable, str(script), "start", "--settings", str(settings_file), "--from-session"])
    if any(c in command for c in "\r\n"):
        raise BridgeError("Install paths cannot contain newlines.")
    if hypr.backend == "lua":
        bootstrap_text = ("-- Start once per compositor session; stop remains effective across reloads.\n"
                          "hl.on(\"hyprland.start\", function()\n"
                          f"    hl.exec_cmd({lua_string(command)})\nend)\n")
    else:
        if any(c in command for c in "#$"):
            raise BridgeError("Hyprlang startup paths containing # or $ are unsupported.")
        bootstrap_text = "# Start the bridge once in this Hyprland session.\nexec-once = " + command + "\n"
    block = bootstrap_block(hypr.backend, bootstrap)
    if previous:
        stop_runtime(previous)
        if was_service and supervisor != "systemd":
            systemctl("disable", SERVICE)
            check_owned_unit(service_path)
            service_path.unlink(missing_ok=True)
            systemctl("daemon-reload")
    original_script = Path(__file__).resolve().read_bytes()
    atomic_write(script, original_script, mode=0o700)
    atomic_write(bootstrap, bootstrap_text)
    before = root.read_bytes()
    backup = state / ("hyprland-before-" + digest(before.decode("utf-8-sig"))[:16] + root.suffix)
    if not backup.exists():
        atomic_write(backup, before)
    added = b""
    try:
        _, added = install_hook(root, block, hypr.backend, expected=before)
        settings["added_hook"] = added.decode("utf-8") if added else (previous or {}).get("added_hook", block)
        settings["backup"] = str(backup)
        save_json(settings_file, settings)
        remember_session(hypr, state)
        # No compositor reload is needed: bindings are installed dynamically.
        start_daemon(config, state, script)
    except Exception:
        if supervisor == "systemd":
            systemctl("stop", SERVICE, check=False)
            if not was_service:
                systemctl("disable", SERVICE, check=False)
            if unit_before is None:
                service_path.unlink(missing_ok=True)
            else:
                atomic_write(service_path, unit_before)
            systemctl("daemon-reload", check=False)
        # Restore only this install's exact root mutation on a failed install.
        if added:
            remove_hook(root, added.decode("utf-8"))
        if previous:
            save_json(settings_file, previous)
            try:
                # Keep an existing installation usable after a failed update.
                start_daemon(config, state, script)
            except (BridgeError, OSError):
                pass
        elif settings_file.is_file():
            settings_file.unlink()
        raise
    print(f"Enabled {NAME} {VERSION}; supervisor={supervisor}; parent: {root} ({hypr.backend}).")
    print(f"Detected {len(instances)} OBS instance(s), {len(preview['forwarded'])} forwardable saved shortcut(s).")
    for issue in dict.fromkeys(issues + preview["issues"]):
        print("  " + issue)
    if not instances:
        print("Waiting for OBS. Launch it normally; saved shortcuts will be discovered automatically.")
    print("Status: hypr-obs status")
    return 0


def socket_path(hypr):
    runtime = Path(os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.geteuid()}"))
    for path in (runtime / "hypr" / hypr.signature / ".socket2.sock",
                 Path("/tmp/hypr") / hypr.signature / ".socket2.sock"):
        if path.exists():
            return path
    return None


def daemon_session(settings, hypr, stopping, supervised=False):
    state = Path(settings["state_dir"])
    private_dir(state)
    lock = state / ("session-" + digest(hypr.signature)[:16] + ".lock")
    with lock.open("a+") as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print("Another OBS hotkey worker is already attached to this session.", flush=True)
            return False
        event_socket = None
        buffer = b""
        last_status = None
        last_full = 0.0
        last_reconcile = 0.0
        last_plan = None
        last_result = None
        last_probe = 0.0
        record = {"daemon_pid": os.getpid(), "script": str(Path(__file__).resolve()),
                  "launcher": str(Path(sys.argv[0]).absolute()),
                  "session": hypr.signature, "backend": hypr.backend,
                  "hypr_config": settings["hypr_config"], "started": stamp(),
                  "supervisor": "systemd" if supervised else "process", "phase": "starting"}
        while not stopping.is_set():
            now = time.monotonic()
            try:
                if event_socket is None and now - last_probe >= 5:
                    last_probe = now
                    path = socket_path(hypr)
                    if path:
                        try:
                            event_socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                            event_socket.settimeout(1)
                            event_socket.connect(str(path))
                            event_socket.setblocking(False)
                        except OSError:
                            if event_socket:
                                event_socket.close()
                            event_socket = None
                if now - last_full >= settings.get("interval", 3.0):
                    last_full = now
                    requests, instances, issues = collect(hypr, settings)
                    plan = tuple(sorted((r.chord.identity, r.address, tuple(sorted(r.actions))) for r in requests))
                    # Poll saved settings every interval, but query/reconcile
                    # compositor binds only when the plan changes, on an event,
                    # or once per 15 seconds to detect external runtime edits.
                    if plan != last_plan or now - last_reconcile >= 15:
                        result = reconcile(hypr, requests, settings["token"])
                        last_plan, last_reconcile = plan, now
                        last_result = result
                    else:
                        result = {**last_result, "updates": 0}
                    record.update(result)
                    record.update({"instances": instances, "issues": list(dict.fromkeys(issues + result["issues"])),
                                   "error": None, "updated": stamp(), "phase": "watching", "message": None})
                    save_json(state / "status.json", record)
                    # Log only changes, not every heartbeat.
                    summary = json.dumps({k: record.get(k) for k in ("instances", "forwarded", "issues", "error")}, sort_keys=True)
                    if summary != last_status:
                        print(stamp(), f"OBS={len(instances)} forwarded={len(result['forwarded'])}", flush=True)
                        for issue in record["issues"]:
                            print("  " + issue, flush=True)
                        last_status = summary
                timeout = min(1.0, settings.get("interval", 3.0))
                if event_socket:
                    readable, _, _ = select.select([event_socket], [], [], timeout)
                    if readable:
                        data = event_socket.recv(65536)
                        if not data:
                            break  # outer worker waits for the next compositor session
                        buffer += data
                        while b"\n" in buffer:
                            line, buffer = buffer.split(b"\n", 1)
                            event = line.split(b">>", 1)[0]
                            if event in (b"openwindow", b"closewindow", b"configreloaded"):
                                last_full = 0.0
                                last_plan = None
                        if len(buffer) > 1024 * 1024:
                            buffer = b""
                else:
                    stopping.wait(timeout)
            except (BridgeError, OSError, ValueError, TypeError) as exc:
                record.update({"error": str(exc), "updated": stamp(), "phase": "retrying"})
                save_json(state / "status.json", record)
                if str(exc) != last_status:
                    print(stamp(), "Waiting:", str(exc), flush=True)
                    last_status = str(exc)
                # Broken JSON during OBS save is retried; the desktop is untouched.
                if not (PROC / str(hypr.pid)).exists():
                    break
                if isinstance(exc, BridgeError) and str(exc).startswith(("Cannot read Hyprland", "hyprctl failed:")):
                    break  # reconnect through the outer session-discovery loop
                if isinstance(exc, OSError) and event_socket:
                    event_socket.close()
                    event_socket = None
                stopping.wait(min(settings.get("interval", 3.0), 2.0))
        if event_socket:
            event_socket.close()
        try:
            reconcile(hypr, [], settings["token"])
        except BridgeError:
            pass
        record.update({"updated": stamp(), "instances": [], "forwarded": [],
                       "phase": "stopped" if stopping.is_set() else "waiting_for_hyprland",
                       "daemon_pid": 0 if stopping.is_set() else os.getpid()})
        if stopping.is_set():
            record["stopped"] = stamp()
        save_json(state / "status.json", record)
    return True


def daemon(args):
    settings_file, settings = resolve_settings(args)
    state = Path(settings["state_dir"])
    private_dir(state)
    stopping = threading.Event()
    signal.signal(signal.SIGTERM, lambda _number, _frame: stopping.set())
    signal.signal(signal.SIGINT, lambda _number, _frame: stopping.set())
    with (state / "worker.lock").open("a+") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print("hypr-obs is already running. Use hypr-obs status or hypr-obs restart.")
            return 0
        reported = None
        try:
            while not stopping.is_set():
                try:
                    if getattr(args, "supervised", False):
                        refresh_session(state)
                    hypr = Hyprland(allow_stale_session=True)
                except BridgeError as exc:
                    message = str(exc)
                    save_json(state / "status.json", {
                        "daemon_pid": os.getpid(), "script": str(Path(__file__).resolve()),
                        "launcher": str(Path(sys.argv[0]).absolute()),
                        "supervisor": "systemd" if getattr(args, "supervised", False) else "process",
                        "phase": "waiting_for_hyprland", "message": message,
                        "hypr_config": settings["hypr_config"], "updated": stamp(),
                        "instances": [], "forwarded": [], "issues": [], "error": None,
                    })
                    if message != reported:
                        print(stamp(), "Waiting for Hyprland:", message, flush=True)
                        reported = message
                    stopping.wait(min(settings.get("interval", 3.0), 3.0))
                    continue
                reported = None
                settings = read_json(settings_file)
                if not daemon_session(settings, hypr, stopping, getattr(args, "supervised", False)):
                    return 0
                if not stopping.is_set():
                    stopping.wait(0.5)
        finally:
            path = state / "status.json"
            if path.is_file():
                record = read_json(path)
                if record.get("daemon_pid") in (0, os.getpid()):
                    record.update({"stopped": stamp(), "phase": "stopped", "daemon_pid": 0})
                    save_json(path, record)
    return 0


def control_runtime(args):
    settings_file, settings = resolve_settings(args)
    state = Path(settings["state_dir"])
    action = args.command
    if action == "stop":
        stop_runtime(settings)
        print("Stopped hypr-obs. Login autostart remains enabled; use disable to remove it.")
        return 0
    old_status = read_json(state / "status.json") if (state / "status.json").is_file() else {}
    current_session = None
    if getattr(args, "from_session", False) or os.environ.get("HYPRLAND_INSTANCE_SIGNATURE"):
        current_session = Hyprland()
        remember_session(current_session, state)
    if settings.get("supervisor") == "systemd":
        if running_daemon(old_status) and old_status.get("supervisor") != "systemd":
            stop_daemon(state)  # adopt a foreground/old detached worker first
        changed = current_session and old_status.get("session") not in (None, current_session.signature)
        systemctl("restart" if action == "restart" or changed else "start", SERVICE)
    else:
        if running_daemon(old_status):
            if action != "restart":
                print("hypr-obs is already running.")
                return 0
            stop_daemon(state)
        start_daemon(settings_file.parent, state, settings_file.parent / (NAME + ".py"))
    print(("Restarted" if action == "restart" else "Started") + " hypr-obs (" + settings.get("supervisor", "process") + ").")
    return 0


def logs(args):
    _settings_file, settings = resolve_settings(args)
    if settings.get("supervisor") == "systemd":
        binary = shutil.which("journalctl")
        if not binary:
            raise BridgeError("journalctl is missing. Use systemctl --user status hypr-obs.service.")
        command = [binary, "--user", "--unit=" + SERVICE, "--no-pager", "--output=cat", "--lines=" + str(args.lines)]
        if args.follow:
            command.append("--follow")
        try:
            return subprocess.run(command, check=False).returncode
        except KeyboardInterrupt:
            return 0
    path = Path(settings["state_dir"]) / "bridge.log"
    if not path.is_file():
        print("No log yet. Run hypr-obs start.")
        return 0
    with path.open(encoding="utf-8", errors="replace") as stream:
        print("".join(stream.readlines()[-args.lines:]), end="", flush=True)
        if args.follow:
            try:
                while True:
                    line = stream.readline()
                    if line:
                        print(line, end="", flush=True)
                    else:
                        time.sleep(0.3)
            except KeyboardInterrupt:
                pass
    return 0


def show_status(args):
    config, state = paths()
    status_file = state / "status.json"
    settings_file = config / "settings.json"
    settings = read_json(settings_file) if settings_file.is_file() else {}
    status = read_json(status_file) if status_file.is_file() else {
        "daemon_pid": 0, "phase": "starting" if settings else "not_enabled",
        "hypr_config": settings.get("hypr_config"), "instances": [], "forwarded": [], "issues": []}
    status["running"] = running_daemon(status) is not None
    status["supervisor"] = settings.get("supervisor", status.get("supervisor", "process"))
    if status["supervisor"] == "systemd":
        info = service_info()
        status["service"] = info
        status["running"] = status["running"] or (info.get("ActiveState") == "active" and int(info.get("MainPID", "0")) > 0)
    if args.json:
        print(json.dumps(status, indent=2, ensure_ascii=False))
    else:
        print(f"hypr-obs {'running' if status['running'] else 'stopped'}; supervisor={status['supervisor']}; phase={status.get('phase', '?')}")
        if status.get("service"):
            info = status["service"]
            print(f"Service: {info.get('ActiveState', '?')}/{info.get('SubState', '?')}; PID={info.get('MainPID', '?')}; restarts={info.get('NRestarts', '?')}")
        if status.get("message"):
            print(status["message"])
        if not settings:
            print("Run hypr-obs enable inside Hyprland to configure automatic forwarding.")
        print("Hyprland parent:", status.get("hypr_config"))
        for instance in status.get("instances", []):
            print(f"OBS PID {instance['pid']}, window {instance['address']}, workspace {instance.get('workspace')}")
            print(f"  {instance['config']} | profile={instance['profile']} | scenes={instance['collection']}")
            if instance.get("aitum_stream_suite"):
                print("  Aitum Stream Suite: aitum.json detected")
            if instance.get("partial"):
                print("  Partial discovery; see issues below or run doctor.")
        for forwarding in status.get("forwarded", []):
            print("  " + forwarding["keys"] + " -> OBS " + forwarding["target"])
        for issue in status.get("issues", []):
            print("  " + issue)
        if status.get("error"):
            print("ERROR:", status["error"])
        print("Logs: hypr-obs logs --follow" if status["supervisor"] == "systemd" else "Log: " + str(state / "bridge.log"))
    active = status["running"] or status.get("service", {}).get("ActiveState") == "activating"
    return 0 if active and not status.get("error") else 1


def doctor(args):
    hypr = Hyprland()
    config, _ = paths()
    installed = read_json(config / "settings.json") if (config / "settings.json").is_file() else {}
    settings = {"obs_config": args.obs_config or installed.get("obs_config"),
                "obs_pid": args.obs_pid or installed.get("obs_pid"),
                "profile": args.profile or installed.get("profile"),
                "collection": args.collection or installed.get("collection")}
    root = detect_config(hypr, args.hypr_config or installed.get("hypr_config"))
    requests, instances, issues = collect(hypr, settings)
    result = reconcile(hypr, requests, installed.get("token", "preview"), apply=False)
    report = {"version": VERSION, "backend": hypr.backend, "hypr_config": str(root),
              "instances": instances, "forwarded": result["forwarded"],
              "issues": issues + result["issues"],
              "saved_config_candidates": [str(p) for p in config_candidates() if p.is_dir()],
              "changes_made": False}
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


def disable(_args):
    config, state = paths()
    settings_file = config / "settings.json"
    if not settings_file.is_file():
        print("Automatic forwarding is already disabled.")
        return 0
    settings = read_json(settings_file)
    service_path = Path(settings.get("unit_path") or unit_path(config))
    if settings.get("supervisor") == "systemd":
        check_owned_unit(service_path)
    # Remove the autostart entry first, so an auto-reload cannot respawn it.
    remove_hook(Path(settings["hypr_config"]), settings.get("added_hook", ""))
    if settings.get("supervisor") == "systemd":
        systemctl("disable", "--now", SERVICE)
        service_path.unlink(missing_ok=True)
        systemctl("daemon-reload")
    stop_daemon(state)
    try:
        hypr = Hyprland()
        reconcile(hypr, [], settings["token"])
    except BridgeError as exc:
        print("Runtime cleanup:", exc, "A Hyprland reload also clears runtime bridge bindings.")
    for filename in (NAME + ".py", LEGACY_NAME + ".py", "startup.lua", "startup.conf", "settings.json"):
        path = config / filename
        if path.is_file():
            path.unlink()
    (state / "session.json").unlink(missing_ok=True)
    try:
        config.rmdir()
    except OSError:
        pass
    print("Disabled forwarding and removed its startup hook. Config backups and logs are retained at", state)
    return 0


def setup(args):
    """Install a standalone command without pip or a virtual environment."""
    require_desktop_user()
    config, _ = paths()
    record_path = config / "command.json"
    previous = read_json(record_path) if record_path.is_file() else None
    requested_dir = args.bin_dir
    if requested_dir:
        directory = expand_path(requested_dir)
    elif previous:
        directory = Path(previous["path"]).parent
    else:
        directory = Path(os.environ.get("XDG_BIN_HOME", str(Path.home() / ".local/bin")))
    directory = directory.absolute()
    command = directory / NAME
    source = Path(__file__).resolve().read_bytes()
    checksum = hashlib.sha256(source).hexdigest()
    if command.is_symlink():
        raise BridgeError(f"Refusing to replace a symlink at {command}. Use --bin-dir for another directory.")
    if command.exists():
        if not command.is_file() or command.stat().st_uid != os.geteuid():
            raise BridgeError(f"Not a managed user executable: {command}")
        actual = hashlib.sha256(command.read_bytes()).hexdigest()
        managed = previous and previous.get("path") == str(command) and previous.get("sha256") == actual
        if not managed and actual != checksum:
            raise BridgeError(f"A different or modified command already exists at {command}; it was left untouched.")
    if previous and previous.get("path") != str(command):
        raise BridgeError("A command is already installed elsewhere. Uninstall it before changing --bin-dir.")
    atomic_write(command, source, mode=0o755)
    command.chmod(0o755)
    save_json(record_path, {"path": str(command), "sha256": checksum, "version": VERSION,
                            "installed": stamp()})
    print(f"Installed {NAME} {VERSION}: {command}")
    on_path = any(Path(p or ".").absolute() == directory for p in os.environ.get("PATH", "").split(os.pathsep))
    if not on_path:
        if Path(os.environ.get("SHELL", "")).name == "fish":
            print("Add the command directory to fish's PATH once: fish_add_path " + shlex.quote(str(directory)))
        else:
            print("Add this directory to your shell's PATH: " + str(directory))
        print("Until then, run: " + shlex.quote(str(command)) + " enable")
    if args.no_enable:
        print("Automatic forwarding is not enabled yet. Run hypr-obs enable inside Hyprland.")
        return 0
    try:
        return install(args)
    except BridgeError as exc:
        print(f"The command is installed; forwarding could not be enabled: {exc}", file=sys.stderr)
        print("Run hypr-obs doctor, then hypr-obs enable inside your Hyprland session.", file=sys.stderr)
        return 1


def uninstall(args):
    config, _ = paths()
    record_path = config / "command.json"
    record = read_json(record_path) if record_path.is_file() else None
    disable(args)
    if not record:
        print("No standalone command receipt found. Remove any pipx/package-managed installation with its package manager.")
        return 0
    command = Path(record["path"])
    if command.is_symlink():
        raise BridgeError(f"The command is now a symlink and was left intact: {command}")
    if command.exists():
        checksum = hashlib.sha256(command.read_bytes()).hexdigest()
        if command.stat().st_uid != os.geteuid() or checksum != record["sha256"]:
            raise BridgeError(f"The command changed outside the installer and was left intact: {command}")
        command.unlink()
    record_path.unlink(missing_ok=True)
    try:
        config.rmdir()
    except OSError:
        pass
    print("Removed command:", command)
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(prog=NAME, description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--version", action="version", version=VERSION)
    commands = parser.add_subparsers(dest="command", required=True)
    for name, function in (("setup", setup), ("enable", install), ("install", install), ("doctor", doctor)):
        helps = {"setup": "Install the hypr-obs command and enable forwarding",
                 "enable": "Enable forwarding and start it at login",
                 "install": "Alias for enable (prototype compatibility)",
                 "doctor": "Read-only discovery and conflict report"}
        command = commands.add_parser(name, help=helps[name])
        command.set_defaults(function=function)
        command.add_argument("--hypr-config", help="Override the active Hyprland entry point")
        command.add_argument("--obs-config", help="Override/select the OBS configuration directory (ending in obs-studio)")
        command.add_argument("--obs-pid", type=int, help="Select one running OBS PID; a restart changes this PID")
        command.add_argument("--profile", help="Override saved active OBS profile directory/name")
        command.add_argument("--collection", help="Override the active scene collection filename, stem or display name")
        if name != "doctor":
            command.add_argument("--interval", type=float, help="Saved-config polling seconds (minimum 1, default 3)")
            command.add_argument("--supervisor", choices=("auto", "systemd", "process"),
                                 help="Prefer a supervised systemd user service when available (default auto)")
        if name == "setup":
            command.add_argument("--no-enable", action="store_true", help="Install only the command, for use outside a Hyprland session")
            command.add_argument("--bin-dir", help="Command directory (default ~/.local/bin or XDG_BIN_HOME)")
    command = commands.add_parser("status", help="Show forwarding, conflicts and errors")
    command.add_argument("--json", action="store_true")
    command.set_defaults(function=show_status)
    for name in ("start", "stop", "restart"):
        command = commands.add_parser(name, help=name.capitalize() + " the background watcher")
        command.add_argument("--settings", help="Settings file (automatically discovered by default)")
        command.add_argument("--from-session", action="store_true", help=argparse.SUPPRESS)
        command.set_defaults(function=control_runtime)
    command = commands.add_parser("logs", help="Show watcher logs")
    command.add_argument("--settings", help="Settings file (automatically discovered by default)")
    command.add_argument("-f", "--follow", action="store_true", help="Follow live log output")
    command.add_argument("-n", "--lines", type=int, default=50, help="Recent lines (default 50)")
    command.set_defaults(function=logs)
    command = commands.add_parser("disable", help="Stop forwarding and remove autostart; keep the command")
    command.set_defaults(function=disable)
    command = commands.add_parser("uninstall", help="Disable forwarding and remove the standalone command")
    command.set_defaults(function=uninstall)
    command = commands.add_parser("daemon", help="Run the watcher in the foreground; enable runs it as a background service",
                                  description="Watch saved OBS/Aitum hotkeys continuously in the foreground. Settings are discovered automatically. Use 'hypr-obs enable' for the background service.")
    command.add_argument("--settings", help="Settings file (automatically discovered by default)")
    command.add_argument("--supervised", action="store_true", help=argparse.SUPPRESS)
    command.set_defaults(function=daemon)
    args = parser.parse_args(argv)
    if getattr(args, "interval", None) is not None and args.interval < 1:
        parser.error("--interval must be at least 1 second")
    if getattr(args, "obs_pid", None) is not None and args.obs_pid <= 0:
        parser.error("--obs-pid must be positive")
    if hasattr(args, "lines") and not 1 <= args.lines <= 10000:
        parser.error("--lines must be between 1 and 10000")
    try:
        return args.function(args)
    except (BridgeError, OSError, ValueError, KeyError) as exc:
        print(f"{NAME}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
