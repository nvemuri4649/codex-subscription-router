# Personal & Work architecture

The 0.3.0 source branch builds **Codex Personal Work**, a separate macOS app
with bundle identifier `app.codexpersonalwork.desktop`. The official app is
read-only build input. The copy has its own Chromium profile and URL scheme,
and its updater is disabled. See [compatibility](COMPATIBILITY.md) for the exact
reviewed input and the limits of validation.

## Accounts and task routing

The copy replaces its bundled `codex` executable with a Go multiplexer and
retains the official executable as `codex.real`. The desktop sees one JSON-RPC
app-server connection; the router manages an official backend for each account.

Account roles are explicit: **Casual** selects Personal and **Intensive** selects
Work. The installer assigns the existing account to Work because that is this
fork's intended work-laptop setup; it leaves Personal unassigned. It does not
infer roles from an email address, subscription plan, or remaining quota.

For a new task, precedence is:

1. A mode chosen for that composer draft, carried in private `_codexWorkflow`
   metadata on that task's creation request.
2. The nearest configured parent project on the same host.
3. The persisted default for new tasks, initially Casual locally.

Private metadata is removed before the official backend receives the request.
Draft selection is captured before asynchronous submission work; tasks with an
explicit selection do not reuse a prewarmed task from another account. A project
default changes only through the separate project-default action.

Once created, a task keeps its recorded account. Changing the global default,
project default, or account roles does not move existing tasks. Existing history
without a router assignment belongs to the original account. Shared task lists
are deduplicated and never overwrite an existing assignment.

An explicit mode change on an existing task reads its rollout and resumes it on
the selected account, preserving its task ID. The router checks its active-turn
tracking and the official task status before moving it. This is an intentional
transfer of that task's context to the other account. Missing, disabled, or
signed-out accounts produce an actionable error; they never select a different
account silently.

**Quota does not select accounts.** The selected backend reports its normal
usage-limit error. There is no automatic failover, retry on another account, or
claim of unlimited Work capacity.

## App identity and shared configuration

Once Personal is mapped, unscoped authentication and account requests use that
backend. In particular, the desktop's `getAuthStatus` request supplies the token
used for ChatGPT and cloud Work requests. Changing the mapped personal account
emits the native `account/updated` notification, which clears the desktop's
cached token and refreshes account state. Selecting Intensive for a coding task
does not change this app identity. Until Personal is mapped, setup uses the
original account; Casual task creation remains unavailable.

This describes the implemented routing and native cache invalidation path.
Actual personal sign-in, cloud sessions, model availability, and native usage
views still require the live checks in [the validation record](PERSONAL-WORK-VALIDATION.md).
Cloud conversation lists are not merged across accounts by this router.

Managed configuration comes from the original Codex home. Unscoped `config/*`
and `experimentalFeature/*` requests stay on that source so changes survive
synchronization. Added account homes receive managed configuration every two
seconds, excluding credential-store settings and project trust. CLI and MCP
OAuth credentials use separate file stores. Inline secrets in shared MCP
configuration are shared configuration, not isolated per-account secrets.

## Local storage

By default, the app profile is under
`~/Library/Application Support/Codex Personal Work/desktop`, and router metadata
and added account homes are under the sibling `router` directory. The original
account normally retains `~/.codex`; its credentials are referenced, not copied.

All account backends use the original `CODEX_SQLITE_HOME`. Added accounts link
`sessions` and `archived_sessions` to the original rollout store. Existing
isolated rollouts are merged with collision checks and preserved backups before
linking. Consequently the official app and the copy share and can update local
history. Separate desktop profiles do not create separate copies of that data.

## Local and SSH control

The copied renderer's local account controls use an HTTP service bound to
`127.0.0.1:48124`. Private endpoints require a random 256-bit control token;
CORS permits the app's `app://-` origin. Responses contain account metadata,
readiness, role mappings, and task selections, not OAuth credentials.

The workflow controls also use these JSON-RPC methods through the selected
host's existing connection:

- `personalWork/routing/read`
- `personalWork/routing/update`
- `personalWork/mode/set`

HTTP equivalents are `/v1/routing` and `/v1/thread-mode`. A supplied host ID
must match the router's configured host. The same filesystem path on two hosts
has separate project preferences.

SSH integration is opt-in. The patched desktop uses a host's installed
`~/.local/share/codex-personal-work/codex` wrapper when present and otherwise
retains the original SSH proxy. The wrapper bridges the native WebSocket
handshake over SSH stdio. Each host keeps its own logins and routing state;
local credentials never authenticate the remote router. Additional remote
account backends use private Unix sockets and survive disconnects. See
[remote setup and transport validation](REMOTE.md).

## Build and retained upstream code

The current builder verifies the source version, build number, ASAR hash, and
unique patch anchors before repacking. It updates Electron's ASAR header
integrity hash, builds the router and independent launcher, signs the copy, and
verifies its signatures. Vendor Computer Use services retain their existing
authentication checks; native Computer Use and Appshots are not certified for
the ad-hoc copy.

The older `scripts/patch_app.py`, profile/reset helpers, diagnostic bridge,
upstream screenshots, and historical reports remain as development references.
Their former quota-pooling UI, automatic routing, and helper-signing claims do
not describe the current Personal & Work builder.
