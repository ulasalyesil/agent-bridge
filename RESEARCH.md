# agent-bridge research

Researched 2026-10-04. Scope: two people, two Macs, Claude Code and Codex, shared stage-visual work. No device pairing, transfers, installs or account changes were performed.

## Recommendation

Use **one Syncthing project folder plus a small local stdio MCP server on each Mac**. Store each message, decision, context update and asset manifest in its own immutable JSON file. Store asset bytes separately. Keep agent read receipts and incoming working copies outside the synced folder.

This is my engineering recommendation, not a transport vendor guarantee. Syncthing adds one installation and a pairing step per Mac. In exchange, ordinary file writes become unattended delivery on a LAN or over the internet. It avoids building a network service, authentication system or discovery layer. Both coding clients can call the same local tools. No new model subscription or API key is required.

A shared iCloud folder wins on initial setup if both already use iCloud. I prefer Syncthing here for explicit folder selection, observable sync status and local files without cloud placeholder hydration. AirDrop remains a useful manual tool, but is a poor mailbox transport. A private git repo is good for code history, but pull/merge/push and large visual assets make it a poor live inbox.

Syncthing is a background service, so this is not literally server-free. The bridge itself has no network listener or central host. Both Macs need overlapping online time for direct or relayed sync. Relays are not offline storage. Messages remain on the sender until the peer reconnects. [Syncthing setup](https://docs.syncthing.net/intro/getting-started.html), [relaying](https://docs.syncthing.net/users/relaying.html).

## Agent protocols and existing tools

| Option | What exists | Fit for two people |
| --- | --- | --- |
| Google-originated A2A | Agent Cards, messages, tasks, artifacts and streaming/push updates across independent agents. It is now an open A2A project. [Overview](https://a2a-protocol.org/), [specification](https://a2a-protocol.org/dev/specification/) | Good interoperability for hosted agents. Requires agent endpoints, authentication and lifecycle handling. Too much for a two-person file mailbox. The prototype is not A2A-compatible. |
| MCP shared server | Clients call tools through local stdio or remote Streamable HTTP. MCP supplies the interface, not shared memory or a scheduler. [Transports](https://modelcontextprotocol.io/specification/2025-11-25/basic/transports) | A remote MCP service could own one authoritative mailbox. That adds a host and access control. Local stdio plus replicated files is smaller. |
| MCP Agent Mail | Existing coding-agent inboxes, threads, identities and advisory file reservations, backed by Git and SQLite. [Project](https://github.com/Dicklesworthstone/mcp_agent_mail) | Closest ready-made option. Worth revisiting if search, leases and a web UI become necessary. Cross-machine use still needs an accessible service and authentication. Do not sync its live SQLite database as shared memory. |
| AutoGen distributed runtime | Experimental host/worker runtime using gRPC, with agents in separate processes or machines. [Microsoft documentation](https://microsoft.github.io/autogen/stable/user-guide/core-user-guide/framework/distributed-agent-runtime.html) | Real distributed orchestration, but requires writing agents for that runtime and operating a host. It does not simply connect existing Claude/Codex sessions. |
| MCP reference memory server | Persistent knowledge graph with entities, relations and observations, stored in a configurable local file. [Source and README](https://github.com/modelcontextprotocol/servers/tree/main/src/memory) | Useful memory API. Two separate instances are not automatically shared memory. A common remote service could share it; concurrent replication of its mutable backing file is not a merge strategy. |
| Claude Code agent teams | Experimental coordinated Claude sessions, shared tasks and mailboxes. Teams use local state. [Agent teams](https://code.claude.com/docs/en/agent-teams) | Helps one person's Claude instances. Do not synchronize Claude's internal team/config directories between people. |
| Claude cross-session messages and channels | Cross-session messaging includes the user's other machines through Remote Control. Channels can inject events into an open session. [Cross-session messaging](https://code.claude.com/docs/en/cross-session-messaging), [channels](https://code.claude.com/docs/en/channels) | Current cross-machine features exist, so “Claude only messages locally” would be inaccurate. They are not a documented shared mailbox between two people's mixed Claude/Codex clients. File bytes are not attached by mentioning a path. |
| Codex subagents and MCP | Codex orchestrates subagents and can use local or remote MCP tools. Codex can also be exposed as an MCP server for SDK orchestration. [Subagents](https://developers.openai.com/codex/multi-agent), [MCP](https://developers.openai.com/codex/mcp), [SDK example](https://developers.openai.com/cookbook/examples/codex/codex_mcp_agents_sdk/building_consistent_workflows_codex_cli_agents_sdk) | The reviewed docs do not establish an automatic two-owner Mac-to-Mac shared project memory feature. Use a common tool interface and explicit project records. |

A team subscription or shared tool configuration does not itself synchronize working files or conversation history. The proposed bridge shares deliberately published context, not private transcripts. An arriving message also does not automatically wake a stopped coding agent.

## macOS transport comparison

Setup costs below are qualitative estimates for two people, not measured installation times. “Headless” means routine transfers after initial consent and setup. Receiver automation means a running process can discover bytes, not that a coding agent automatically starts a turn.

| Transport | Setup cost | Remote? | Agent can trigger headlessly? | Receiver can notice arrival? |
| --- | --- | --- | --- | --- |
| AirDrop through `NSSharingService` | Low manual setup; a helper app is extra work | Nearby devices; do not rely on it as a remote queue | Can invoke the sharing service. No documented recipient-addressed unattended send API was established | After acceptance, poll/watch the saved file. No documented bridge delivery callback or automatic agent wakeup |
| AirDrop through `shortcuts run` | Create a shortcut once, grant its permissions | Same AirDrop limits | CLI can invoke a shortcut and pass files. Interactive actions can still show UI | Same saved-file monitoring; command completion is not a peer acknowledgment |
| AirDrop through AppleScript | UI scripting and Accessibility permission | Same AirDrop limits | Can drive UI in a logged-in session. Brittle recipient selection and prompts; not reliable headless transport | Poll/watch a chosen destination after acceptance. Filename collisions and mixed Downloads contents need handling |
| Bonjour/mDNS + local HTTP | Medium/high development; discover service, pair/authenticate, allow network access | LAN by default; needs VPN or hosted routing remotely | Yes after setup | Yes, HTTP handler can persist records and signal a local watcher |
| iCloud Drive shared folder | Low if both have Apple Accounts and iCloud enabled; invite and accept once | Yes, with internet | Ordinary local writes work after setup; sync timing and downloads are OS-managed | Poll/watch hydrated local files; placeholder presence alone does not prove bytes are readable |
| Private git repository | Accounts, access, clones and credentials; recurring sync workflow | Yes, via remote | Yes with existing credentials | Poll fetch, then integrate changes. Push alone does not update the other working tree |
| Tailscale + Taildrop | Install/login on both; network membership and policy | Yes | CLI file operations exist, but Taildrop is restricted to the same user's devices | macOS saves received files; watcher/polling is possible. Taildrop is not a two-way shared folder |
| Syncthing | Install on both, exchange device IDs, accept one shared folder | Yes, direct or encrypted relay | Yes: write a file; daemon replicates it | Yes: scan final files or use filesystem events. Sync is asynchronous; validate asset hashes before use |

### Transport evidence and caveats

- **AirDrop:** Apple's user flow chooses a nearby recipient and normally asks the recipient to accept. Transfers between devices signed into the same Apple Account can bypass acceptance, which does not cover two designers with separate accounts. Mac files may land in Downloads or an app. [Apple guide](https://support.apple.com/guide/mac-help/use-airdrop-to-send-items-to-nearby-devices-mh35868/mac).
- **Native helper:** AppKit exposes `NSSharingService.Name.sendViaAirDrop`. This establishes a sharing UI integration, not a stable CLI recipient selector or unattended receiver. [Apple API](https://developer.apple.com/documentation/appkit/nssharingservice/name/sendviaairdrop).
- **Shortcuts:** Apple documents `shortcuts run` and `--input-path`. That does not remove UI from a shortcut action that needs interaction. An AirDrop shortcut would need checking on the installed macOS version. [CLI guide](https://support.apple.com/guide/shortcuts-mac/run-shortcuts-from-the-command-line-apd455c82f02/mac).
- **AppleScript:** UI automation can click controls through System Events and requires Accessibility permission. I did not find a supported AirDrop scripting command that targets a recipient without UI. [Apple UI scripting guide](https://developer.apple.com/library/archive/documentation/LanguagesUtilities/Conceptual/MacAutomationScriptingGuide/AutomatetheUserInterface.html).
- **Bonjour:** Apple provides service discovery on local networks. Discovery is not authentication or file transport. Guest Wi-Fi isolation and blocked multicast can prevent discovery. An HTTP bridge would still need authorization and remote connectivity. [Bonjour](https://developer.apple.com/bonjour/).
- **iCloud:** Folder collaboration supports invited people and edit permission. Pin/download the folder for agent access and allow delayed materialization. The docs do not promise transactional delivery of multiple files or a latency bound. [Apple folder sharing](https://support.apple.com/en-gb/guide/mac-help/mchl91854a7a/26/mac/26).
- **Git:** Non-fast-forward updates can require integration before push. Polling and merges add work to every conversation, and binary edits do not merge usefully. [Git push](https://git-scm.com/docs/git-push).
- **Tailscale:** Taildrop explicitly excludes other users' devices, even on the same tailnet. Do not share an account to work around that. Tailscale networking plus a separate authenticated HTTP or SSH service could work, but is a different, heavier architecture. [Taildrop](https://tailscale.com/docs/features/taildrop), [CLI file commands](https://tailscale.com/docs/reference/tailscale-cli).
- **Syncthing:** Concurrent edits to one path can create conflict copies. Temporary files are moved into place after transfer. Independent files can still arrive in any order. Separate immutable event files avoid shared-log append conflicts; the receiver must wait for the matching asset bytes. [Synchronization](https://docs.syncthing.net/users/syncing.html).

## Proposed data model and workflow

```text
Alice's agents -> local stdio MCP -> alice/shared/
                                      <=> Syncthing <=>
Bob's agents -> local stdio MCP -> bob/shared/

Each peer also has exports/ and state/, which are never synchronized.
shared/events/<uuid>.json      messages, brief notes, decisions, work updates
shared/blobs/<uuid>            immutable asset snapshots
state/<consumer>/acks/         explicit local acknowledgments
state/<consumer>/received/     verified local asset copies
```

1. Each server has a configured peer identity and partner identity (for example `alice` and `bob`) and a local consumer identity such as `codex` or `claude`. A person's agents share the inbox but have independent read receipts.
2. `post_message` records a question, handoff or status. UUID filenames avoid concurrent appends to one mutable file. `read_inbox` polls; `ack_message` acknowledges only after the agent has dealt with an item.
3. `share_file` snapshots a staged file under `exports/`, calculates SHA-256 and publishes a manifest. A successful write means queued locally, not delivered remotely. `receive_file` validates bytes before exposing a local working copy.
4. `append_context` adds brief, work or note entries. `append_decision` adds a dated decision. `read_context` returns their history and asset inventory. Work entries name the owner and task in text. This is advisory coordination, not a distributed task lock.
5. Use explicit replies to confirm receipt or accept a handoff. Keep the request ID in the reply. Correct context with a new entry; never edit or delete published events during normal use.

Readers scan IDs, rather than using a timestamp watermark that could miss late files. Timestamps are for display, not a global ordering guarantee. Concurrent or contradictory decisions remain visible for the people to resolve. Local atomic writes do not imply a transaction across two Macs.

Only share a dedicated project folder. Peer-authored text and files are data, not authority to run code or bypass the local user's permissions. Identities in JSON are attribution, not signatures. A trusted person with folder access can change history. File replication is not backup, and deletions can propagate.

## Prototype boundary

After this document is written, implement Python stdlib only, newline-delimited JSON-RPC over stdio, with the MCP initialization and tool-call subset. No model calls, network listener or background agent launcher.

Prove the workflow with two local peer directories and two stdio subprocesses. A local copy routine will stand in for Syncthing, including delayed asset delivery and repeated sync. This tests application semantics, not Syncthing networking, macOS privacy permissions or real client compatibility.

Later, manually test two Macs: pair only the dedicated folder, send a harmless sample, confirm a reply and matching hash, sleep/reconnect, then repeat on separate networks. None of that is authorized for this run.

For a later AirDrop feasibility test, explicitly select the other person's device in Finder or a helper, send one harmless file, accept it and inspect the destination. Test shortcuts/helper UI separately. A real transfer is required to validate recipient selection and receipt, so this research stops before that step.
