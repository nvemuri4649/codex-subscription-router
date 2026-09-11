"""Portable transaction tests: real files/SQLite, mocked macOS process/signing APIs."""
from contextlib import closing
import errno
import os
import json
from pathlib import Path
import plistlib
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import update_lifecycle as lifecycle


class LifecycleTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.state = self.root / "state"
        self.state.mkdir()
        self.destination = self.root / "Router.app"
        self.candidate = self.root / "Candidate.app"
        self.home = self.root / "codex-home"
        self.home.mkdir()
        self.database = self.home / "state_5.sqlite"
        with closing(sqlite3.connect(self.database)) as connection, connection:
            connection.execute("CREATE TABLE threads (id TEXT PRIMARY KEY)")
            connection.execute("PRAGMA user_version = 7")
        self.bundle(self.destination, "old")
        self.bundle(self.candidate, "new")
        self.old_report = {"sourceBuild": "old", "codexHome": str(self.home), "app": str(self.destination)}
        self.report = {"sourceBuild": "new", "codexHome": str(self.home), "app": str(self.candidate)}
        (self.state / "build.json").write_text(json.dumps(self.old_report) + "\n")
        (self.state / "router").mkdir()
        self.protected = [self.state / "router/state.json", self.home / "auth.json", self.home / "config.toml"]
        for path in self.protected:
            path.write_text("unchanged test fixture\n")
        self.before = {path: path.read_bytes() for path in self.protected}
        self.processes = self.enterContext(patch.object(lifecycle, "running_executables", return_value=[]))
        self.signature = self.enterContext(patch.object(lifecycle, "verify_bundle"))
        self.exchange = self.enterContext(patch.object(lifecycle, "exchange_bundles", side_effect=self.emulate_exchange))

    def bundle(self, path, label):
        (path / "Contents").mkdir(parents=True)
        (path / "Contents/Info.plist").write_bytes(plistlib.dumps({"CFBundleIdentifier": "app.cdxmux.multi", "CFBundleVersion": label}))
        (path / "label").write_text(label)

    def emulate_exchange(self, left, right):
        # A portable test seam only. Production MUST use native atomic exchange.
        temporary = left.with_name("exchange-temporary")
        left.rename(temporary)
        right.rename(left)
        temporary.rename(right)

    def activate(self):
        return lifecycle.activate_candidate(self.candidate, self.destination, self.state, self.report)

    def label(self, path):
        return (path / "label").read_text()

    def assert_protected(self):
        for path, contents in self.before.items():
            self.assertEqual(path.read_bytes(), contents)

    def assert_not_activated(self):
        self.assertEqual(self.label(self.destination), "old")
        self.assertEqual(self.label(self.candidate), "new")
        self.assertEqual(json.loads((self.state / "build.json").read_text()), self.old_report)
        self.assertFalse((self.state / "updates/manifest.json").exists())
        self.assert_protected()

    def test_activation_preserves_old_bundle_and_accounts(self):
        result = self.activate()
        self.assertEqual(self.label(self.destination), "new")
        self.assertFalse(self.candidate.exists())
        self.assertEqual(self.label(Path(result["previous"]["bundlePath"])), "old")
        self.assertEqual(result["previous"]["report"], self.old_report)
        self.assertEqual(result["active"]["report"]["app"], str(self.destination))
        self.assertEqual(result["active"]["sqlite"]["userVersion"], 7)
        self.assertEqual(json.loads((self.state / "updates/manifest.json").read_text()), result)
        self.assertEqual(json.loads((self.state / "build.json").read_text()), result["active"]["report"])
        self.assertFalse((self.state / "updates/transaction.json").exists())
        self.assert_protected()

    def test_first_install_uses_rename_without_exchange(self):
        destination = self.root / "First.app"
        result = lifecycle.activate_candidate(self.candidate, destination, self.state, self.report)
        self.exchange.assert_not_called()
        self.assertIsNone(result["previous"])
        self.assertEqual(self.label(destination), "new")

    def test_running_app_is_not_stopped_or_moved(self):
        self.processes.return_value = [(123, self.destination / "Contents/MacOS/Runtime")]
        with self.assertRaisesRegex(RuntimeError, "running"):
            self.activate()
        self.exchange.assert_not_called()
        self.assert_not_activated()

    def test_running_candidate_is_rejected(self):
        self.processes.return_value = [(456, self.candidate / "Contents/Resources/codex")]
        with self.assertRaisesRegex(RuntimeError, "running"):
            self.activate()
        self.assert_not_activated()

    def test_similar_path_is_not_a_running_app_match(self):
        self.processes.return_value = [(123, self.root / "Router.app-other/Contents/Runtime")]
        self.activate()
        self.assertEqual(self.label(self.destination), "new")

    def test_app_starting_during_validation_prevents_activation(self):
        self.processes.side_effect = [[], [(321, self.destination / "Contents/MacOS/Runtime")]]
        with self.assertRaisesRegex(RuntimeError, "running"):
            self.activate()
        self.exchange.assert_not_called()
        self.assert_not_activated()

    def test_failed_signature_never_moves_bundles(self):
        self.signature.side_effect = subprocess.CalledProcessError(1, ["codesign"])
        with self.assertRaises(subprocess.CalledProcessError):
            self.activate()
        self.assert_not_activated()

    def test_failed_native_exchange_does_not_fall_back_to_unsafe_renames(self):
        self.exchange.side_effect = OSError(errno.ENOTSUP, "unsupported")
        with self.assertRaises(OSError):
            self.activate()
        self.assertEqual(self.exchange.call_count, 1)
        self.assert_not_activated()

    def test_cross_filesystem_candidate_is_rejected_before_exchange(self):
        original_stat = Path.stat
        def stat(path, **kwargs):
            result = original_stat(path, **kwargs)
            if path == self.candidate:
                values = list(result)
                values[2] += 1
                return os.stat_result(values)
            return result
        with patch.object(Path, "stat", stat):
            with self.assertRaisesRegex(RuntimeError, "same filesystem"):
                self.activate()
        self.exchange.assert_not_called()
        self.assert_not_activated()

    def test_failed_backup_move_reverses_atomic_exchange(self):
        original_rename = lifecycle.os.rename
        def rename(source, target):
            if Path(source) == self.candidate and "backups" in Path(target).parts:
                raise OSError(errno.ENOSPC, "disk full")
            return original_rename(source, target)
        with patch.object(lifecycle.os, "rename", side_effect=rename):
            with self.assertRaises(OSError):
                self.activate()
        self.assertEqual(self.exchange.call_count, 2)
        self.assert_not_activated()

    def test_manifest_failure_restores_app_candidate_and_exact_old_build_report(self):
        original_bytes = (self.state / "build.json").read_bytes()
        original_write = lifecycle._write_manifest
        def write(path, document):
            if path.name == "manifest.json":
                raise PermissionError("injected metadata failure")
            original_write(path, document)
        with patch.object(lifecycle, "_write_manifest", side_effect=write):
            with self.assertRaises(PermissionError):
                self.activate()
        self.assert_not_activated()
        self.assertEqual((self.state / "build.json").read_bytes(), original_bytes)
        self.assertFalse((self.state / "updates/transaction.json").exists())

    def test_first_install_metadata_failure_restores_candidate(self):
        destination = self.root / "First.app"
        original_write = lifecycle._write_manifest
        def write(path, document):
            if path.name == "manifest.json":
                raise PermissionError("injected failure")
            original_write(path, document)
        with patch.object(lifecycle, "_write_manifest", side_effect=write):
            with self.assertRaises(PermissionError):
                lifecycle.activate_candidate(self.candidate, destination, self.state, self.report)
        self.assertFalse(destination.exists())
        self.assertEqual(self.label(self.candidate), "new")

    def test_equal_nested_or_symlinked_bundles_are_rejected(self):
        for candidate in (self.destination, self.destination / "Nested.app", self.root):
            with self.subTest(candidate=candidate):
                with self.assertRaisesRegex(RuntimeError, "separate"):
                    lifecycle.activate_candidate(candidate, self.destination, self.state, self.report)
        linked = self.root / "Linked.app"
        linked.symlink_to(self.candidate, target_is_directory=True)
        with self.assertRaisesRegex(RuntimeError, "symlink"):
            lifecycle.activate_candidate(linked, self.destination, self.state, self.report)
        self.assert_not_activated()

    def test_absolute_codex_home_is_required(self):
        for report in ({}, {"codexHome": "relative"}):
            with self.assertRaisesRegex(RuntimeError, "absolute codexHome"):
                lifecycle.activate_candidate(self.candidate, self.destination, self.state, report)
        self.assert_not_activated()

    def test_legacy_report_records_shared_home_without_changing_legacy_metadata_early(self):
        (self.state / "build.json").write_text('{"sourceBuild":"old"}')
        result = self.activate()
        self.assertEqual(result["previous"]["report"]["codexHome"], str(self.home))

    def test_rollback_keeps_new_rows_and_both_app_versions(self):
        self.activate()
        with closing(sqlite3.connect(self.database)) as connection, connection:
            connection.execute("INSERT INTO threads VALUES ('task-created-after-update')")
        result = lifecycle.rollback_last(self.destination, self.state)
        self.assertEqual(self.label(self.destination), "old")
        self.assertEqual(self.label(Path(result["previous"]["bundlePath"])), "new")
        with closing(sqlite3.connect(self.database)) as connection, connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM threads").fetchone()[0], 1)
        self.assert_protected()

    def test_rollback_refuses_changed_schema_or_user_version(self):
        self.activate()
        with closing(sqlite3.connect(self.database)) as connection, connection:
            connection.execute("CREATE TABLE future_schema (id INTEGER)")
        manifest_bytes = (self.state / "updates/manifest.json").read_bytes()
        with self.assertRaisesRegex(RuntimeError, "schema changed"):
            lifecycle.rollback_last(self.destination, self.state)
        self.assertEqual(self.label(self.destination), "new")
        self.assertEqual((self.state / "updates/manifest.json").read_bytes(), manifest_bytes)
        self.assert_protected()

    def test_rollback_refuses_changed_user_version_without_table_changes(self):
        self.activate()
        with closing(sqlite3.connect(self.database)) as connection, connection:
            connection.execute("PRAGMA user_version = 8")
        with self.assertRaisesRegex(RuntimeError, "schema changed"):
            lifecycle.rollback_last(self.destination, self.state)
        self.assertEqual(self.label(self.destination), "new")

    def test_rollback_rechecks_schema_immediately_before_swap(self):
        self.activate()
        previous_calls = self.exchange.call_count
        def process_check():
            if self.processes.call_count == 5:
                with closing(sqlite3.connect(self.database)) as connection, connection:
                    connection.execute("PRAGMA user_version = 8")
            return []
        # Activation used two checks; rollback has an initial, full-pair,
        # and final check. Mutate only at the final check to exercise the race.
        self.processes.side_effect = process_check
        with self.assertRaisesRegex(RuntimeError, "schema changed"):
            lifecycle.rollback_last(self.destination, self.state)
        self.assertEqual(self.exchange.call_count, previous_calls)
        self.assertEqual(self.label(self.destination), "new")

    def test_rollback_refuses_unknown_database_fingerprint(self):
        self.activate()
        manifest_path = self.state / "updates/manifest.json"
        data = json.loads(manifest_path.read_text())
        del data["previous"]["sqlite"]
        manifest_path.write_text(json.dumps(data))
        with self.assertRaisesRegex(RuntimeError, "unknown"):
            lifecycle.rollback_last(self.destination, self.state)
        self.assertEqual(self.label(self.destination), "new")

    def test_running_app_blocks_rollback(self):
        self.activate()
        self.processes.return_value = [(123, self.destination / "Contents/Resources/codex")]
        with self.assertRaisesRegex(RuntimeError, "running"):
            lifecycle.rollback_last(self.destination, self.state)
        self.assertEqual(self.label(self.destination), "new")

    def test_interrupted_transaction_blocks_another_activation(self):
        updates = self.state / "updates"
        updates.mkdir()
        (updates / "transaction.json").write_text("{}")
        with self.assertRaisesRegex(RuntimeError, "interrupted"):
            self.activate()
        self.assert_not_activated()


class ProcessAndPlatformTests(unittest.TestCase):
    def test_ps_parses_full_executable_paths_with_spaces_without_arguments(self):
        result = subprocess.CompletedProcess([], 0, "123 /Applications/Router App.app/Contents/MacOS/Runtime\n456 relative-name\n")
        with patch.object(lifecycle.subprocess, "run", return_value=result) as run:
            actual = lifecycle.running_executables()
        self.assertEqual(actual, [(123, Path("/Applications/Router App.app/Contents/MacOS/Runtime"))])
        self.assertEqual(run.call_args.args[0], ["ps", "-axo", "pid=,comm=", "-ww"])

    def test_unsupported_platform_never_emulates_exchange(self):
        with patch.object(lifecycle.sys, "platform", "unsupported"):
            with self.assertRaisesRegex(RuntimeError, "requires macOS"):
                lifecycle.exchange_bundles(Path("left"), Path("right"))

    def test_signature_verification_uses_deep_strict_native_check(self):
        with tempfile.TemporaryDirectory() as temporary:
            bundle = Path(temporary) / "App.app"
            (bundle / "Contents").mkdir(parents=True)
            (bundle / "Contents/Info.plist").write_bytes(plistlib.dumps({"CFBundleIdentifier": "app.cdxmux.multi", "CFBundleVersion": "8576"}))
            with patch.object(lifecycle.subprocess, "run") as run:
                lifecycle.verify_bundle(bundle)
            self.assertEqual(run.call_args.args[0], ["codesign", "--verify", "--deep", "--strict", str(bundle)])

    def test_wrong_bundle_identity_or_report_build_is_rejected_before_codesign(self):
        with tempfile.TemporaryDirectory() as temporary:
            bundle = Path(temporary) / "App.app"
            (bundle / "Contents").mkdir(parents=True)
            for info, report in (({"CFBundleIdentifier": "com.openai.codex", "CFBundleVersion": "8576"}, None),
                                 ({"CFBundleIdentifier": "app.cdxmux.multi", "CFBundleVersion": "8576"}, {"sourceBuild": "8881"}),
                                 ({"CFBundleIdentifier": "app.cdxmux.multi", "CFBundleVersion": "8576"}, {})):
                with self.subTest(info=info, report=report):
                    (bundle / "Contents/Info.plist").write_bytes(plistlib.dumps(info))
                    with patch.object(lifecycle.subprocess, "run") as run:
                        with self.assertRaises(RuntimeError):
                            lifecycle.verify_bundle(bundle, report)
                    run.assert_not_called()

    @unittest.skipUnless(sys.platform == "darwin", "macOS native atomic exchange")
    def test_native_exchange_swaps_scratch_directories(self):
        with tempfile.TemporaryDirectory() as temporary:
            left, right = Path(temporary) / "left", Path(temporary) / "right"
            left.mkdir()
            right.mkdir()
            (left / "label").write_text("old")
            (right / "label").write_text("new")
            lifecycle.exchange_bundles(left, right)
            self.assertEqual((left / "label").read_text(), "new")
            self.assertEqual((right / "label").read_text(), "old")


if __name__ == "__main__":
    unittest.main()
