"""Activate verified app bundles without stopping processes or changing account data.

Both public functions return the newly committed updates/manifest.json document.
Activation reports require ``sourceBuild`` and an absolute ``codexHome``; ``sqlitePath`` optionally
overrides its state_5.sqlite index. Rollback compares the index schema recorded
before activation and refuses unknown or changed schemas. It never restores a
database snapshot, credentials, configuration, or routing metadata.
"""
from __future__ import annotations

from contextlib import closing, contextmanager
from copy import deepcopy
import ctypes
import fcntl
import hashlib
import json
import os
from pathlib import Path
import plistlib
import sqlite3
import subprocess
import sys
import tempfile
import time
from typing import Callable
import uuid


def running_executables() -> list[tuple[int, Path]]:
    """Read executable names only: process arguments may contain private data."""
    result = subprocess.run(["ps", "-axo", "pid=,comm=", "-ww"], check=True,
                            capture_output=True, text=True)
    processes = []
    for line in result.stdout.splitlines():
        parts = line.strip().split(None, 1)
        if len(parts) == 2 and parts[0].isdigit() and parts[1].startswith("/"):
            processes.append((int(parts[0]), Path(parts[1]).resolve()))
    return processes


def ensure_bundles_stopped(*bundles: Path) -> None:
    roots = [(bundle / "Contents").resolve() for bundle in bundles]
    for pid, executable in running_executables():
        for root in roots:
            if executable.is_relative_to(root):
                raise RuntimeError(f"App is running (PID {pid}); quit it before activating or rolling back an update")


def verify_bundle(bundle: Path, report: dict | None = None) -> None:
    if not bundle.is_dir() or not (bundle / "Contents/Info.plist").is_file():
        raise RuntimeError("Candidate is not a complete app bundle")
    try:
        info = plistlib.loads((bundle / "Contents/Info.plist").read_bytes())
    except (OSError, plistlib.InvalidFileException) as error:
        raise RuntimeError("Candidate has an invalid app Info.plist") from error
    if info.get("CFBundleIdentifier") != "app.cdxmux.multi":
        raise RuntimeError("Candidate is not a Codex Subscription Router bundle")
    if report is not None and (not report.get("sourceBuild") or
                              str(info.get("CFBundleVersion")) != str(report["sourceBuild"])):
        raise RuntimeError("Candidate build does not match its verified build report")
    subprocess.run(["codesign", "--verify", "--deep", "--strict", str(bundle)],
                   check=True, capture_output=True, text=True)


def _bundle_path(path: Path) -> Path:
    path = path.expanduser().absolute()
    if path.is_symlink():
        raise RuntimeError("Activation requires a real bundle path, not a symlink")
    return path.resolve()


def _separate(left: Path, right: Path) -> None:
    if left == right or left.is_relative_to(right) or right.is_relative_to(left):
        raise RuntimeError("Candidate and destination must be separate, nonnested bundles")


def _report(value: dict) -> dict:
    report = deepcopy(value)
    home = report.get("codexHome")
    if not isinstance(home, str) or not Path(home).is_absolute():
        raise RuntimeError("Build report requires an absolute codexHome for safe rollback")
    if report.get("sqlitePath") is not None and not Path(report["sqlitePath"]).is_absolute():
        raise RuntimeError("Build report sqlitePath must be absolute")
    if not report.get("sourceBuild"):
        raise RuntimeError("Build report requires sourceBuild to identify the verified app")
    # Validate before moving bundles; reports must be JSON metadata, not objects.
    json.dumps(report)
    return report


def sqlite_fingerprint(report: dict) -> dict:
    home = report.get("codexHome")
    if not isinstance(home, str) or not Path(home).is_absolute():
        raise RuntimeError("Database path is unknown; cannot safely roll back this app")
    path = Path(report.get("sqlitePath", str(Path(home) / "state_5.sqlite"))).resolve()
    if not path.exists():
        return {"path": str(path), "exists": False}
    if not path.is_file():
        raise RuntimeError("Database path is not a file; cannot verify rollback compatibility")
    try:
        with closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)) as connection:
            connection.execute("BEGIN")
            user_version = connection.execute("PRAGMA user_version").fetchone()[0]
            schema_version = connection.execute("PRAGMA schema_version").fetchone()[0]
            schema = connection.execute("SELECT type, name, tbl_name, sql FROM sqlite_master ORDER BY type, name, tbl_name, sql").fetchall()
    except sqlite3.Error as error:
        raise RuntimeError("Cannot read database schema; refusing an unverified rollback") from error
    digest = hashlib.sha256(json.dumps(schema, separators=(",", ":")).encode()).hexdigest()
    return {"path": str(path), "exists": True, "userVersion": user_version,
            "schemaVersion": schema_version, "schemaSha256": digest}


@contextmanager
def _locked(state: Path):
    updates = state / "updates"
    updates.mkdir(mode=0o700, parents=True, exist_ok=True)
    with (updates / "activation.lock").open("a") as lock:
        os.chmod(lock.name, 0o600)
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise RuntimeError("Another update activation is in progress") from error
        try:
            yield updates
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


def _read_json(path: Path) -> dict | None:
    if not path.exists():
        return None
    data = json.loads(path.read_text())
    if not isinstance(data, dict):
        raise RuntimeError(f"Invalid update metadata: {path.name}")
    return data


def _write_manifest(path: Path, manifest: dict) -> None:
    fd, temporary = tempfile.mkstemp(prefix=".manifest-", dir=path.parent)
    temporary_path = Path(temporary)
    try:
        with os.fdopen(fd, "w") as stream:
            json.dump(manifest, stream, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_path, path)
    finally:
        temporary_path.unlink(missing_ok=True)


def _backup_path(updates: Path, destination: Path) -> Path:
    directory = updates / "backups" / (time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:12])
    directory.mkdir(mode=0o700, parents=True)
    return directory / destination.name


def exchange_bundles(left: Path, right: Path) -> None:
    """Atomically swap whole bundles; never emulate this with live renames.

    macOS SDK sys/stdio.h declares renamex_np and RENAME_SWAP = 0x00000002.
    Tests replace this seam; production fails closed on unsupported platforms.
    """
    if sys.platform != "darwin":
        raise RuntimeError("Atomic app replacement requires macOS renamex_np")
    library = ctypes.CDLL(None, use_errno=True)
    try:
        renamex = library.renamex_np
    except AttributeError as error:
        raise RuntimeError("Atomic app replacement is unavailable on this system") from error
    renamex.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_uint]
    renamex.restype = ctypes.c_int
    if renamex(os.fsencode(left), os.fsencode(right), 0x00000002) != 0:
        number = ctypes.get_errno()
        raise OSError(number, os.strerror(number))


def _switch(candidate: Path, destination: Path, backup: Path | None,
            manifest_path: Path, manifest: dict, compatibility_check: Callable[[], None] | None = None) -> None:
    """Recover ordinary rename/manifest failures; do not delete either bundle."""
    exchanged = moved_old = moved_new = False
    build_path = manifest_path.parent.parent / "build.json"
    old_build = build_path.read_bytes() if build_path.exists() else None
    build_written = False
    journal_path = manifest_path.parent / "transaction.json"
    if journal_path.exists():
        raise RuntimeError("An interrupted activation needs review; both app bundles are preserved. Inspect updates/transaction.json before another update")
    volumes = [candidate.stat().st_dev, destination.parent.stat().st_dev]
    if backup is not None:
        volumes.extend([destination.stat().st_dev, backup.parent.stat().st_dev])
    if len(set(volumes)) != 1:
        raise RuntimeError("Candidate, installed app, and backups must be on the same filesystem for atomic replacement")
    try:
        _write_manifest(journal_path, {"candidate": str(candidate), "destination": str(destination),
                        "backup": str(backup) if backup else None, "nextManifest": manifest})
        # Recheck after all staging/validation and immediately before renames.
        ensure_bundles_stopped(candidate, destination)
        if compatibility_check:
            compatibility_check()
        if backup is not None:
            exchange_bundles(candidate, destination)
            exchanged = True
            # The old bundle now lives at candidate, while destination is
            # always a complete app even if this process loses power here.
            os.rename(candidate, backup)
            moved_old = True
        else:
            os.rename(candidate, destination)
            moved_new = True
        _write_manifest(build_path, manifest["active"]["report"])
        build_written = True
        _write_manifest(manifest_path, manifest)
    except BaseException:
        if exchanged:
            if moved_old:
                os.rename(backup, candidate)
            exchange_bundles(candidate, destination)
        elif moved_new:
            os.rename(destination, candidate)
        if build_written:
            if old_build is None:
                build_path.unlink(missing_ok=True)
            else:
                fd, name = tempfile.mkstemp(prefix=".build-restore-", dir=build_path.parent)
                try:
                    with os.fdopen(fd, "wb") as stream:
                        stream.write(old_build)
                        stream.flush()
                        os.fsync(stream.fileno())
                    os.replace(name, build_path)
                finally:
                    Path(name).unlink(missing_ok=True)
        journal_path.unlink(missing_ok=True)
        raise
    journal_path.unlink(missing_ok=True)


def activate_candidate(candidate: Path, destination: Path, state: Path, report: dict) -> dict:
    """Activate a separately built, signed candidate; never terminate an app."""
    candidate, destination = _bundle_path(candidate), _bundle_path(destination)
    state = state.expanduser().resolve()
    _separate(candidate, destination)
    for bundle in (candidate, destination):
        if state.is_relative_to(bundle):
            raise RuntimeError("Update state must be outside app bundles")
    report = _report(report)
    if destination.exists() and (not destination.is_dir() or not (destination / "Contents/Info.plist").is_file()):
        raise RuntimeError("Existing destination is not an app bundle")
    ensure_bundles_stopped(candidate, destination)
    verify_bundle(candidate, report)
    with _locked(state) as updates:
        manifest_path = updates / "manifest.json"
        previous_manifest = _read_json(manifest_path)
        if previous_manifest and previous_manifest.get("version") != 1:
            raise RuntimeError("Unsupported update manifest version")
        fingerprint = sqlite_fingerprint(report)
        previous = None
        backup = None
        if destination.exists():
            old_report = ((previous_manifest or {}).get("active") or {}).get("report") or _read_json(state / "build.json") or {}
            old_report = deepcopy(old_report)
            # Legacy builds recorded no codexHome. The update contract retains
            # the same shared primary home; record it explicitly for rollback.
            old_report.setdefault("codexHome", report["codexHome"])
            if "sqlitePath" in report:
                old_report.setdefault("sqlitePath", report["sqlitePath"])
            old_fingerprint = sqlite_fingerprint(old_report)
            if old_fingerprint["path"] != fingerprint["path"]:
                raise RuntimeError("Updates must preserve the shared database path")
            backup = _backup_path(updates, destination)
            previous = {"bundlePath": str(backup), "report": old_report, "sqlite": old_fingerprint}
        active_report = {**report, "app": str(destination)}
        manifest = {"version": 1, "active": {"bundlePath": str(destination), "report": active_report,
                    "sqlite": fingerprint}, "previous": previous, "activatedAt": time.time()}
        _switch(candidate, destination, backup, manifest_path, manifest)
        return manifest


def rollback_last(destination: Path, state: Path) -> dict:
    """Restore the previous signed bundle only when its database schema matches."""
    destination, state = _bundle_path(destination), state.expanduser().resolve()
    ensure_bundles_stopped(destination)
    with _locked(state) as updates:
        manifest_path = updates / "manifest.json"
        manifest = _read_json(manifest_path)
        if not manifest or manifest.get("version") != 1 or not manifest.get("previous"):
            raise RuntimeError("No previous router build is recorded for rollback")
        active, previous = manifest["active"], manifest["previous"]
        if Path(active["bundlePath"]).resolve() != destination:
            raise RuntimeError("Recorded active bundle does not match the requested destination")
        candidate = _bundle_path(Path(previous["bundlePath"]))
        _separate(candidate, destination)
        if not candidate.is_relative_to(updates / "backups"):
            raise RuntimeError("Previous bundle is outside the managed backup directory")
        ensure_bundles_stopped(candidate, destination)
        verify_bundle(candidate, previous.get("report", {}))
        def verify_schema():
            expected = previous.get("sqlite")
            if not expected or sqlite_fingerprint(previous.get("report", {})) != expected:
                raise RuntimeError("Database schema changed or is unknown; refusing unsafe binary rollback. Keep the current app and review database compatibility")
        verify_schema()
        backup = _backup_path(updates, destination) if destination.exists() else None
        updated = {"version": 1, "active": {**previous, "bundlePath": str(destination),
                   "report": {**previous["report"], "app": str(destination)}},
                   "previous": {**active, "bundlePath": str(backup)} if backup else None,
                   "activatedAt": time.time(), "operation": "rollback"}
        _switch(candidate, destination, backup, manifest_path, updated, verify_schema)
        return updated
