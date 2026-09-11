"""Artifact-only health checks use tiny ASAR fixtures and mocked process lists."""
import contextlib
import io
import json
from pathlib import Path
import plistlib
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import check_router_health as health


class HealthTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.state = self.root / "state"
        self.state.mkdir()
        self.bundle = self.root / "Router.app"
        self.resources = self.bundle / "Contents/Resources"
        self.resources.mkdir(parents=True)
        self.wrapper = self.resources / "codex"
        self.wrapper.write_bytes(b"binary " + health.GO_BUILD_MAGIC + b" data " + health.GO_ROUTER_PATH)
        (self.resources / "codex.real").write_bytes(b"official CLI fixture")
        self.set_info("8576")
        self.write_archive()
        (self.state / "build.json").write_text(json.dumps({"app": str(self.bundle), "sourceBuild": "8576", "routerVersion": "0.2.1"}))
        self.processes = self.enterContext(patch.object(health, "running_executables", return_value=[self.wrapper]))

    def set_info(self, version, identifier="app.cdxmux.multi"):
        (self.bundle / "Contents/Info.plist").write_bytes(plistlib.dumps({"CFBundleVersion": version, "CFBundleIdentifier": identifier}))

    def write_archive(self, menu=True, task=True, unfamiliar_layout=False):
        payload = bytearray()
        files = {}
        names = ["app-primary-fixture.js", "local-conversation-thread-fixture.js"]
        if unfamiliar_layout:
            names = ["renamed-ui.js", "renamed-task.js"]
        markers = [b"function CodexMuxAccountMenu() {}", b"function CodexMuxThreadSubscription() {}"]
        for name, enabled, marker in zip(names, (menu, task), markers):
            data = marker if enabled else b"function officialComponent() {}"
            # Bundle source may contain local control tokens; never emit them.
            data += b' const token = "PRIVATE_FIXTURE_SENTINEL";'
            files[name] = {"size": len(data), "offset": str(len(payload))}
            payload.extend(data)
        table = {"files": {"webview": {"files": {"assets": {"files": files}}}}}
        encoded = json.dumps(table, separators=(",", ":")).encode()
        padding = b"\0" * (-len(encoded) % 4)
        header_pickle = struct.pack("<II", 4 + len(encoded) + len(padding), len(encoded)) + encoded + padding
        (self.resources / "app.asar").write_bytes(struct.pack("<II", 4, len(header_pickle)) + header_pickle + payload)

    def check(self):
        result = health.check_health(self.state)
        self.assertNotIn("PRIVATE_FIXTURE_SENTINEL", json.dumps(result))
        return result

    def test_intact_running_router_is_healthy(self):
        result = self.check()
        self.assertEqual(result["status"], "healthy")
        self.assertTrue(result["evidence"]["routerWrapperPresent"])
        self.assertTrue(result["evidence"]["accountMenu"])
        self.assertTrue(result["evidence"]["taskSelector"])

    def test_closed_intact_app_is_not_running_not_broken(self):
        self.processes.return_value = []
        self.assertEqual(self.check()["status"], "not-running")

    def test_no_router_process_during_app_startup_is_inconclusive(self):
        self.processes.return_value = [self.bundle / "Contents/MacOS/Runtime"]
        self.assertEqual(self.check()["status"], "inconclusive")

    def test_similar_other_app_path_does_not_count_as_running(self):
        self.processes.return_value = [self.root / "Router.app-other/Contents/Resources/codex"]
        self.assertEqual(self.check()["status"], "not-running")

    def test_confirmed_official_update_removed_router_needs_repair(self):
        self.set_info("9000", "com.openai.codex")
        self.wrapper.write_bytes(b"official Rust executable")
        (self.resources / "codex.real").unlink()
        self.write_archive(menu=False, task=False)
        result = self.check()
        self.assertEqual(result["status"], "repair-needed")
        self.assertTrue(result["evidence"]["buildChanged"])
        self.assertIn("updated", result["reason"])

    def test_retained_stale_real_cli_does_not_hide_removed_router(self):
        self.set_info("9000")
        self.wrapper.write_bytes(b"official Rust executable")
        self.write_archive(menu=False, task=False)
        self.assertEqual(self.check()["status"], "repair-needed")

    def test_same_version_patch_removal_is_detected_without_inventing_update(self):
        self.wrapper.write_bytes(b"official Rust executable")
        self.write_archive(menu=False, task=False)
        result = self.check()
        self.assertEqual(result["status"], "repair-needed")
        self.assertFalse(result["evidence"]["buildChanged"])
        self.assertNotIn("updated", result["reason"])

    def test_closed_app_with_confirmed_removed_patch_still_reports_evidence(self):
        self.processes.return_value = []
        self.wrapper.write_bytes(b"official executable")
        self.write_archive(menu=False, task=False)
        result = self.check()
        self.assertEqual(result["status"], "repair-needed")
        self.assertFalse(result["evidence"]["appRunning"])

    def test_changed_version_with_router_intact_is_not_breakage(self):
        self.set_info("9000")
        self.assertEqual(self.check()["status"], "healthy")

    def test_partial_renderer_evidence_is_inconclusive(self):
        self.write_archive(menu=True, task=False)
        self.assertEqual(self.check()["status"], "inconclusive")

    def test_future_renderer_layout_alone_is_inconclusive(self):
        self.write_archive(unfamiliar_layout=True)
        result = self.check()
        self.assertEqual(result["status"], "inconclusive")
        self.assertIsNone(result["evidence"]["accountMenu"])

    def test_wrapper_without_required_real_cli_is_confirmed_breakage(self):
        (self.resources / "codex.real").unlink()
        self.assertEqual(self.check()["status"], "repair-needed")

    def test_app_change_during_scan_is_inconclusive(self):
        def mutate():
            self.set_info("9000")
            return [self.wrapper]
        self.processes.side_effect = mutate
        self.assertEqual(self.check()["status"], "inconclusive")

    def test_corrupt_archive_is_inconclusive_and_never_emits_contents(self):
        (self.resources / "app.asar").write_bytes(b"PRIVATE_FIXTURE_SENTINEL")
        self.assertEqual(self.check()["status"], "inconclusive")

    def test_bad_asar_entry_bounds_are_not_read(self):
        archive = self.resources / "app.asar"
        blob = archive.read_bytes().replace(b'"offset":"0"', b'"offset":"-1"')
        archive.write_bytes(blob)
        self.assertEqual(self.check()["status"], "inconclusive")

    def test_unknown_bundle_identity_is_inconclusive(self):
        self.set_info("9000", "other.application")
        self.assertEqual(self.check()["status"], "inconclusive")

    def test_missing_or_moved_installation_is_not_assumed_broken(self):
        self.bundle.rename(self.root / "Moved.app")
        self.assertEqual(self.check()["status"], "inconclusive")

    def test_missing_report_is_inconclusive(self):
        (self.state / "build.json").unlink()
        self.assertEqual(self.check()["status"], "inconclusive")

    def test_unrecognized_report_shape_is_inconclusive(self):
        (self.state / "build.json").write_text("[]")
        self.assertEqual(self.check()["status"], "inconclusive")

    def test_process_inspection_failure_is_not_breakage(self):
        self.processes.side_effect = subprocess.CalledProcessError(1, ["ps"])
        self.assertEqual(self.check()["status"], "inconclusive")

    def test_check_does_not_read_credentials_or_write_any_files(self):
        for name in ("auth.json", "control-token", "state.json", "config.toml"):
            (self.state / name).write_text("PRIVATE_FIXTURE_SENTINEL")
        before = {path: path.read_bytes() for path in self.root.rglob("*") if path.is_file()}
        original_open = Path.open
        def open_path(path, mode="r", *args, **kwargs):
            self.assertNotIn(path.name, ("auth.json", "control-token", "state.json", "config.toml"))
            self.assertNotIn("w", mode)
            self.assertNotIn("a", mode)
            self.assertNotIn("+", mode)
            return original_open(path, mode, *args, **kwargs)
        with patch.object(Path, "open", open_path), patch("socket.socket", side_effect=AssertionError("no network allowed")):
            self.assertEqual(self.check()["status"], "healthy")
        after = {path: path.read_bytes() for path in self.root.rglob("*") if path.is_file()}
        self.assertEqual(after, before)

    def test_cli_emits_one_short_json_result(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(health.main(["--state", str(self.state)]), 0)
        result = json.loads(output.getvalue())
        self.assertEqual(result["status"], "healthy")
        self.assertNotIn("PRIVATE_FIXTURE_SENTINEL", output.getvalue())


class BuildInfoTests(unittest.TestCase):
    def test_go_build_info_markers_cross_chunk_boundary(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "codex"
            path.write_bytes(b"x" * (1024 * 1024 - 3) + health.GO_BUILD_MAGIC + health.GO_ROUTER_PATH)
            self.assertTrue(health.has_router_build_info(path))

    def test_go_binary_for_another_program_is_not_the_router(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "codex"
            path.write_bytes(health.GO_BUILD_MAGIC + b"path\tother/module\n")
            self.assertFalse(health.has_router_build_info(path))


if __name__ == "__main__":
    unittest.main()
