#!/usr/bin/env python3
"""Perform deterministic, non-building release checks for this repository."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
REPOSITORY = "https://github.com/nvemuri4649/codex-subscription-router"
REQUIRED_FILES = (
    ".github/workflows/ci.yml",
    ".github/workflows/release.yml",
    "CHANGELOG.md",
    "CONTRIBUTING.md",
    "LICENSE",
    "NOTICE.md",
    "README.md",
    "SECURITY.md",
    "VERSION",
    "install.sh",
    "docs/ARCHITECTURE.md",
    "docs/COMPATIBILITY.md",
    "docs/E2E-REPORT-0.1.0.md",
    "docs/PERSONAL-WORK-VALIDATION.md",
    "docs/REMOTE.md",
    "screenshots/README.md",
    "scripts/build_personal_work.py",
    "scripts/patch_composer.py",
    "scripts/install_remote.py",
    "scripts/test_personal_work_build.py",
    "ui/workflow.test.cjs",
    "docs/RELEASING.md",
    "docs/SECURITY-MODEL.md",
    "docs/SMOKE-TEST.md",
    "package-lock.json",
    "package.json",
)
ARCHIVED_SCREENSHOTS = (
    "screenshots/account-menu.png",
    "screenshots/combined-profile-20px.png",
    "screenshots/plugin-account-picker-primary-final.png",
    "screenshots/plugin-account-picker-secondary-final.png",
    "screenshots/quota-all-depleted.png",
    "screenshots/rate-limit-reset-accounts.png",
)
FORBIDDEN_TRACKED_SUFFIXES = {
    ".asar",
    ".cer",
    ".dmg",
    ".key",
    ".mobileprovision",
    ".p12",
    ".pem",
    ".pfx",
    ".pkg",
    ".provisionprofile",
    ".zip",
}
FORBIDDEN_TRACKED_NAMES = {".env", "auth.json", "control-token", "state.json"}
TEXT_SUFFIXES = {"", ".c", ".go", ".json", ".js", ".cjs", ".md", ".py", ".toml", ".yml", ".yaml"}
MACOS_USER_PREFIX = "/" + "Users" + "/"


def fail(message: str) -> None:
    print(f"release check: {message}", file=sys.stderr)
    raise SystemExit(1)


def main() -> int:
    for relative in REQUIRED_FILES:
        if not (ROOT / relative).is_file():
            fail(f"missing required file: {relative}")

    version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    if re.fullmatch(r"\d+\.\d+\.\d+", version) is None:
        fail(f"VERSION is not semantic: {version!r}")

    package = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))
    lock = json.loads((ROOT / "package-lock.json").read_text(encoding="utf-8"))
    if package.get("version") != version:
        fail("package.json version does not match VERSION")
    lock_root_version = lock.get("packages", {}).get("", {}).get("version")
    if lock.get("version") != version or lock_root_version != version:
        fail("package-lock.json version does not match VERSION")
    asar_version = package.get("devDependencies", {}).get("@electron/asar")
    locked_asar = lock.get("packages", {}).get("node_modules/@electron/asar", {})
    if not isinstance(asar_version, str) or re.fullmatch(r"\d+\.\d+\.\d+", asar_version) is None:
        fail("@electron/asar must use an exact version")
    if locked_asar.get("version") != asar_version:
        fail("package-lock.json does not match the declared @electron/asar version")
    if package.get("name") != "codex-personal-work-patcher":
        fail("package.json must identify the Personal & Work patcher")
    if lock.get("name") != package["name"] or lock.get("packages", {}).get("", {}).get("name") != package["name"]:
        fail("package-lock.json package name does not match package.json")
    if package.get("repository", {}).get("url") != f"git+{REPOSITORY}.git":
        fail("package.json repository must identify the personal fork")
    if package.get("homepage") != f"{REPOSITORY}#readme" or package.get("bugs", {}).get("url") != f"{REPOSITORY}/issues":
        fail("package.json homepage and issue URLs must identify the personal fork")
    if package.get("license") != "MIT":
        fail("package.json license does not match LICENSE")
    if not ((ROOT / "install.sh").stat().st_mode & 0o111):
        fail("install.sh is not executable")

    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    dated_heading = rf"^## \[{re.escape(version)}\] - \d{{4}}-\d{{2}}-\d{{2}}$"
    if re.search(dated_heading, changelog, re.MULTILINE) is None:
        fail(f"CHANGELOG.md has no dated entry for {version}")
    # A source branch may carry the next semantic version before a tag exists.
    # Check provenance without requiring or inventing a published release.
    version_link = re.search(rf"^\[{re.escape(version)}\]: (\S+)$", changelog, re.MULTILINE)
    allowed_prefixes = (f"{REPOSITORY}/tree/", f"{REPOSITORY}/releases/tag/")
    if version_link is None or not version_link.group(1).startswith(allowed_prefixes):
        fail(f"CHANGELOG.md has no personal-fork source or release link for {version}")

    compatibility = (ROOT / "docs/COMPATIBILITY.md").read_text(encoding="utf-8")
    if f"## Source version {version}" not in compatibility and f"## Release {version}" not in compatibility:
        fail(f"docs/COMPATIBILITY.md has no entry for {version}")

    screenshot_notice = (ROOT / "screenshots/README.md").read_text(encoding="utf-8")
    if "Archived upstream screenshots" not in screenshot_notice:
        fail("inherited screenshots must be identified as archived upstream examples")

    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    if MACOS_USER_PREFIX in readme:
        fail("README.md contains a machine-specific macOS user path")

    for relative in ARCHIVED_SCREENSHOTS:
        path = ROOT / relative
        if not path.is_file() or path.stat().st_size == 0:
            fail(f"missing or empty archived screenshot: {relative}")
        if not path.read_bytes().startswith(b"\x89PNG\r\n\x1a\n"):
            fail(f"archived screenshot is not a PNG: {relative}")

    tracked_output = subprocess.check_output(
        ["git", "ls-files", "-z"], cwd=ROOT
    )
    tracked = [Path(value.decode("utf-8")) for value in tracked_output.split(b"\0") if value]
    for relative in tracked:
        path = ROOT / relative
        lower_name = relative.name.lower()
        contains_app_bundle = any(part.lower().endswith(".app") for part in relative.parts)
        if contains_app_bundle or relative.suffix.lower() in FORBIDDEN_TRACKED_SUFFIXES:
            fail(f"forbidden release artifact is tracked: {relative}")
        if lower_name in FORBIDDEN_TRACKED_NAMES or lower_name.startswith(".env."):
            fail(f"credential or local-state file is tracked: {relative}")
        if path.is_file() and path.stat().st_size > 10 * 1024 * 1024:
            fail(f"unexpected tracked file larger than 10 MiB: {relative}")
        if path.is_file() and relative.suffix.lower() in TEXT_SUFFIXES:
            text = path.read_text(encoding="utf-8", errors="replace")
            if MACOS_USER_PREFIX in text:
                fail(f"machine-specific macOS user path is tracked: {relative}")

    print(f"release check: v{version} source metadata is consistent (does not assert a published release)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
