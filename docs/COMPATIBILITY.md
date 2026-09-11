# Compatibility

## Source version 0.3.0

This is the Personal & Work source branch dated 11 September 2026. It is not a
published 0.3.0 binary or tagged release. The current entry point is
`scripts/build_personal_work.py`.

| Component | Reviewed input |
| --- | --- |
| Official desktop version | `26.903.71938` |
| Official bundle build | `8576` |
| Source `app.asar` SHA-256 | `58fef82480b9064e209b5b2fd934992e8d71515aea8084482369cfeaff1b8ee0` |
| Local architecture | Apple silicon (`arm64`) |
| Generated app | `Codex Personal Work.app` |
| Bundle identifier | `app.codexpersonalwork.desktop` |
| Local control port | `48124` |

The builder rejects a different version, build, or archive hash and rejects
missing or repeated patch anchors. It has no untested-source override. An
upstream app update requires a deliberate review and updated compatibility
checks; matching a version label alone is insufficient.

The generated copy has passed the patch-anchor, syntax, ASAR integrity, and
signature checks recorded in [Personal Work validation](PERSONAL-WORK-VALIDATION.md).
That does not establish successful two-account operation. Personal login,
native visual checks, real task transfers, cloud ChatGPT/Work identity, and
per-account model/usage behavior remain subject to that live validation record.
Native Computer Use and Appshots are unverified for the ad-hoc copy.

## SSH scope

The remote installer supports Linux and macOS on x86-64 and ARM64. Its transport
matches the current app's native WebSocket-over-SSH proxy. Host logins and
workflow preferences are independent. Read-only transport and account-discovery
evidence, including the tested remote CLI version, is recorded in
[remote validation](REMOTE.md). Interactive remote switching remains a separate
check. Remote-control/cloud-paired hosts and cloud Work sessions are not remote
installer targets.

## Historical upstream compatibility

These inputs were documented by the original project or the vrlda fork. They
belong to the retained legacy patcher and reports, not the 0.3.0 builder:

| Upstream source version | Official version | Build |
| --- | --- | --- |
| 0.1.0 | `26.803.61601` | `6396` |
| 0.2.0 | `26.825.32147` | `7303` |
| 0.2.0 | `26.825.41651` | `7345` |

The [archived 0.1.0 report](E2E-REPORT-0.1.0.md) and images under `screenshots/`
show earlier behavior, including automatic quota failover. They are not tests
or screenshots of Personal & Work 0.3.0.
