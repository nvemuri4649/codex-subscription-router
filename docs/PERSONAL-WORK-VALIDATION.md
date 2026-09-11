# Personal Work validation

Local development validation on 11 September 2026. This is a source-only test build, not a released binary.

## Reviewed build

Official desktop 26.903.71938, build 8576, macOS arm64.
Source ASAR SHA-256: `58fef82480b9064e209b5b2fd934992e8d71515aea8084482369cfeaff1b8ee0`.

- Original app archive is read-only build input; its SHA-256 was rechecked unchanged after the live tests.
- Every edited renderer and main-process anchor checked against that exact archive.
- Modified JavaScript syntax checked before packaging.
- Correct ASAR **header** SHA-256 written to Electron integrity metadata.
- Generated app and nested signatures verified with `codesign --verify --deep --strict`.
- Independent application identity, Chromium profile, and disabled copied-app updater verified in the build.

## Automated checks

Go unit tests and vet pass across the router, account store, control API, and remote backend. Race tests cover state, routing, control, and remote transport. All 20 UI behavior tests pass and cover per-draft state, readiness, host scope, project defaults, keyboard control, running tasks, and transport startup. Python tests verify anchor rejection, archive integrity hashing, and existing-login ownership without copying credentials.

Synthetic accounts verify explicit account dispatch, removal of private workflow metadata, preservation of existing task ownership, idle-only account changes, personal controller authentication, and unchanged native quota errors. These tests do not establish real personal-account authentication.

## Live local checks

The final generated desktop starts successfully, its renderer sends workflow requests through the native connection, and its token-authenticated loopback endpoint reports the current Work account connected through ChatGPT authentication. Its startup log contains no JavaScript reference, type, or syntax failure. The final bundle also passes deep signature verification.

A separate router smoke test used the real official app-server and the existing Work login. It verified that missing Personal rejects Casual before task creation, then created an **ephemeral** Intensive task and received the expected model response. No smoke task was saved to normal task history. This verifies account dispatch and generation below the UI; it does not verify clicking Send in the native composer.

## Live SSH checks

An isolated wrapper was installed alongside the existing official Codex CLI on the configured Linux x86-64 SSH host. Official remote CLI version: `0.153.4`. An authenticated WebSocket-over-SSH smoke test verified initialization, matching host-scoped routing status, connected Work authentication, and discovery of four existing tasks. No remote model turn or account change was submitted.

A separate real-CLI transport test with empty temporary homes verified private additional-account servers, persistence after disconnect, and reconnection to the same process. No remote TCP listener is exposed by the router. Existing official CLI, credentials, and active jobs remain in place.

## Pending live checks

Personal ChatGPT sign-in is user-driven and has not been completed. Actual personal/work task transfers, cloud ChatGPT/Work session identity, and per-account native model/usage views remain unverified. GitHub authentication is separate from ChatGPT authentication.

Native visual verification requires an unlocked Mac. The account menu and composer have not yet received a visual acceptance pass. Computer Use/Appshots authentication failed for the ad-hoc app copy during launch; those capabilities are not validated or repaired by this build. Existing official application permissions and vendor service authentication checks have not been changed.

The copied desktop initially logged a remote bundled `sites` catalog error. The same error was reproduced through the official proxy without the router, and subsequent routed and direct reads both succeeded with identical configuration. This suggests transient native catalog readiness; no router-specific plugin regression was reproduced and no plugin configuration was changed during the comparison.
