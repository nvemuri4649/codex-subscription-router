# Compatibility

The patcher is intentionally tied to known ChatGPT desktop bundle structures.
It verifies every modified renderer, main-process, and native binary anchor and
stops instead of applying a partial patch.

## Release 0.1.0

| Component | Tested value |
| --- | --- |
| Official ChatGPT version | `26.803.61601` |
| Official bundle build | `6396` |
| `app.asar` SHA-256 | `d5a44ed9e2f1db5f81dbbe85408aed256f3203c5b16f00817bb9d7cd941343cf` |
| Architecture | Apple silicon (`arm64`) |

## Release 0.2.0

### Build 7303

| Component | Tested value |
| --- | --- |
| Official ChatGPT version | `26.825.32147` |
| Official bundle build | `7303` |
| `app.asar` SHA-256 | `0462b03e878f0e78b223b849ee14cbba0de043f2c16acebee163cb95daa622ef` |
| Architecture | Apple silicon (`arm64`) |

Build 7303 regenerates the renderer bundles and uses a dedicated, fail-closed
set of native UI anchors. The original build 6396 patch remains supported.

### Build 7345

| Component | Tested value |
| --- | --- |
| Official ChatGPT version | `26.825.41651` |
| Official bundle build | `7345` |
| `app.asar` SHA-256 | `c089b63abb7ca4a751072c0da434248db13c32bed9c363e1b7e5428584b0576d` |
| Architecture | Apple silicon (`arm64`) |

Build 7345 retains the reviewed build-7303 renderer anchors. The full patch,
repack, signing, and signature verification flow was repeated against this
exact ASAR.

A different official version may work when all anchors remain identical, but
it is unverified. The patcher rejects a version, build, or ASAR hash mismatch by
default; `--allow-untested-source` is an explicit diagnostic override. Never
weaken an anchor-count or binary-constant check merely to make a new build
complete. Review the upstream change and update the patch deliberately.

## Release 0.2.1

### Build 8576

| Component | Reviewed value |
| --- | --- |
| Official ChatGPT version | `26.903.71938` |
| Official bundle build | `8576` |
| `app.asar` SHA-256 | `58fef82480b9064e209b5b2fd934992e8d71515aea8084482369cfeaff1b8ee0` |
| Bundled Codex CLI | `0.153.4` |
| Architecture | Apple silicon (`arm64`) |

The normal `scripts/patch_app.py` entry point dispatches this build to
`scripts/build_current.py`. Current-build source mismatches are rejected even
with the legacy diagnostic override. The renderer ports reuse upstream UI
components with reviewed native aliases; the current packager uses Electron's
ASAR header hash and keeps downloaded CLI updates from bypassing the mux.

State lives in `~/Library/Application Support/Codex Subscription Router/router`
and the desktop profile in the sibling `desktop` directory. Account metadata
may be imported using `build_current.py --import-state PATH --controller-account ID`.
Existing credential homes stay in place and must not be deleted after import.
See [build validation](BUILD-8576.md) for tested and unverified behavior.

## Release 0.2.2

| Component | Reviewed value |
| --- | --- |
| Official version | `26.908.40834` |
| Build | `8881` |
| ASAR SHA-256 | `bb40cd8811887363104a19291346af9595632e0e956316a1086b274fb8e3eafc` |
| Download bytes | `575938573` |
| Official signing team | `2DC432GLL2` |

The source archive was verified against its Sparkle Ed25519 signature, then
extracted and verified with strict code signing and Gatekeeper notarization.
Build 8576 remains supported with the corrected updater capability gates.
Source bundles are snapshotted and revalidated before extraction and packaging.
See [managed updates](UPDATES.md) for update and rollback guarantees and limits.

## Release 0.2.3

Builds 8576 and 8881 retain native updater behavior. The original `SUPublicEDKey`
is preserved and `SUBundleName=ChatGPT` enables the official archive's app name
matching. Sparkle's standalone Autoupdate executable and its nested helper
bundles use the copied app's signing identity. Update verification is retained.
An actual subsequent native update installation has not yet been verified.
Native updates can remove the patch; monitoring reports that for manual repair.
