# Managed router updates

The router keeps a separate app bundle. Official app updates are disabled in
that copy at the native updater manager and menu capabilities, including late
feature-flag and manual paths. Runtime dependency downloads remain available.
Updating the official app cannot replace the separate router bundle.

## Prepare, then activate

From the source checkout with its documented build tools installed:

```sh
python3 scripts/update_router.py status
python3 scripts/update_router.py prepare
# After finishing tasks and quitting the router:
python3 scripts/update_router.py activate --launch
```

The default source is `/Applications/ChatGPT.app`. Use `--source /path/to/ChatGPT.app`
for a separately extracted official release. The installed destination and shared
Codex home come from the current build report. `install.sh` performs the same
prepare/activate flow and never terminates a running app. If activation is
blocked, the prepared candidate remains available for the next command.

Preparing checks the version and full ASAR hash against reviewed builds, verifies
the official signing team, snapshots the complete source, and repeats source
verification. It then patches reviewed anchors, syntax-checks every changed
JavaScript bundle, packages and signs a separate candidate, verifies the whole
bundle, and checks the bundled CLI version. It does not launch a candidate
against live user history or replace the active app.

Unknown versions, changed hashes, missing or duplicate patch anchors, packaging
errors, signature failures, and unsupported platforms stop the update. They do
not remove or overwrite the working app. An older official installation cannot
silently downgrade a newer router.

Activation checks that neither bundle has running processes, verifies the
candidate again, then rechecks immediately before a macOS atomic bundle swap.
The old app is retained under the state directory's `updates/backups`. There is
no interval where the stable installed path contains a partial app. Candidate,
installed app and backups must reside on the same filesystem; otherwise activation
refuses. An activation lock prevents concurrent swaps. A transaction journal
preserves the intended state if power is lost before metadata is finalized.
An interrupted transaction requires review before another update; its app
bundles are preserved.

## Rollback

```sh
# Finish tasks and quit the router first.
python3 scripts/update_router.py rollback --launch
```

Rollback verifies the previous bundle and compares the shared database schema
with the fingerprint recorded before activation. It refuses if the schema is
unknown or changed. Credentials, routing metadata, desktop profile, database
contents and task history are never rolled back or replaced by snapshots.
Ordinary task writes do not change the schema and are retained.

## Limits and maintenance

This protects the working installation from incompatible incoming updates. It
does not make arbitrary future private UI changes compatible automatically.
New official bundles need a reviewed adapter and hash added to the source,
followed by preparation and verification. Update this source checkout from the
maintained fork before preparing a newly supported version. A successful build
and syntax check do not replace a live visual and account-routing smoke test.

No client modification can guarantee perpetual backend access: OpenAI can
change authentication, service APIs or minimum supported client versions.
Shared SQLite migrations can also prevent a safe binary downgrade. Keeping a
working app is the update strategy, not a promise that an old client can access
the service forever.

The current copy is ad-hoc signed. Native Computer Use/Appshots peer-signing
requirements remain a separate limitation; this updater does not bypass them.

## Current verification

Build 8881 (26.908.40834) is supported alongside corrected build 8576. The source
archive's Ed25519 signature, official bundle signature and notarization were
verified. Both renderer adapters passed syntax and behavioral checks, including
clipboard, local plugin account scope, selected profile guards and task switching.
The actual native update manager was exercised with updates disabled: initialization
settles, later feature flags do not enable Sparkle, and manual check/install stays
idle. Primary runtime installation code remains present.

Portable regression tests cover unsupported builds, changed archive hashes,
failed candidate builds, downgrades, active-process refusal, atomic activation,
rollback, schema drift, transaction failures and preservation of account state.
The prepared build has passed packaging, signing and CLI version checks
(`0.154.0-alpha.6.2`). Its explicit CLI path was verified to force JSONL stdio
through the mux rather than the native daemon/proxy path. Empty-home CLI
initialization, account-read and task-list protocol checks passed; the core
account/task schemas remain compatible. The real running-app activation guard
also refused replacement as expected. Live
GUI verification and a restart into the candidate are separate activation steps.
