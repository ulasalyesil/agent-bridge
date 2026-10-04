# Public status

## What works

- A Python 3.9+ standard-library stdio MCP mailbox for any two configured peers.
  Nine tools cover messages, replies, consumer-specific acknowledgements, shared
  context, decisions, file snapshots, and grouped handoffs. Records retain their
  existing format; malformed or unrelated-peer records produce warnings.
- Streamed SHA-256/size verification for files up to 256 MiB; grouped handoffs
  accept up to 50 files. Manifests can arrive before bytes without exposing an
  unverified copy. Consumer receipts survive restarts.
- Installer previews, receipt-based identities, client registrations, pairing,
  doctor, and uninstall preservation. Reinstall upgrades registrations missing
  `--partner`. Examples use `alice` and `bob`.
- Optional fixed intake with project routing, configurable recipient role,
  collision-safe job files, blocked executable formats, draft `HANDOFF.md`,
  verified-file receipts, bounded retries/logs, and local notifications.
- Optional watcher and session hooks. Hook status reads only local files, prints
  at most one line, and exits 0 on internal errors. A consumer's acknowledgement
  clears that handoff's intake-failure alert.

## Verification

- **69 tests passed on each interpreter** with `-B -m unittest test_bridge test_bridgectl`:
  `/usr/bin/python3` (3.9.6) and `python3` (3.14.0). Tests use temporary homes
  and checkouts, fake client/service executables, injected errors, and a
  loopback-only Syncthing HTTP fixture. No real HOME, client configuration,
  launchd, or Syncthing changes are part of this suite.
- `python3 -B demo.py` exercises two MCP subprocesses and local file copying:
  initialization, messages/replies, context, manifest-before-bytes delivery,
  verified files, and persistent acknowledgements. It prints four PASS lines.
- A prior real-client loopback used Claude Code and Codex on one Mac with local
  copying as the transport. It verified a 40 MiB file handoff and reply round
  trip, including matching received bytes/hash. This was a local trial of the
  earlier registration format, not a two-Mac transport test.
- Automated coverage includes arbitrary/invalid peer identities, partner-only
  tool schemas, unrelated-record warnings, registration migration, prompt
  substitutions, receipt names, and hook acknowledgement/error handling.

## Unverified and limits

- Real Syncthing between two Macs: pairing, remote delivery, sleep/reconnect,
  separate networks, and production assets.
- Real launchd startup and WatchPaths delivery, macOS TCC/Files and Folders
  permissions, visible notifications, and launchd-held log descriptors.
- The Codex `SessionStart` hook event name/schema and `/hooks` trust flow, plus
  actual startup-hook execution in both clients.
- Real intake runs: Codex authentication, image arguments, model output, sandbox
  and configuration enforcement; real sips previews and visual contact sheets.
  The model connection needs connectivity even with sandbox networking disabled.
- No signed records, pruning, distributed locks, or exactly-once sends. Both
  folder participants are trusted; replication is not a backup. The fixed
  intake prompt is not an independent security boundary.
