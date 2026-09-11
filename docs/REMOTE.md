# Personal and Work on SSH hosts

The patched app supports a separate router on each SSH host. A local account
selection does **not** authenticate a remote host. Each host owns its logins,
role assignments, project defaults, and task ownership. The `Intensive` choice
on a remote task selects that host's Work account.

This integration is opt-in. Without the remote wrapper, the patched app keeps
the original SSH connection. The workflow selector reports that the host uses its current account and
disables mode changes; native task submission continues. A configured router
that is disconnected or failing shows an error and blocks its workflow
submission. Neither path substitutes a local account.

## Install

Disconnect the host in the patched app while installing or changing account
roles. Keep the original Codex CLI installed on the host. From this repository:

```sh
python3 scripts/install_remote.py my-ssh-alias \
  --host-id remote-ssh-discovered:my-ssh-alias \
  --primary-role work --default-mode intensive --dry-run
```

Use the **exact host ID shown by the app**, which may differ from the SSH alias.
Remove `--dry-run` to install. The helper probes the remote OS and architecture,
cross-compiles locally, and transfers the router binary and a small launcher.
It supports Linux and macOS, on x86-64 or ARM64. Add `--real-codex /absolute/path`
if the official CLI is not on the noninteractive SSH PATH, and `--go /path/to/go`
if Go is not on the local PATH. SSH authentication uses the existing SSH config
and host-key verification; the helper never requests or saves an SSH password.

The launcher is installed at
`~/.local/share/codex-personal-work/codex`. The patched app discovers that exact
executable during native SSH startup. The original app and terminal `codex`
command continue to use the original executable. Router state lives in
`~/.codex-pw`; the official remote account remains in its existing `CODEX_HOME`.
Reinstalling preserves existing role and workflow preferences.

`--primary-role work` assigns the already authenticated remote account to Work.
This is an explicit assignment, not an inference from an email or plan name.
The default is Intensive because this installation is for coding hosts. Choose
`--default-mode casual` if desired; Casual requires a separate Personal login.

## Add the personal account on a host

The installer prints the exact command for that host. In general:

```sh
ssh -t my-ssh-alias \
  '~/.local/share/codex-personal-work/codex personal-work login --role personal --label Personal'
```

Complete the official Codex device login yourself in the browser. Credentials
are written by the official CLI into the remote account's isolated home. They
are never copied from the laptop, uploaded by the installer, or stored in the
repository. This command refuses to replace the existing primary account's
login. Reconnect the host after login.

To inspect non-secret routing metadata on the host:

```sh
~/.local/share/codex-personal-work/codex personal-work status
```

## Transport and task continuity

The current native app sends a WebSocket connection through SSH stdio using
`codex app-server proxy`. The remote launcher accepts that same WebSocket
handshake and bridges JSON RPC to the router. The router connects to the native
remote server for the primary account. Additional accounts use private Unix
sockets under `~/.codex-pw/sockets`, with their own official app-server process.
These processes survive an SSH disconnect and are reused on reconnect. Account
homes share the host's thread index and rollout storage, matching the local
router design.

No TCP port is opened on the remote host. Workflow requests use the existing
SSH channel: `personalWork/routing/read`, `personalWork/routing/update`, and
`personalWork/mode/set`. Every request is checked against the installed host ID.
There is no cross-host account fallback, automatic quota failover, or claim
that the Work subscription has unlimited capacity.

Additional account logs and PIDs are stored beside their private sockets as
`personal-work.log` and `personal-work.pid`. They contain ordinary app-server
logs and should be treated as private local data. The launcher creates state
directories with mode `0700` and metadata with `0600` permissions.

## Validation and current limits

The isolated integration test exercises the installed official CLI's real
WebSocket transport using empty temporary account homes. It verifies primary
and additional account initialization, confirms both are signed out, checks
that disconnecting leaves their servers alive, and reconnects to the same
additional-account process. Run it explicitly with:

```sh
CODEX_MUX_TEST_REAL_CODEX=/Applications/ChatGPT.app/Contents/Resources/codex \
  go test ./internal/backend -run TestRealRemoteAppServerTransport -v
```

The regular tests also exercise native WebSocket framing over an in-memory
duplex stream, workflow RPC delivery, and clean disconnect behavior. The real
transport test was validated against the CLI bundled with app build `8576`.

An authenticated read-only SSH smoke test also passed on the configured Crusoe
host using official remote CLI `0.153.4`: native WebSocket initialization,
host-scoped routing status, the connected Work account, and existing task
discovery. No model generation was submitted and no account was changed. An
interactive task and account change through the finished native UI still need
an end-to-end smoke test after personal login. This installer
does not configure remote-control/cloud-paired hosts or ChatGPT cloud Work
sessions. Those use different transports. Active tasks still require an idle
state before changing their account, and existing tasks started by a separate
official desktop session may remain owned by that session's backend until
their turn completes.

## Disable

Disconnect the host in the patched app, rename
`~/.local/share/codex-personal-work/codex` to `codex.disabled`, and reconnect.
The patched app returns to the original SSH proxy. Existing primary Codex
credentials, projects, and the original executable are unchanged.

Additional-account servers may still be finishing tasks. Leave them running
until those tasks complete. To stop one, inspect its `personal-work.pid` and
verify that the process command is the official CLI with `--listen unix://`
pointing to the matching private socket before sending that PID `SIGTERM`.
Keep `~/.codex-pw` if you want to preserve accounts and routing preferences.
