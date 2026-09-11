# Architecture

The independently built desktop uses bundle identifier `app.cdxmux.multi`.
Build 8576 stores router state and its desktop profile under
`~/Library/Application Support/Codex Subscription Router`. Legacy builds use
`~/.codex-mux` and a separately identified Computer Use helper. Current builds
leave the vendor helper identities and peer authentication unchanged.

Codex Subscription Router replaces the copied app's bundled `codex` executable
with a small Go multiplexer and keeps the original binary beside it as
`codex.real`.

## Request routing

The desktop app opens one JSON-RPC app-server connection to the multiplexer.
The multiplexer starts one real app-server child for every enabled account,
each with its own credential-bearing `CODEX_HOME`. Normal account/authentication
requests use the account marked `controller`. All children use the original
Codex home as `CODEX_SQLITE_HOME`, so one thread index is visible to both desktop
apps.

New threads are assigned using a quota-urgency score: weekly percentage
remaining divided by the hours until that account resets. Banked usage resets
add a capped bonus, while short-window usage, existing pinned-thread count, and
stable account order break close results. Reset-credit metadata is fetched in
parallel, cached for five minutes, and treated as neutral when unavailable.
Once a thread ID is known, `state.json` persists its owner. Requests, responses,
approvals, and notifications are rewritten only as needed to preserve one
coherent desktop session.

If the owner is depleted, the multiplexer resumes the rollout on an account
with capacity, starts a continuation turn, and updates ownership. An idle thread
can also be switched explicitly from its pinned summary. Threads do not migrate
for ordinary load balancing.

## Account isolation

The original account uses `~/.codex`. Added accounts use
`accounts/<id>/codex-home` beneath the router state directory. Imported accounts
retain their existing home paths. Managed configuration is copied from
the original Codex home, excluding credential-store settings and project trust.
Each isolated account forces file-backed CLI and MCP OAuth credentials. Its
`sessions` and `archived_sessions` paths link to the Primary rollout store;
existing isolated rollouts are merged with collision checks and preserved
backups before the links are installed.

## Desktop integration

The patcher extracts `app.asar`, verifies exact upstream anchors, inserts the
account UI, preserves native updates, and repacks the archive with an updated
integrity hash. The app receives a separate Chromium profile and URL scheme.

Legacy builders re-sign the Computer Use service, runtime, and callers under
one Apple team with separate helper identity/socket. Build 8576 leaves vendor
service signatures and authentication intact; an ad-hoc app copy may therefore
be rejected by those helpers. This fork does not bypass their peer checks.

## Plugin behavior

Plugin definitions and managed MCP configuration are shared. The Plugins page
adds an account selector and marks Apps, MCP status, and MCP OAuth requests with
the selected account ID. The multiplexer removes that private routing marker
before forwarding the strict RPC request to the chosen child.

## Control API

The renderer talks to a loopback-only HTTP service on port 48123. All private
routes require a random 256-bit token. CORS is limited to the copied app's
`app://-` origin. The service exposes account metadata, aggregated usage and
profile data, thread ownership, login/logout actions, and an authenticated SSE
event stream; it never returns OAuth tokens.
