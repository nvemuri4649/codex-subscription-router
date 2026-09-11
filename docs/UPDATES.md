# Native updates and repair alerts

Normal app updates stay enabled. The router does not freeze versions, reject an
incoming native update because its UI patch is unknown, or repair itself.
An official update may replace the modified app, remove its account menu, or
stop subscription routing. The user decides when to ask Codex to repair it.

Account homes, routing metadata, history, source code and recovery copies live
outside the replaceable app bundle. Their preservation makes a later repair
possible; it does not guarantee that arbitrary future clients remain compatible.
The updater itself never restores older credentials or task data.

## Native updater setup

The original Sparkle updater initialization, feature policy and update-menu
capabilities are preserved. Publisher verification remains enabled through the
original `SUPublicEDKey`. `SUBundleName=ChatGPT` uses Sparkle's documented name
override to find the official `ChatGPT.app` payload in the update archive.

The copied app's standalone `Sparkle.framework/Versions/B/Autoupdate` helper,
its XPC services, Updater.app and enclosing framework use the same signing
identity. Leaving Autoupdate signed by OpenAI while the copied app is ad hoc
signed caused the observed installation failure. This correction follows
[Sparkle's signing instructions](https://sparkle-project.org/documentation/sandboxing/#code-signing)
and its [documented configuration](https://sparkle-project.org/documentation/customization/).
It does not spoof a signing team or disable update signature verification.

The revised build passes packaging, signature checks and tests that verify the
native updater capabilities remain present. An actual subsequent native update
installation has not yet been verified. Native Computer Use/Appshots signing
limitations are separate from the updater.

## Notification-only monitoring

```sh
python3 scripts/check_router_health.py
```

The checker reads the installed bundle metadata, router executable markers,
account-menu/task-picker markers and process paths. It never reads credentials,
contacts services, executes the CLI, changes files or triggers a repair.

It reports `healthy`, `not-running`, `repair-needed`, or `inconclusive`, with
short evidence. A closed app is not a failure. Ambiguous startup state, inaccessible
files or an update occurring during the scan do not become confirmed breakage.
This detects missing router components; it is not a full test of every UI or
backend behavior.

This user's hourly Codex notification check stays quiet for healthy/closed apps,
alerts on newly detected breakage, and avoids repeated alerts for unchanged
evidence. It does not repair, rebuild, restart, install, or roll back anything.
The check runs when the Codex automation host is available; it is not a real-time
operating-system alert or part of the app's installer.

## Repair when requested

The repository retains explicit developer rebuild tools and prior app bundles.
When the user asks for repair, Codex can inspect the new official build, update
its compatibility adapter, rebuild and test a replacement, then activate it after
running tasks are finished. The supported-source checks below govern that manual
patching operation, not the normal native updater:

```sh
python3 scripts/update_router.py status
python3 scripts/update_router.py prepare --source /path/to/ChatGPT.app
# Finish tasks and quit the router before installing the repaired copy.
python3 scripts/update_router.py activate --launch
```

A prepared replacement is built from a verified snapshot and kept separate from
the active app. Activation uses an atomic macOS bundle swap, checks for running
processes and keeps the prior bundle. No process is terminated automatically.
The optional explicit `rollback` command refuses unverified database-schema
changes. It is never called by the app updater or notification check.
