# Build 8576 validation

This fork restores the upstream `vrlda` experience at commit `97fbebc` and ports
it to ChatGPT desktop 26.903.71938, build 8576, with Codex CLI 0.153.4. The
experimental Casual/Intensive UI, role routing, and custom remote transport
are removed. Original account-menu and task-subscription component sources
remain unchanged; the compatibility modules bind them to current native UI.

## Behavior

Normal desktop account/auth requests use the account marked `controller`.
Local Codex tasks retain upstream quota-aware selection, sticky ownership,
manual switching, and failover. The original Codex home remains the source of
shared history and managed configuration even when the controller changes.
Listing shared history deduplicates task IDs and preserves saved owners.

ChatGPT cloud histories are account-specific and are not merged. Native remote
connections use their remote host's account; this base router does not pool
subscriptions remotely. The previous experimental remote wrapper was disabled
by a reversible rename, without changing the official CLI or remote credentials.

The setup retained every account home and all 16 saved task owners. Personal
is the normal desktop controller. An authenticated check confirmed two saved
Personal entries referred to the same account and subscription/workspace; the
duplicate is disabled for routing, with its login and home preserved.

## Verified

- All Go tests and `go vet`; race tests for mux and state packages.
- Eleven portable metadata-import and ASAR-integrity tests.
- Reviewed version, build and full source ASAR hash; unique native patch anchors.
- Syntax checks of every changed JavaScript bundle and Python module, shell
  installer, and native launcher.
- Functional checks of original device-code copying through native clipboard,
  task account selection, plugin account scoping and cache separation, reset
  account capture, and selected-profile plan/edit guards.
- Full separate app packaging, Electron ASAR header integrity, ad-hoc signing,
  and `codesign --verify --deep --strict`.
- Live isolated mux: all saved accounts authenticated; account/read resolved to
  Personal; 16 unique existing tasks retained all ownership assignments.
- Live two-turn ephemeral Codex task: automatic selection, successful response,
  sticky follow-up and unchanged normal-account identity. No task rollout or
  SQLite history row persisted; production routing metadata and managed config
  contents stayed unchanged during this isolated test.
- Final app launch and authenticated control API: Personal controller and Work
  enabled and connected, confirmed duplicate Personal disabled.
- The official app ASAR and official remote CLI bytes stayed unchanged.

## Limits

The live test selected Personal because it reports a measured quota window.
The Work usage-based plan reports null quota windows, available credits, and
`unlimited=false`. Upstream assigns unknown weekly quota a score of -1, so it
remains eligible but follows accounts with known positive quota scores. It can
be selected manually per task and serves as a fallback when other accounts
are depleted. This is preserved upstream policy, not a missing parser field.
The base selection algorithm does not model monetary balances or spend controls.

Native GUI automation was unavailable because the Computer Use tool connection
had closed. Popup sizing, original UI behavior and current native bindings were
checked in code and functional fixtures; the final onscreen appearance has not
been visually verified. A real normal ChatGPT/cloud Work generation, live
cross-account quota exhaustion, reset redemption, plugin OAuth/install, and
remote subscription pooling were not tested. No reset credits were consumed.

No team signing certificate is installed. This is an ad-hoc development copy;
Computer Use rejected its sender identity on the final launch. Appshots remains
unverified. Vendor service signatures
and peer checks are retained. The fork does not bypass those checks.
