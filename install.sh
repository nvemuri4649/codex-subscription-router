#!/bin/bash
set -euo pipefail

# Source-only installer. Builds a local copy from the user's official app.
source_dir="${CODEX_PERSONAL_WORK_SOURCE:-$HOME/Library/Application Support/Codex Personal Work/source}"
for tool in git node npm python3 go xcrun codesign; do
  command -v "$tool" >/dev/null || { echo "Missing required tool: $tool" >&2; exit 1; }
done
if [ ! -d "$source_dir/.git" ]; then
  mkdir -p "$(dirname "$source_dir")"
  git clone https://github.com/nvemuri4649/codex-subscription-router.git "$source_dir"
else
  if [ -n "$(git -C "$source_dir" status --porcelain)" ]; then
    echo "Source checkout has local changes. Commit or move them before updating." >&2
    exit 1
  fi
  git -C "$source_dir" pull --ff-only
fi
cd "$source_dir"
npm ci --ignore-scripts
npm run check:personal-work
python3 scripts/build_personal_work.py "$@"
echo 'Open the generated Codex Personal Work.app, then connect Personal in the profile menu.'
