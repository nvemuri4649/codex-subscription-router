# Personal & Work smoke test

Use the exact source build in [compatibility](COMPATIBILITY.md). Record the
commit, macOS version, signing mode, source hash, and which checks actually
passed. A successful build or a synthetic-account test is not a completed
interactive smoke test.

## App copy

- Confirm the official app archive is unchanged and the generated copy passes
  `codesign --verify --deep --strict`.
- Launch the copy and confirm it opens its independent window/profile rather
  than opening a window in the original app's process.
- Confirm the native profile menu, composer, and task details render in light
  and dark themes with keyboard-accessible Casual/Intensive controls.

## Accounts and workflows

- Confirm the existing account is explicitly Work and Personal is unassigned.
  Casual should show a connection requirement, not use Work implicitly.
- Sign in to Personal through the official device-login page. Verify the
  displayed personal/work identities and that app ChatGPT/Work requests use
  Personal after the native account refresh.
- Start a Casual local task and an Intensive local task. Verify actual account
  assignment and follow-up continuity, not only the selected UI label.
- Confirm two draft composers can choose different modes without changing each
  other's default. Verify the choice survives asynchronous worktree creation.
- Set a project default, open a fresh task there, and verify inheritance. Check
  that an unrelated project and existing tasks remain unchanged.
- Switch an idle task explicitly, verify its history remains available, and
  confirm a running task cannot switch.
- Confirm imported work history is deduplicated and retains Work ownership after
  adding Personal or changing defaults.
- Using synthetic tests or a legitimately limited account, verify that the
  native usage-limit error remains on the chosen account. No task should
  continue automatically on another subscription.
- Check native account/model/usage views against the selected identity. Never
  present Personal's usage as the Intensive account's usage.

## SSH hosts

- Install the opt-in wrapper following [REMOTE.md](REMOTE.md), using the exact
  native host ID. Verify host-scoped account identities and project defaults.
- Confirm an unconfigured host uses its current account, disables workflow
  controls, and still starts native tasks. A failing configured router must
  block workflow submission rather than substitute local credentials.
- Verify one authorized task and idle switch on the configured host, then
  disconnect/reconnect and confirm continuity and ownership.

## Configuration and native access

- Change an ordinary shared setting after mapping Personal and confirm it
  survives configuration synchronization and a restart.
- Treat Computer Use/Appshots as unverified until exercised on this exact
  signing configuration. Do not reuse the historical upstream report as proof.

Record results and outstanding checks in
[PERSONAL-WORK-VALIDATION.md](PERSONAL-WORK-VALIDATION.md). Keep private account
identities, device codes, and conversation content out of published evidence.
