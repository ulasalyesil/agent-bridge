#!/usr/bin/env python3
"""Two-peer local demo and immutable-file replication stand-in. No networking."""
import argparse
import json
from pathlib import Path
import selectors
import subprocess
import sys
import tempfile

from bridge import Bridge, ID, MAX_FILE, MAX_RECORD, atomic_write, regular_bytes, safe_path

HERE = Path(__file__).resolve().parent


def local_root(path):
    root = Path(path).absolute()
    if any(p.is_symlink() for p in (root, *root.parents)) or not root.resolve().is_relative_to(HERE):
        raise ValueError("Demo paths must stay inside this project, without symlinks")
    return root.resolve()


def sync(left, right, events_only=False):
    """Copy final immutable records, never private state or exports. Not Syncthing."""
    left, right = local_root(left), local_root(right)
    if left == right or left.is_relative_to(right) or right.is_relative_to(left):
        raise ValueError("Use distinct, non-nested peer roots")
    count = 0
    for source, destination in ((left, right), (right, left)):
        for category in (("events",) if events_only else ("events", "blobs")):
            source_dir = safe_path(source, f"shared/{category}")
            if not source_dir.exists():
                continue
            for path in sorted(source_dir.iterdir()):
                valid = ID.fullmatch(path.stem) and path.suffix == ".json" if category == "events" else ID.fullmatch(path.name)
                if not valid:
                    continue
                relative = f"shared/{category}/{path.name}"
                data = regular_bytes(safe_path(source, relative), MAX_RECORD if category == "events" else MAX_FILE)
                target = safe_path(destination, relative)
                if target.exists():
                    if regular_bytes(target, MAX_FILE) != data:
                        raise ValueError(f"Immutable-file conflict: {relative}")
                else:
                    atomic_write(target, data)
                    count += 1
    return count


class Client:
    """Tiny wire-level client used by demo/tests, not a model or coding agent."""
    def __init__(self, root, peer, partner, consumer="demo", version="2025-11-25"):
        self.process = subprocess.Popen(
            [sys.executable, "-B", str(HERE / "bridge.py"), "--root", str(root),
             "--peer", peer, "--partner", partner, "--consumer", consumer],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, encoding="utf-8", cwd=HERE)
        self.sequence = 0
        self.selector = selectors.DefaultSelector()
        self.selector.register(self.process.stdout, selectors.EVENT_READ)
        result = self.rpc("initialize", {"protocolVersion": version,
                                         "capabilities": {}, "clientInfo": {"name": "loopback", "version": "1"}})
        self.version = result["result"]["protocolVersion"]
        self.send({"jsonrpc": "2.0", "method": "notifications/initialized"})

    def send(self, value):
        self.process.stdin.write(json.dumps(value) + "\n")
        self.process.stdin.flush()

    def read(self):
        if not self.selector.select(timeout=5):
            raise TimeoutError("MCP subprocess did not respond within 5 seconds")
        line = self.process.stdout.readline()
        if not line:
            raise RuntimeError("MCP subprocess closed unexpectedly")
        return json.loads(line)

    def rpc(self, method, params=None):
        self.sequence += 1
        self.send({"jsonrpc": "2.0", "id": self.sequence, "method": method, "params": params or {}})
        response = self.read()
        if response["id"] != self.sequence:
            raise AssertionError("Unexpected JSON-RPC response ID")
        return response

    def call(self, name, **arguments):
        response = self.rpc("tools/call", {"name": name, "arguments": arguments})
        if "error" in response:
            raise RuntimeError(response["error"])
        result = response["result"]
        if result.get("isError"):
            raise RuntimeError(result["content"][0]["text"])
        return json.loads(result["content"][0]["text"])

    def close(self):
        self.process.stdin.close()
        try:
            self.process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait()
        self.selector.close()
        errors = self.process.stderr.read()
        self.process.stdout.close()
        self.process.stderr.close()
        if self.process.returncode or errors:
            raise RuntimeError(f"Server exit {self.process.returncode}: {errors}")

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()


def demo():
    parent = HERE / ".demo"
    parent.mkdir(exist_ok=True)
    root = Path(tempfile.mkdtemp(prefix="run-", dir=parent))
    alice, bob = root / "alice", root / "bob"
    with Client(alice, "alice", "bob") as a, Client(bob, "bob", "alice") as b:
        tools = a.rpc("tools/list")["result"]["tools"]
        assert len(tools) == 9
        assert any(tool["name"] == "send_handoff" for tool in tools)
        a.call("append_context", section="brief", text="DEMO ONLY: shared stage-visual project")
        a.call("append_context", section="work", text="DEMO ONLY: Alice prepares a palette; Bob reviews the sample.")
        a.call("append_decision", text="DEMO ONLY: Review a small text fixture before any production assets.")
        question = a.call("post_message", to="bob", text="Can you review this sample palette?")["event"]
        assert b.call("read_inbox")["items"] == []
        sync(alice, bob)
        assert b.call("read_inbox")["items"][0]["id"] == question["id"]
        assert len(b.call("read_context")["items"]) == 3
        print("PASS: MCP initialization, tools, offline queue, message and shared context")
        b.call("post_message", to="alice", text="Yes, send the sample.", reply_to=question["id"])
        b.call("ack_message", id=question["id"])
        sync(alice, bob)
        assert a.call("read_inbox")["items"][0]["reply_to"] == question["id"]
        assert b.call("read_inbox")["items"] == []
        print("PASS: reply and explicit consumer receipt")
        (alice / "exports" / "palette.txt").write_text("DEMO palette: navy, amber, cream.\n", encoding="utf-8")
        asset = a.call("share_file", to="bob", path="palette.txt")["event"]
        sync(alice, bob, events_only=True)
        assert b.call("receive_file", id=asset["id"])["status"] == "pending"
        sync(alice, bob)
        received = b.call("receive_file", id=asset["id"])
        assert received["status"] == "verified"
        assert Path(received["path"]).read_bytes() == (alice / "exports" / "palette.txt").read_bytes()
        assert sync(alice, bob) == 0
        assert len(b.call("read_context", section="assets")["items"]) == 1
        print("PASS: manifest-before-bytes, verified file handoff, inventory and duplicate sync")
    with Client(bob, "bob", "alice") as b:
        ids = [r["id"] for r in b.call("read_inbox")["items"]]
        assert question["id"] not in ids and asset["id"] in ids
    print("PASS: receipt persists across process restart")
    print(f"Inspect local peer folders: {root}")
    print("Transport simulated by local copies. No network, real agents, or config changes.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sync", nargs=2, metavar=("LEFT", "RIGHT"))
    parser.add_argument("--events-only", action="store_true")
    args = parser.parse_args()
    if args.sync:
        print(f"Copied {sync(*args.sync, events_only=args.events_only)} immutable files locally")
    else:
        demo()


if __name__ == "__main__":
    main()
