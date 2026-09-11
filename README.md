# Codex Subscription Router

This personal fork preserves the original experience from
[`vrlda/codex-subscription-router`](https://github.com/vrlda/codex-subscription-router)
and [`b-nnett/codex-subscription-router`](https://github.com/b-nnett/codex-subscription-router),
with compatibility fixes for ChatGPT desktop **26.908.40834 (8881)** and **26.903.71938 (8576)**.
The experimental Casual/Intensive customization has been removed.

Normal ChatGPT chats and cloud Work tasks use the primary account. Local Codex
coding tasks use the subscription pool below. These are separate histories;
this patch does not merge ChatGPT accounts. Native SSH connections remain
available, using the account configured on that remote host; this original
router does not pool remote subscriptions.

Screenshots below show the upstream interface. See [build 8576 validation](docs/BUILD-8576.md)
for the earlier fork checks and native integration limits. [Native updates and repair alerts](docs/UPDATES.md)
describes the current update policy.

![Multi-subscription account menu](screenshots/account-menu.png)

Use multiple ChatGPT subscriptions from one independent macOS desktop app.

Codex Subscription Router creates a locally patched copy of the official
ChatGPT app, balances new local Codex tasks across connected subscriptions, and keeps every
thread on one subscription so follow-up turns retain conversation context and
benefit from account-level caching.

The official ChatGPT installation is used only as build input and is never
modified. This repository contains source code and build tooling—not OpenAI
binaries or a prebuilt application.

> [!WARNING]
> This is an unofficial, version-sensitive project. It is not affiliated with
> or supported by OpenAI. Review the source and ensure your use complies with
> the terms governing every connected subscription.

![Combined multi-account profile](screenshots/combined-profile-20px.png)

## Highlights

- **Quota-aware routing.** New chats favour weekly allowance that will expire
  sooner, with a bounded boost for accounts holding banked usage resets.
- **Sticky conversations.** Once a thread is assigned, every follow-up returns
  to the same subscription unless it is manually switched or depleted.
- **Automatic failover.** A depleted thread continues through another account
  with quota; if the whole pool is empty, the app shows one combined alert.
- **Shared chat history.** Rollouts and the thread index are visible to every
  connected subscription and the official app, while credentials stay isolated.
- **Per-chat switching.** The pinned thread summary can move an idle chat to
  another connected subscription without creating a new conversation.
- **Native account management.** The existing profile menu shows pooled usage,
  profile photos, plan names, masked emails, and device-code sign-in.
- **Account-aware settings.** Profile statistics can be viewed together or per
  subscription, while the Plugins page can switch Apps and MCP connections
  between accounts.
- **Per-account resets.** The native rate-limit sheet shows and consumes resets
  for the selected subscription.
- **Independent app copy.** The official installation stays intact. Build 8576
  retains vendor helper authentication; Appshots and Computer Use are not
  validated in ad-hoc copies.

## How it works

The patched desktop still opens one app-server connection. A small Go
multiplexer fans that connection out to one official Codex child per account.
Each child has an isolated Codex home, while the multiplexer records the owner
of every thread.

```text
Codex Subscription Router.app
        │
        │ one app-server connection
        ▼
    codex-mux
    ├── Primary       → ~/.codex
    ├── Subscription 2 → isolated Codex home
    └── Subscription 3 → isolated Codex home
             │
             └── thread ID → persistent account owner
```

New-thread routing compares the quota burn rate needed before each weekly reset,
then applies a capped banked-reset boost. Short-window usage, pinned-thread
count, and stable account order break close results. Existing threads do not
migrate merely for load balancing.

Read [the architecture](docs/ARCHITECTURE.md) for the request flow and
[the security model](docs/SECURITY-MODEL.md) for trust boundaries.

## Compatibility

Codex Subscription Router currently targets:

| Component | Supported value |
| --- | --- |
| Platform | macOS on Apple silicon |
| Official ChatGPT versions | `26.908.40834`, `26.903.71938` (current), `26.803.61601`, `26.825.32147`, `26.825.41651` (legacy) |
| Official bundle builds | `8881`, `8576` (current), `6396`, `7303`, `7345` (legacy) |
| Go | 1.26 or newer |
| Node.js | 22.12 or newer |

The patcher verifies the official version, build, ASAR hash and renderer anchors
before packaging a copy. Legacy helper patches also validate native constants. An unknown upstream build
is rejected by default rather than being partially patched. See
[Compatibility](docs/COMPATIBILITY.md) for the recorded hash and test details.

## Requirements

- The official ChatGPT app installed at `/Applications/ChatGPT.app`
- Xcode Command Line Tools
- Go 1.26+
- Node.js 22.12+ and npm
- Optional: an Apple Development or Developer ID Application signing identity

A team-backed signing identity is used when available for reliable Appshots and
Computer Use permissions. Without one, the installer automatically falls back
to an ad-hoc signature; the core router remains usable, while native helpers may
not pass peer checks.

## Install

Run one command. It downloads or updates the source, installs the locked build
dependency, creates the independently signed app, and launches it:

```sh
curl -fsSL https://raw.githubusercontent.com/nvemuri4649/codex-subscription-router/main/install.sh | /bin/bash
```

The source installer prepares a patched copy without stopping running tasks. Activation waits
until the router has been quit; the previous app is retained.

Normal updates subsequently use the native updater and may replace the patch.

The installer keeps its source checkout in
`~/.codex-subscription-router/source`. On an existing installation it uses the
same account state and creates a recoverable backup. Legacy builds require
signing-team continuity; current-build native helper access is not guaranteed. It stops with a clear message
instead of making a partial installation when a prerequisite or upstream
compatibility check fails.

> [!TIP]
> To inspect the installer before running it, open
> [`install.sh`](install.sh) or download it without piping it into a shell.

### Install via prompt

> Install Codex Subscription Router from `https://github.com/nvemuri4649/codex-subscription-router` on this Mac using the repository's supported one-command installer, without modifying the official ChatGPT app or deleting any existing router state. Verify the resulting app signature, report native helper limitations, launch the app, and ask me only if a prerequisite or macOS permission requires interaction.

### Install from a clone

```sh
git clone https://github.com/nvemuri4649/codex-subscription-router.git
cd codex-subscription-router
npm ci --ignore-scripts
python3 scripts/update_router.py install --launch
```

This creates:

- `~/Applications/Codex Subscription Router.app`
- Legacy builds also create `~/Applications/Codex Subscription Router Computer Use.app`;
  build 8576 retains vendor services without modifying their peer authentication.
- an independent desktop profile under
  `~/Library/Application Support/Codex Subscription Router`

The first valid Developer ID Application identity is selected, falling back to
an Apple Development identity. Select a certificate explicitly when needed:

```sh
CODEX_MUX_SIGNING_IDENTITY="Developer ID Application: Example Corp (TEAMID1234)" \
  python3 scripts/patch_app.py
```

Reuse the same Apple team for every rebuild. Changing teams changes the app's
designated requirement and can invalidate existing macOS privacy consent. The
patcher refuses an unexpected team change unless you deliberately pass
`--allow-signing-team-change`.

To explicitly document an ad-hoc build in a scripted invocation:

```sh
python3 scripts/patch_app.py --allow-adhoc-signing
```

The flag is retained for compatibility; ad-hoc signing is already selected
automatically when no certificate is available. Appshots and Computer Use may
not function with an ad-hoc signature.

## Grant macOS permissions

Open **System Settings → Privacy & Security** and grant:

| Permission | Application |
| --- | --- |
| Accessibility | Codex Subscription Router |
| Screen & System Audio Recording | Codex Subscription Router Computer Use |

When macOS offers **Quit & Reopen**, use it. If the app does not relaunch,
reopen Codex Subscription Router manually. If the Computer Use row does not
appear, press the plus button and choose
`~/Applications/Codex Subscription Router Computer Use.app`.

Do not select the official ChatGPT or Codex Computer Use helper for this build;
the independent app has its own identity and permission rows. macOS may also
request Automation access the first time Computer Use controls another app.

## Add subscriptions

1. Open the profile menu at the bottom of the sidebar.
2. Select **Add another subscription**.
3. Complete the displayed device-code sign-in in your browser.
4. Return to Codex Subscription Router and wait for the account row to appear.

While the code is visible, clicking away does not dismiss the menu. Clicking
the code copies it and opens the verification page.

The profile menu displays combined usage followed by one row per subscription.
Each row shows both five-hour and weekly usage with reset times. Email addresses
remain masked until hovered. The final row always starts another sign-in.

## Routing behavior

| Situation | Behaviour |
| --- | --- |
| New chat | Assigned by quota-at-risk, banked resets, and short-window pressure |
| Follow-up | Sent to the thread's persisted account owner |
| Manual switch | Resumes an idle chat on the selected subscription |
| Owner depleted | Continued through another account with capacity |
| Every account depleted | Combined quota alert with the next known reset |
| Account disabled | Excluded from routing and pooled usable quota |

The subscription assigned to the current thread appears in its pinned summary.

## Profiles, plugins, and resets

**Profile statistics** begin in a combined view with overlapping account
photos. Select a photo to see only that subscription's identity and statistics;
select it again to return to the combined view.

**Settings → Plugins** includes a subscription picker. Plugin definitions and
managed MCP configuration are shared, while Apps, connection status, and OAuth
login are scoped to the selected subscription.

**Rate-limit resets** remain native to the app, with an account picker added to
the sheet. Selecting a subscription changes the displayed balance and ensures
the reset is consumed only for that account.

![Account-scoped plugin connections](screenshots/plugin-account-picker-secondary-final.png)

## Update or rebuild

Normal native updates stay enabled. An update can remove or break the router;
the user decides when to request a repair. The notification-only health check
reports detected component loss and never fixes or rolls back the app.

Logins, routing metadata, history, source code and prior bundles remain outside
the updated app. Explicit developer rebuild tools are available when Codex is
called in to repair a new version; their source compatibility checks do not
block native updates. See [updates and repair alerts](docs/UPDATES.md).

## Local data and security

| Path | Purpose |
| --- | --- |
| `~/.codex` | Original credentials, shared Codex history, and configuration |
| `~/Library/Application Support/Codex Subscription Router/router/state.json` | Current account metadata and sticky task ownership |
| `~/Library/Application Support/Codex Subscription Router/router/accounts/<id>/codex-home` | New isolated account homes |
| `~/Library/Application Support/Codex Subscription Router/router/control-token` | Loopback control token |
| `~/Library/Application Support/Codex Subscription Router/updates` | Prepared candidates, previous bundles, activation journal |
| `~/Library/Application Support/Codex Subscription Router/backups` | Earlier recoverable app backups |
| `~/Library/Application Support/Codex Subscription Router/desktop` | Independent desktop profile |
| `~/.codex-mux` | Legacy build state |

Imported accounts keep their existing home paths. Do not remove those directories
while the router still references them. The primary ChatGPT account can differ
from the original home used for shared Codex history and configuration.

The control service binds only to `127.0.0.1` and protects private routes with a
random 256-bit token. OAuth tokens stay inside their account's Codex home and
are never returned by the control API. Account directories are owner-only.

Plugin configuration is intentionally synchronized from the original Codex home.
Inline secrets inside shared MCP configuration are therefore copied to each
isolated account home; the account homes are not separate secret boundaries.

See [SECURITY.md](SECURITY.md) before reporting a credential, signing, or local
control-service issue.

## Development and verification

```sh
npm ci --ignore-scripts
npm run check
npm run release:check
```

The Go backend and injected renderer have no runtime third-party dependencies.
`@electron/asar` is build-only. Deterministic UI preview routes are enabled only
when `CODEX_MUX_UI_TESTS=1` is present at launch and remain token-authenticated.

The signed-app test procedure is in [SMOKE-TEST.md](docs/SMOKE-TEST.md). The
current fork checks are recorded in [BUILD-8576.md](docs/BUILD-8576.md).
[E2E-REPORT-0.1.0.md](docs/E2E-REPORT-0.1.0.md) records the historical upstream run.

## Known limitations

- Normal ChatGPT and cloud Work use the primary account; remote hosts use their
  own account. The pool applies to local Codex tasks.
- Plans that report no quota windows remain eligible but rank below measured
  positive quota in the original algorithm. They can be selected manually;
  missing windows do not establish unlimited usage.

- Normal updates are enabled and can remove the router UI/routing. A repair
  requires a user request and, where needed, new compatibility anchors.
- The initial merged history fetch is limited to 500 threads per account.
- Combined “skills explored” totals can count the same skill once per account
  because the upstream profile response exposes counts rather than skill IDs.
- Generated app bundles are tied to one macOS user and signing team.
- Releases are source-only; patched OpenAI binaries are never distributed.

## Contributing and releases

Read [CONTRIBUTING.md](CONTRIBUTING.md) before submitting changes. Releases use
the source-only process in [RELEASING.md](docs/RELEASING.md) and require a
completed signed-app smoke test for the exact tagged commit.

## License

Project source is available under the [MIT License](LICENSE). ChatGPT, Codex,
and the official macOS application are OpenAI products and are not covered by
this license.
