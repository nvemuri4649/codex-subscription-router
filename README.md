# Codex Personal Work

A personal/work subscription handler for the Codex Mac app. Keep everyday chats and ChatGPT Work on your personal account, and explicitly choose your work account for intensive coding tasks. One familiar interface, two clear workflows.

**Casual → Personal · Intensive → Work**

This is an unofficial, source-only fork of [Codex Subscription Router](https://github.com/b-nnett/codex-subscription-router), incorporating [vrlda's shared-history work](https://github.com/vrlda/codex-subscription-router). It builds a separate local app from your installed official desktop. It does not distribute OpenAI software.

## What changes

- The existing profile menu has compact Personal and Work rows, with account assignments under Manage. Sign-in codes are selectable and have a separate native Copy action.
- A compact Casual/Intensive selector lets you choose a workflow before starting a task.
- An idle task's Workflow section lets you change its account explicitly.
- Projects can remember a default workflow, scoped to the execution host.
- Existing tasks keep their account; signing in or changing a default does not move them.
- Local and opted-in SSH hosts use the same workflow protocol. Remote accounts are authenticated on that host.
- Missing accounts show a connection requirement. Running tasks cannot switch accounts.
- Quota exhaustion stays a normal Codex error. There is no automatic cross-account failover, combined quota, or promise of unlimited usage.

The controls use the current app's React runtime, native profile menu, task summary, typography, and theme colors. They are added to the existing interface rather than a separate dashboard.

## Current compatibility

The reviewed patch targets **macOS Apple silicon, desktop 26.903.71938 (build 8576)**. The builder checks the exact source archive hash and every edited code anchor. A different build stops before creating an app; updates need a reviewed compatibility change.

The copy has an independent application identity and desktop profile. Its updater is disabled; update the official app normally, then rebuild only when the new version is supported.

**Validation boundaries:** automated routing, HTTP, UI behavior, remote WebSocket, and patch checks are included. Cloud ChatGPT/Work identity, OS privacy permissions, and the complete two-account workflow must be checked after signing into both accounts. An ad-hoc build is for local testing; Computer Use/Appshots may need additional signing and privacy setup. See [validation](docs/PERSONAL-WORK-VALIDATION.md) for the current run.

## Build a local copy

Requirements: the official app at `/Applications/ChatGPT.app`, Apple Command Line Tools, Node 22.12+, npm, Python 3, and Go 1.26+.

```sh
git clone https://github.com/nvemuri4649/codex-subscription-router.git
cd codex-subscription-router
npm ci --ignore-scripts
npm run check:personal-work
python3 scripts/build_personal_work.py --check-only
python3 scripts/build_personal_work.py
open "$HOME/Applications/Codex Personal Work.app"
```

The first build uses your current Codex home as the **Work** account and leaves Personal unassigned. This matches the intended setup of a work laptop. You can change either assignment in the profile menu. The default for new tasks is Casual; connect Personal or select Intensive to begin. GitHub sign-in is separate from ChatGPT account sign-in.

Use `--destination PATH` for another app location, `--codex-home PATH` for the existing account home, and `--state PATH` for independent router/desktop state. Use `--force` to replace a stopped copy while retaining a backup. Never point the destination at the official app.

## Accounts and data

The original app bundle is never changed. The router stores role mappings, task ownership, and secondary logins under `~/Library/Application Support/Codex Personal Work`. The original Codex home remains the Work account's credential owner and task store, avoiding stale duplicate refresh-token files. The copied app and official app share local Codex history; the desktop window profile is separate.

Adding Personal uses the official device-code flow and a separate credential home. Credentials stay local and are excluded from this repository. The local control API binds to loopback and requires a random token. Remote controls travel through the existing authenticated SSH connection, without exposing a public HTTP endpoint.

Choosing another account for an existing task resumes its context under that account. Choose the account appropriate for that task's data and organization. Plugin definitions and managed MCP configuration are shared by the upstream design; account homes are not separate secret boundaries.

The ChatGPT/Work cloud experience has additional authentication state beyond local Codex tasks. Routing its account metadata to Personal is implemented, but it is **not claimed verified** until real personal sign-in and cloud-session tests pass.

## SSH projects

See [remote setup](docs/REMOTE.md). The original remote Codex binary, login, and jobs remain in place. Only this copied desktop opts into the separately installed wrapper. A host without the wrapper remains a normal remote Codex connection and does not claim to support Casual/Intensive routing.

## Tests

```sh
npm run check:personal-work
go test -race ./internal/state ./internal/mux ./internal/control ./internal/backend ./cmd/codex-mux
```

Tests exercise role mapping, inheritance, private routing metadata removal, missing login, wrong-host rejection, idle-only transfers, history ownership, native quota errors, and SSH transport. Tests with synthetic accounts are distinct from a live two-account sign-in check.

## License and service terms

Fork code is MIT-licensed; see [LICENSE](LICENSE) and [NOTICE.md](NOTICE.md). OpenAI's desktop and services retain their own licenses and terms. Account switching support does not imply approval of desktop modification. This project is not affiliated with or endorsed by OpenAI.
