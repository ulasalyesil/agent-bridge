"""Behavior tests for the local bridge and its real stdio wire interface."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import tempfile
import subprocess
import sys
import tracemalloc
import unittest
import uuid

from bridge import Bridge, MAX_FILE, TOOLS
from demo import Client, HERE, sync


class BridgeTests(unittest.TestCase):
    def setUp(self):
        parent = HERE / ".tests"
        parent.mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=parent)
        self.root = Path(self.temp.name)
        self.left, self.right = self.root / "alice", self.root / "bob"
        self.a = Bridge(self.left, "alice", 'bob', "codex")
        self.b = Bridge(self.right, "bob", 'alice', "codex")

    def tearDown(self):
        self.temp.cleanup()

    def test_arbitrary_peers_and_partner_only_schemas(self):
        peer, partner = 'studio-7', 'b' + '9' * 31
        left, right = self.root / 'custom-left', self.root / 'custom-right'
        with Client(left, peer, partner) as sender, Client(right, partner, peer) as receiver:
            for client, recipient in ((sender, partner), (receiver, peer)):
                schemas = client.rpc('tools/list')['result']['tools']
                for tool in schemas:
                    if 'to' in tool['inputSchema']['properties']:
                        self.assertEqual(tool['inputSchema']['properties']['to']['enum'], [recipient])
            event = sender.call('post_message', to=partner, text='hello')['event']
            sync(left, right)
            self.assertEqual(receiver.call('read_inbox')['items'], [event])
            # Reopen existing on-disk records using the same identities.
            reopened = Bridge(right, partner, peer, 'codex')
            self.assertEqual(reopened.call('read_inbox', {})['items'], [event])
            for recipient in (peer, 'third-person'):
                result = sender.rpc('tools/call', dict(name='post_message',
                                    arguments=dict(to=recipient, text='refuse')))
                self.assertTrue(result['result']['isError'])

    def test_invalid_peer_names_and_equal_pair_refused(self):
        invalid = ('', 'Alice', '1alice', '-alice', 'a_b', 'a b', '../alice',
                   'a' * 33, 'álîce', 'alice\n')
        root = self.root / 'invalid'
        for name in invalid:
            for peer, partner in ((name, 'bob'), ('alice', name)):
                with self.subTest(peer=peer, partner=partner):
                    with self.assertRaises(ValueError):
                        Bridge(root, peer, partner, 'codex')
        with self.assertRaisesRegex(ValueError, 'must differ'):
            Bridge(root, 'alice', 'alice', 'codex')
        self.assertFalse(root.exists())

    def test_cli_requires_valid_distinct_peer_and_partner(self):
        root = self.root / 'invalid-cli'
        for args in ([], ['--peer', 'alice'], ['--partner', 'bob'],
                     ['--peer', 'alice', '--partner', 'alice'],
                     ['--peer', 'Bad', '--partner', 'bob'],
                     ['--peer', 'alice', '--partner', '../bob']):
            with self.subTest(args=args):
                result = subprocess.run([sys.executable, '-B', str(HERE / 'bridge.py'),
                                         '--root', str(root)] + args, input='',
                                        capture_output=True, text=True, timeout=5)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(result.stdout, '')
                self.assertFalse(root.exists())

    def test_third_party_author_and_recipient_warn(self):
        valid = self.a.call('post_message', dict(to='bob', text='valid'))['event']
        for field in ('from', 'to'):
            record = dict(valid, id=uuid.uuid4().hex)
            record[field] = 'third-person'
            (self.left / 'shared/events' / (record['id'] + '.json')).write_text(json.dumps(record))
        sync(self.left, self.right)
        inbox = self.b.call('read_inbox', {})
        self.assertEqual(inbox['items'], [valid])
        self.assertEqual(len(inbox['warnings']), 2)

    def large_source(self):
        source = self.left / "exports/large.bin"
        chunk = bytes(range(256)) * 4096
        digest = hashlib.sha256()
        with source.open("wb") as stream:
            for _ in range(40):
                stream.write(chunk)
                digest.update(chunk)
        return source, digest.hexdigest()

    def test_send_handoff_round_trip_and_validation(self):
        (self.left / 'exports/tracks').mkdir()
        (self.left / 'exports/tracks/3.txt').write_text('track three')
        (self.left / 'exports/4.txt').write_text('track four')
        event = self.a.call('send_handoff', dict(to='bob', paths=['tracks/3.txt', '4.txt'],
                                               text='Please do motion', project='stage'))['event']
        self.assertTrue(event['handoff'])
        self.assertEqual(event['project'], 'stage')
        self.assertEqual(len(event['files']), 2)
        sync(self.left, self.right, events_only=True)
        self.assertEqual(self.b.call('receive_file', {'id': event['files'][0]})['status'], 'pending')
        sync(self.left, self.right)
        for file_id in event['files']:
            self.assertEqual(self.b.call('receive_file', {'id': file_id})['status'], 'verified')
        self.assertEqual(self.b.call('read_inbox', {})['total'], 3)
        for paths in ([], ['x'] * 51, '4.txt', [4], [''], ['../private'], ['/absolute']):
            with self.assertRaises(ValueError):
                self.a.call('send_handoff', dict(to='bob', paths=paths, text='ask'))
        for project in ('STAGE', 'two words', 'a' * 41):
            with self.assertRaises(ValueError):
                self.a.call('send_handoff', dict(to='bob', paths=['4.txt'], text='ask', project=project))

    def test_handoff_malformed_fields_warn(self):
        base = self.a.call('post_message', dict(to='bob', text='hello'))['event']
        for extra in ({'surprise': True}, {'handoff': False}, {'files': []},
                      {'handoff': True, 'files': ['bad']},
                      {'handoff': True, 'files': [uuid.uuid4().hex], 'project': None},
                      {'handoff': True, 'files': [uuid.uuid4().hex], 'project': '../bad'}):
            record = dict(base, id=uuid.uuid4().hex, **extra)
            (self.left / 'shared/events' / (record['id'] + '.json')).write_text(json.dumps(record))
        records, warnings = self.a.records()
        self.assertEqual(len(records), 1)
        self.assertEqual(len(warnings), 6)

    def test_large_file_verified(self):
        source, sha256 = self.large_source()
        asset = self.a.call("share_file", {"to": "bob", "path": source.name})["event"]
        self.assertEqual(asset["size"], 40 * 1024 * 1024)
        self.assertEqual(asset["sha256"], sha256)
        sync(self.left, self.right)
        result = self.b.call("receive_file", {"id": asset["id"]})
        self.assertEqual(result["status"], "verified")
        self.assertEqual(result["sha256"], sha256)
        destination = Path(result["path"])
        self.assertEqual(destination.stat().st_size, asset["size"])
        digest = hashlib.sha256()
        with destination.open("rb") as stream:
            while chunk := stream.read(1024 * 1024):
                digest.update(chunk)
        self.assertEqual(digest.hexdigest(), sha256)

    def test_file_over_new_cap_rejected(self):
        self.assertEqual(MAX_FILE, 256 * 1024 * 1024)
        source = self.left / "exports/oversized.bin"
        with source.open("wb") as stream:
            stream.truncate(MAX_FILE + 1)
        with self.assertRaisesRegex(ValueError, f"File exceeds {MAX_FILE} bytes"):
            self.a.call("share_file", {"to": "bob", "path": source.name})
        self.assertEqual(list((self.left / "shared/blobs").iterdir()), [])
        self.assertEqual(list((self.left / "shared/events").iterdir()), [])

    def test_corrupted_large_blob_cleanup(self):
        source, _ = self.large_source()
        asset = self.a.call("share_file", {"to": "bob", "path": source.name})["event"]
        sync(self.left, self.right)
        blob = self.right / "shared/blobs" / asset["id"]
        for corruption in ("hash", "size"):
            with self.subTest(corruption=corruption):
                with blob.open("r+b") as stream:
                    if corruption == "hash":
                        stream.seek(35 * 1024 * 1024)
                        stream.write(b"corrupt")
                    else:
                        stream.truncate(asset["size"] - 1)
                with self.assertRaisesRegex(ValueError, "Asset size/hash mismatch. Do not use it; sync and retry."):
                    self.b.call("receive_file", {"id": asset["id"]})
                self.assertEqual(list((self.right / "state/codex/received").iterdir()), [])
                self.assertEqual(list(self.right.rglob("*.tmp")), [])

    def test_large_file_streaming_memory(self):
        source, sha256 = self.large_source()
        tracemalloc.start()
        try:
            asset = self.a.call("share_file", {"to": "bob", "path": source.name})["event"]
            _, peak = tracemalloc.get_traced_memory()
            self.assertLess(peak, 8 * 1024 * 1024)
        finally:
            tracemalloc.stop()
        # The demo's replication stand-in is outside the server memory measurement.
        sync(self.left, self.right)
        tracemalloc.start()
        try:
            result = self.b.call("receive_file", {"id": asset["id"]})
            _, peak = tracemalloc.get_traced_memory()
            self.assertLess(peak, 8 * 1024 * 1024)
        finally:
            tracemalloc.stop()
        self.assertEqual(result["status"], "verified")
        self.assertEqual(result["sha256"], sha256)

    def test_offline_concurrent_writes_and_late_event(self):
        # Two server processes sharing one writer directory cannot clobber records.
        with Client(self.left, "alice", "bob", "one") as a, Client(self.left, "alice", "bob", "two") as b:
            def publish(client):
                return [client.call("post_message", to="bob", text=f"item {i}")["event"]["id"] for i in range(12)]
            with ThreadPoolExecutor(2) as pool:
                futures = [pool.submit(publish, client) for client in (a, b)]
                ids = [item for f in futures for item in f.result()]
        self.assertEqual(self.b.call("read_inbox", {})["total"], 0)
        self.assertEqual(len(set(ids)), 24)
        sync(self.left, self.right)
        self.assertEqual(self.b.call("read_inbox", {})["total"], 24)
        for event_id in ids:
            self.b.call("ack_message", {"id": event_id})
        late = self.a.call("post_message", {"to": "bob", "text": "late"})["event"]
        late["created"] = "2000-01-01T00:00:00+00:00"
        (self.left / "shared/events" / f"{late['id']}.json").write_text(json.dumps(late))
        sync(self.left, self.right)
        self.assertEqual(self.b.call("read_inbox", {})["items"][0]["id"], late["id"])
        self.assertEqual(sync(self.left, self.right), 0)

    def test_receipts_independent_and_persistent(self):
        event = self.a.call("post_message", {"to": "bob", "text": "Hello Bob"})["event"]
        sync(self.left, self.right)
        self.assertEqual(self.b.call("read_inbox", {})["total"], 1)
        self.assertEqual(self.b.call("read_inbox", {})["total"], 1)
        self.b.call("ack_message", {"id": event["id"]})
        restarted = Bridge(self.right, "bob", 'alice', "codex")
        self.assertEqual(restarted.call("read_inbox", {})["total"], 0)
        self.assertEqual(Bridge(self.right, "bob", 'alice', "claude").call("read_inbox", {})["total"], 1)
        self.assertEqual(restarted.call("read_inbox", {"include_acked": True})["total"], 1)
        with self.assertRaises(ValueError):
            self.a.call("ack_message", {"id": event["id"]})
        self.assertEqual(list((self.left / "state/codex/acks").iterdir()), [])

    def test_file_delay_corruption_and_snapshot(self):
        source = self.left / "exports" / "örnek.txt"
        source.write_bytes(b"sample\x00data")
        asset = self.a.call("share_file", {"to": "bob", "path": source.name})["event"]
        source.write_bytes(b"edited later")
        sync(self.left, self.right, events_only=True)
        self.assertEqual(self.b.call("receive_file", {"id": asset["id"]})["status"], "pending")
        sync(self.left, self.right)
        blob = self.right / "shared/blobs" / asset["id"]
        original = blob.read_bytes()
        blob.write_bytes(b"corrupt")
        with self.assertRaisesRegex(ValueError, "hash mismatch"):
            self.b.call("receive_file", {"id": asset["id"]})
        self.assertEqual(list((self.right / "state/codex/received").iterdir()), [])
        blob.write_bytes(original)
        result = self.b.call("receive_file", {"id": asset["id"]})
        self.assertEqual(Path(result["path"]).read_bytes(), b"sample\x00data")
        self.assertEqual(result["sha256"], hashlib.sha256(original).hexdigest())

    def test_context_both_writers_and_pagination(self):
        self.a.call("append_context", {"section": "brief", "text": "DEMO ONLY: shared stage-visual project"})
        self.b.call("append_context", {"section": "work", "text": "Bob: reviewing"})
        self.a.call("append_decision", {"text": "Choice A"})
        self.b.call("append_decision", {"text": "Choice B, needs discussion"})
        sync(self.left, self.right)
        self.assertEqual(self.a.call("read_context", {})["items"], self.b.call("read_context", {})["items"])
        first = self.b.call("read_context", {"section": "decisions", "limit": 1})
        self.assertEqual(first["total"], 2)
        second = self.b.call("read_context", {"section": "decisions", "limit": 1, "offset": first["next_offset"]})
        self.assertNotEqual(first["items"][0]["id"], second["items"][0]["id"])

    def test_traversal_symlinks_and_large_files(self):
        (self.left / "private.txt").write_text("must not share")
        for path in ("../private.txt", str(self.left / "private.txt")):
            with self.assertRaises(ValueError):
                self.a.call("share_file", {"to": "bob", "path": path})
        (self.left / "exports/link").symlink_to(self.left / "private.txt")
        with self.assertRaises(ValueError):
            self.a.call("share_file", {"to": "bob", "path": "link"})
        with (self.left / "exports/large").open("wb") as stream:
            stream.truncate(MAX_FILE + 1)
        with self.assertRaises(ValueError):
            self.a.call("share_file", {"to": "bob", "path": "large"})
        self.assertEqual(list((self.left / "shared/events").iterdir()), [])
        with self.assertRaises(ValueError):
            Bridge(self.right, "bob", 'alice', "../escape")

    def test_malformed_records_and_temporary_files(self):
        event = self.a.call("post_message", {"to": "bob", "text": "valid"})["event"]
        sync(self.left, self.right)
        events = self.right / "shared/events"
        (events / f"{uuid.uuid4().hex}.json").write_text("{")
        (events / f"{uuid.uuid4().hex}.json").write_text("[]")
        (events / ".unfinished.tmp").write_text("{")
        (events / f"{uuid.uuid4().hex}.json").symlink_to(events / f"{event['id']}.json")
        result = self.b.call("read_inbox", {})
        self.assertEqual(result["total"], 1)
        self.assertEqual(len(result["warnings"]), 3)

    def test_mcp_protocol_and_argument_failures(self):
        with Client(self.left, "alice", "bob", version="2024-11-05") as client:
            self.assertEqual(client.version, "2024-11-05")
            self.assertEqual(client.rpc("ping")["result"], {})
            self.assertEqual(len(client.rpc("tools/list")["result"]["tools"]), len(TOOLS))
            self.assertEqual(client.rpc("unknown")["error"]["code"], -32601)
            self.assertEqual(client.rpc("tools/call", {"name": []})["error"]["code"], -32602)
            for arguments in ({"to": "other", "text": "x"}, {"to": "bob"}, {"to": "bob", "text": 3}, {"to": "bob", "text": "x", "from": "spoof"}):
                response = client.rpc("tools/call", {"name": "post_message", "arguments": arguments})
                self.assertTrue(response["result"]["isError"])
            client.process.stdin.write("not json\n")
            client.process.stdin.flush()
            self.assertEqual(client.read()["error"]["code"], -32700)
            client.send([])
            self.assertEqual(client.read()["error"]["code"], -32600)
            self.assertEqual(client.call("post_message", to="bob", text="Still alive")["status"], "queued_locally")
        with Client(self.left, "alice", "bob", version="2099-01-01") as client:
            self.assertEqual(client.version, "2025-11-25")


if __name__ == "__main__":
    unittest.main()
