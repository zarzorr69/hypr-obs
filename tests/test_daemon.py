"""Subprocess tests with an IPC-command simulator, not a live compositor.

Exercise the real daemon, saved OBS files, child hyprctl invocations, heartbeat
and signal cleanup. A Unix event socket is used when the host permits it;
otherwise the real periodic recovery path is checked. The simulator cannot
establish whether Qt/Wayland receives a physical keyboard event.
"""
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import tempfile
import textwrap
import time
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "hypr_obs.py"

SIMULATOR = r'''#!/usr/bin/env python3
import json,os,pathlib,re,sys
base=pathlib.Path(os.environ['BRIDGE_SIM_DIR'])
args=sys.argv[1:]
if '-i' in args:
    i=args.index('-i'); del args[i:i+2]
json_mode='-j' in args
if json_mode:args.remove('-j')
command=args[0]
state_path=base/'binds.json'
state=json.loads(state_path.read_text())
def save():
    temp=base/'binds.tmp'
    temp.write_text(json.dumps(state))
    temp.replace(state_path)
def add(keys,target,description):
    parts=keys.split(' + ')
    mods=sum({'SHIFT':1,'CTRL':4,'ALT':8,'SUPER':64}[x] for x in parts[:-1])
    state.append({'key':parts[-1],'keycode':0,'modmask':mods,'description':description,'dispatcher':'pass','arg':target,'submap':''})
if command=='instances':
    print(json.dumps([{'instance':os.environ['HYPRLAND_INSTANCE_SIGNATURE'],'pid':int(os.environ['BRIDGE_SIM_PARENT'])}]))
elif command=='clients':print((base/'clients.json').read_text())
elif command=='binds':print(json.dumps(state))
elif command=='eval':
    if os.environ['BRIDGE_SIM_BACKEND']!='lua':print('unknown request');sys.exit(1)
    payload=args[1]
    quoted=r'("(?:\\.|[^"\\])*")'
    for match in re.finditer(r'local h=__obs_hotkey_bridge and __obs_hotkey_bridge\['+quoted+r'\]',payload):
        description=json.loads(match[1]);state[:]=[x for x in state if x['description']!=description]
    pattern=r'hl\.bind\('+quoted+r',hl\.dsp\.pass\((?:\{window=)?'+quoted+r'\}?\),\{description='+quoted+r'\}\)'
    for match in re.finditer(pattern,payload):add(*(json.loads(x) for x in match.groups()))
    save();print('ok')
elif command=='--batch':
    for operation in args[1].split(' ; '):
        if operation=='keyword submap reset':print('ok');continue
        if operation.startswith('keyword bindd '):
            mods,key,description,dispatcher,target=map(str.strip,operation[len('keyword bindd '):].split(',',4))
            add(' + '.join(mods.split()+[key]),target,description)
        elif operation.startswith('keyword unbind '):
            mods,key=map(str.strip,operation[len('keyword unbind '):].split(',',1))
            mask=sum({'SHIFT':1,'CTRL':4,'ALT':8,'SUPER':64}[x] for x in mods.split())
            state[:]=[x for x in state if (x['modmask'],x['key'])!=(mask,key)]
        else:raise RuntimeError('Unexpected operation '+operation)
        print('ok')
    save()
else:raise RuntimeError('Unexpected command '+str(args))
'''


class DaemonLifecycle(unittest.TestCase):
    def exercise(self, backend):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            executable = base / "hyprctl"
            executable.write_text(SIMULATOR)
            executable.chmod(0o700)
            obs = base / "obs-studio"
            profile = obs / "basic/profiles/Main/basic.ini"
            profile.parent.mkdir(parents=True)
            (obs / "user.ini").write_text("[Basic]\nProfileDir=Main\n")

            def save_hotkey(key):
                profile.write_text('[Hotkeys]\nOBSBasic.StartRecording=' +
                                   json.dumps({"bindings": [{"key": "OBS_KEY_" + key, "control": True}]}) + '\n')

            save_hotkey("F9")
            clients = base / "clients.json"

            def set_client(address):
                clients.write_text(json.dumps([{"pid": os.getpid(), "address": address,
                                               "class": "com.obsproject.Studio", "title": "OBS 33.0.0",
                                               "workspace": {"id": 8}, "size": [800, 600]}] if address else []))

            set_client("0xabc")
            (base / "binds.json").write_text("[]")
            state = base / "state"
            state.mkdir()
            settings = base / "settings.json"
            settings.write_text(json.dumps({"token": "simulation", "state_dir": str(state), "interval": 1.0,
                                            "hypr_config": str(base / "hyprland.conf"), "obs_config": str(obs)}))
            env = {**os.environ, "PATH": str(base) + os.pathsep + os.environ.get("PATH", ""),
                   "XDG_RUNTIME_DIR": str(base / "runtime"),
                   "HYPRLAND_INSTANCE_SIGNATURE": "bridge_test_" + base.name,
                   "BRIDGE_SIM_PARENT": str(os.getpid()), "BRIDGE_SIM_DIR": str(base),
                   "BRIDGE_SIM_BACKEND": backend}
            event_path = base / "runtime/hypr" / env["HYPRLAND_INSTANCE_SIGNATURE"] / ".socket2.sock"
            event_path.parent.mkdir(parents=True)
            server = None
            connection = None
            try:
                server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                server.bind(str(event_path))
                server.listen(1)
                server.settimeout(5)
            except OSError:
                if server:
                    server.close()
                server = None
            output = (base / "daemon.log").open("w+")
            process = subprocess.Popen([sys.executable, str(SCRIPT), "daemon", "--settings", str(settings)],
                                       env=env, stdout=output, stderr=output)
            try:
                if server:
                    connection, _ = server.accept()
                def wait_for(predicate, seconds=7):
                    deadline = time.monotonic() + seconds
                    while time.monotonic() < deadline:
                        if process.poll() is not None:
                            output.seek(0)
                            self.fail("Daemon exited: " + output.read())
                        current = json.loads((base / "binds.json").read_text())
                        if predicate(current):
                            return current
                        time.sleep(0.05)
                    output.seek(0)
                    self.fail("Timed out waiting for simulated binds: " + output.read())

                first = wait_for(lambda x: len(x) == 1 and x[0]["key"] == "F9")
                self.assertEqual(first[0]["arg"], "address:0xabc")
                # A compositor reload removes dynamic bindings. The real
                # socket2 event or periodic recovery should reconstruct them.
                (base / "binds.json").write_text("[]")
                if connection:
                    connection.sendall(b"configreloaded>>\n")
                wait_for(lambda x: len(x) == 1 and x[0]["key"] == "F9", seconds=18)
                save_hotkey("F10")
                wait_for(lambda x: len(x) == 1 and x[0]["key"] == "F10")
                # Stream Suite stores its shortcuts outside basic.ini. Verify
                # the running daemon notices both introducing and editing them.
                profile.write_text("[Hotkeys]\n")
                aitum_path = profile.parent / "aitum.json"
                def save_aitum_hotkey(key):
                    aitum_path.write_text(json.dumps({"outputs": [
                        {"name": "Game Recording", "start_hotkey": [
                            {"key": "OBS_KEY_" + key, "control": True}]}]}))
                save_aitum_hotkey("F11")
                wait_for(lambda x: len(x) == 1 and x[0]["key"] == "F11")
                save_aitum_hotkey("F12")
                wait_for(lambda x: len(x) == 1 and x[0]["key"] == "F12")
                set_client(None)
                wait_for(lambda x: not x)
                set_client("0xdef")
                wait_for(lambda x: len(x) == 1 and x[0]["arg"] == "address:0xdef")
                process.send_signal(signal.SIGTERM)
                process.wait(timeout=5)
                self.assertEqual(process.returncode, 0)
                self.assertEqual(json.loads((base / "binds.json").read_text()), [])
                status = json.loads((state / "status.json").read_text())
                self.assertEqual(status["daemon_pid"], 0)
                self.assertIn("stopped", status)
            finally:
                if process.poll() is None:
                    process.terminate()
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait()
                output.close()
                if server:
                    server.close()
                if connection:
                    connection.close()

    def test_hyprlang_daemon_lifecycle(self):
        self.exercise("hyprlang")

    def test_lua_daemon_lifecycle(self):
        self.exercise("lua")


if __name__ == "__main__":
    unittest.main()
