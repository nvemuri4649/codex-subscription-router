# Source release procedure

The 0.3.0 Personal & Work branch currently identifies a source revision; no
0.3.0 tag or release has been created. Local app construction does not publish
anything.

Only source may be released. Never attach a generated app, official ASAR,
extracted vendor file, credential, account state, or signing material.

1. Keep `VERSION`, `package.json`, and both root versions in `package-lock.json`
   consistent. Update the dated changelog entry and compatibility record.
2. Run `npm ci --ignore-scripts`, `npm run check`, and
   `npm run release:check` with Go, Node, Python, and Xcode command-line tools.
3. Complete the relevant [smoke tests](SMOKE-TEST.md). Record partial validation
   accurately; build/signature checks do not certify login or native UI flows.
4. Review `git diff --check`, staged files, and screenshots for private data.
   Existing screenshots are archived upstream examples, not current evidence.
5. Only when a release is explicitly approved, configure the protected
   `release` environment and create/push the reviewed `vX.Y.Z` tag. Update the
   changelog source link to the actual tag or release if one is created.

The tag-triggered workflow verifies metadata and tests and creates a **draft**
GitHub source release. It never uploads a patched app. Review the draft and
validation record before publishing manually. A source consistency check does
not verify that a remote release or tag exists.
