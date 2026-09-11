#!/usr/bin/env python3
"""Report router patch health without network requests or changing the installation.

This inspects installed artifacts and executable process paths, not authentication,
account quota, or model availability. It does not execute the bundled CLI, repair
the app, restart processes, install updates, or send notifications.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path, PurePosixPath
import plistlib
import struct
import subprocess


DEFAULT_STATE = Path.home() / "Library/Application Support/Codex Subscription Router"
GO_BUILD_MAGIC = b"\xff Go buildinf:"
GO_ROUTER_PATH = b"path\tgithub.com/b-nnett/codex-subscription-router/cmd/codex-mux\n"


def running_executables() -> list[Path]:
    result = subprocess.run(["ps", "-axo", "pid=,comm=", "-ww"], check=True,
                            capture_output=True, text=True)
    paths = []
    for line in result.stdout.splitlines():
        fields = line.strip().split(None, 1)
        if len(fields) == 2 and fields[0].isdigit() and fields[1].startswith("/"):
            paths.append(Path(fields[1]).resolve())
    return paths


def file_stamp(path: Path):
    try:
        stat = path.stat()
    except FileNotFoundError:
        return None
    return stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns


def has_router_build_info(path: Path) -> bool:
    if not path.is_file():
        return False
    markers = [GO_BUILD_MAGIC, GO_ROUTER_PATH]
    found = [False] * len(markers)
    overlap = max(map(len, markers)) - 1
    tail = b""
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            data = tail + chunk
            found = [present or marker in data for present, marker in zip(found, markers)]
            if all(found):
                return True
            tail = data[-overlap:]
    return False


def renderer_markers(path: Path) -> dict:
    """Read only relevant packed JavaScript entries; never extract an archive."""
    with path.open("rb") as stream:
        header = stream.read(16)
        if len(header) != 16:
            raise ValueError("invalid ASAR header")
        size_pickle, header_size, payload_size, json_size = struct.unpack("<4I", header)
        if size_pickle != 4 or not 0 < json_size <= 32 * 1024 * 1024:
            raise ValueError("unsupported ASAR header")
        if header_size != payload_size + 4 or json_size > header_size - 8:
            raise ValueError("invalid ASAR header length")
        contents = json.loads(stream.read(json_size))
        data_start = 8 + header_size
        total_size = path.stat().st_size
        if data_start > total_size or not isinstance(contents, dict) or not isinstance(contents.get("files"), dict):
            raise ValueError("invalid ASAR file table")
        targets = {"accountMenu": [], "taskSelector": []}

        def walk(files: dict, prefix: str = ""):
            for name, entry in files.items():
                relative = f"{prefix}/{name}" if prefix else name
                if "files" in entry:
                    walk(entry["files"], relative)
                elif relative.startswith("webview/assets/"):
                    filename = PurePosixPath(relative).name
                    if filename.startswith("app-primary-") and filename.endswith(".js"):
                        targets["accountMenu"].append(entry)
                    elif filename.startswith("local-conversation-thread-") and filename.endswith(".js"):
                        targets["taskSelector"].append(entry)
        walk(contents["files"])
        tokens = {"accountMenu": b"function CodexMuxAccountMenu(",
                  "taskSelector": b"function CodexMuxThreadSubscription("}
        result = {}
        for key, entries in targets.items():
            if not entries:
                result[key] = None  # A renamed future layout is not proof of removal.
                continue
            present = False
            for entry in entries:
                if entry.get("unpacked") or "link" in entry:
                    raise ValueError("renderer storage layout is not recognized")
                offset, size = int(entry["offset"]), int(entry["size"])
                if offset < 0 or not 0 <= size <= 64 * 1024 * 1024 or data_start + offset + size > total_size:
                    raise ValueError("invalid ASAR entry bounds")
                stream.seek(data_start + offset)
                present = present or tokens[key] in stream.read(size)
            result[key] = present
        return result


def _result(status: str, reason: str, evidence: dict) -> dict:
    return {"status": status, "reason": reason, "evidence": evidence}


def check_health(state: Path = DEFAULT_STATE, app: Path | None = None) -> dict:
    """Return healthy, not-running, repair-needed, or inconclusive JSON evidence."""
    state = state.expanduser().resolve()
    report_path = state / "build.json"
    evidence = {}
    try:
        report_stamp = file_stamp(report_path)
        if report_stamp is None:
            return _result("inconclusive", "No recorded router build is available.", evidence)
        report = json.loads(report_path.read_text())
        if not isinstance(report, dict):
            return _result("inconclusive", "The recorded build metadata is not recognized.", evidence)
        recorded_app = report.get("app")
        if not report.get("sourceBuild") or (app is None and not recorded_app):
            return _result("inconclusive", "The recorded build does not identify an installation.", evidence)
        bundle = (app or Path(recorded_app)).expanduser().resolve()
        if not bundle.is_dir():
            return _result("inconclusive", "The recorded app was not found; it may have moved.", evidence)
        resources = bundle / "Contents/Resources"
        plist_path, archive = bundle / "Contents/Info.plist", resources / "app.asar"
        wrapper, real_cli = resources / "codex", resources / "codex.real"
        observed_paths = (plist_path, archive, wrapper, real_cli)
        before = [file_stamp(path) for path in observed_paths]
        info = plistlib.loads(plist_path.read_bytes())
        if not isinstance(info, dict):
            return _result("inconclusive", "The app metadata is not recognized.", evidence)
        evidence.update({"recordedBuild": str(report["sourceBuild"]),
                         "installedBuild": str(info.get("CFBundleVersion", "unknown")),
                         "bundleIdentifier": str(info.get("CFBundleIdentifier", "unknown")),
                         "buildChanged": str(info.get("CFBundleVersion")) != str(report["sourceBuild"])})
        if info.get("CFBundleIdentifier") not in ("app.cdxmux.multi", "com.openai.codex"):
            return _result("inconclusive", "The recorded path contains an unexpected app identity.", evidence)
        evidence["routerWrapperPresent"] = has_router_build_info(wrapper)
        evidence["originalCliPresent"] = real_cli.is_file()
        evidence.update(renderer_markers(archive))
        try:
            processes = running_executables()
            evidence["appRunning"] = any(path.is_relative_to(bundle / "Contents") for path in processes)
            evidence["routerRunning"] = wrapper.resolve() in processes
        except (OSError, subprocess.SubprocessError):
            evidence["appRunning"] = evidence["routerRunning"] = None
        if before != [file_stamp(path) for path in observed_paths] or report_stamp != file_stamp(report_path):
            return _result("inconclusive", "The app changed during inspection; check again after the update finishes.", evidence)

        wrapper_present = evidence["routerWrapperPresent"]
        renderer_removed = evidence["accountMenu"] is False and evidence["taskSelector"] is False
        # Require independent evidence of removal, rather than treating process
        # absence, startup delay, quota, or network failures as patch breakage.
        if not wrapper_present and (renderer_removed or not evidence["originalCliPresent"]):
            reason = "The app updated and the router components were removed." if evidence["buildChanged"] else "The installed app no longer contains the router components."
            return _result("repair-needed", reason, evidence)
        if wrapper_present and not evidence["originalCliPresent"]:
            return _result("repair-needed", "The router wrapper is present but its required bundled CLI is missing.", evidence)
        complete = wrapper_present and evidence["originalCliPresent"] and evidence["accountMenu"] and evidence["taskSelector"]
        if not complete:
            return _result("inconclusive", "Only part of the router patch could be confirmed; inspect before repairing.", evidence)
        if evidence["appRunning"] is False:
            return _result("not-running", "The router patch is intact and the app is closed.", evidence)
        if evidence["routerRunning"] is True:
            return _result("healthy", "Router components are present and the router process is running.", evidence)
        return _result("inconclusive", "Router components are intact, but its process was not observed; the app may still be starting.", evidence)
    except (OSError, ValueError, TypeError, KeyError, RecursionError, plistlib.InvalidFileException, struct.error):
        # Do not emit exception bodies: bundle contents can contain embedded
        # local control tokens, even though no credential files are read.
        return _result("inconclusive", "The installed artifacts could not be read reliably; no breakage is confirmed.", evidence)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state", type=Path, default=DEFAULT_STATE)
    parser.add_argument("--app", type=Path, help="Inspect this app instead of the recorded installation path")
    args = parser.parse_args(argv)
    print(json.dumps(check_health(args.state, args.app), separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
