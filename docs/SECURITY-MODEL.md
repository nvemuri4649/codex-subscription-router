# Personal & Work security model

## Accounts and shared data

Each added account has its own file-backed CLI and MCP OAuth credentials. The
original account keeps its existing credential file rather than duplicating
refresh tokens. Router HTTP/RPC workflow responses contain account metadata,
not credential contents. The normal app-server authentication path still
returns the selected account's token to the desktop as required by the official
app; the router does not log it.

These account homes are not operating-system sandboxes. The same user can read
them, and the backends intentionally share conversation rollouts and the thread
index. Moving an idle task to another account transfers its context to that
account. Changing a default does not move existing tasks, and quota exhaustion
never transfers them automatically.

Managed MCP/plugin configuration is synchronized from the original Codex home.
Inline environment values in that configuration therefore reach added account
homes. Per-account OAuth stores do not make shared inline secrets private to
one account. Root directories use mode `0700`; metadata and credential-store
configuration use `0600`.

## Transport

The local control API binds to `127.0.0.1` and requires a random 256-bit token on
private endpoints. The injected renderer holds that token. CORS permits only
the app origin; CORS does not isolate other processes running as the same user.
Profile images use HTTPS. Optional legacy test endpoints require both the
explicit test setting and normal control authentication.

Remote workflow RPC uses the existing SSH connection, with native host-key
verification. Each remote host owns its credentials and validates its configured
host ID. Additional remote backends use private Unix sockets, not an exposed
TCP listener. Their logs and PID files are private operational data and should
not be uploaded with bug reports. See [remote setup](REMOTE.md).

## App copy and native services

The builder reads the official app, validates the exact supported archive, and
modifies a separate staged copy. It assigns an independent desktop identity,
profile, launcher, and URL scheme and disables the copied updater. Signature
verification is a build check, not an endorsement or a grant of macOS access.
The original app's permissions are not changed.

Vendor Computer Use services retain their original authentication checks. The
current ad-hoc copy does not claim working Computer Use or Appshots. The older
patcher's native helper modification/signing flow is retained upstream code;
its validation does not apply to this builder.

## Scope and distribution

The router is not an OpenAI product. Source availability and local signing do
not establish compliance with OpenAI's software or subscription terms. The
project makes no account-enforcement guarantee or claim of unlimited usage.

Only source is distributed. Do not commit or publish app bundles, official ASAR
archives, extracted vendor files, account homes, tokens, signing keys, or
unredacted captures. Current validation limits are recorded in
[Personal Work validation](PERSONAL-WORK-VALIDATION.md).
