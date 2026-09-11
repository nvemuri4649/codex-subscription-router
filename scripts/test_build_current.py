"""Portable tests for metadata migration and Electron ASAR integrity."""

import copy
import hashlib
import json
from pathlib import Path
import stat
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_current import asar_header_hash, seed_state


class SeedStateTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.state = self.root / "new router"
        (self.state / "router").mkdir(parents=True)
        self.path = self.state / "router/state.json"
        self.source_home = self.root / "original account home"
        self.import_path = self.root / "previous-state.json"
        self.previous = {
            "version": 1,
            "accounts": [
                {"id": "primary", "label": "Original work", "codexHome": str(self.source_home),
                 "enabled": True, "controller": True, "createdAt": 11},
                {"id": "personal", "label": "Personal", "codexHome": str(self.root / "personal home"),
                 "enabled": True, "controller": False, "createdAt": 22},
                {"id": "dormant", "label": "Disconnected", "codexHome": str(self.root / "dormant home"),
                 "enabled": False, "controller": False, "createdAt": 33},
            ],
            "threadOwner": {"work-task": "primary", "personal-task": "personal", "archived-task": "dormant"},
            "routing": {"defaultMode": "casual", "roleAccounts": {"personal": "personal", "work": "primary"}},
            "threadModes": {"work-task": "intensive"},
            "projectModes": {"/project": "casual"},
        }
        self.import_path.write_text(json.dumps(self.previous))

    def read_state(self):
        return json.loads(self.path.read_text())

    def test_import_keeps_all_accounts_homes_and_owners_but_drops_modes(self):
        original_bytes = self.import_path.read_bytes()
        seed_state(self.state, self.source_home, self.import_path)
        actual = self.read_state()
        self.assertEqual(actual, {key: self.previous[key] for key in ("version", "accounts", "threadOwner")})
        self.assertEqual(self.import_path.read_bytes(), original_bytes)
        # Credential homes need not exist on the build host; importing metadata
        # neither creates those homes nor reads or copies their credentials.
        for account in actual["accounts"]:
            self.assertFalse(Path(account["codexHome"]).exists())
        self.assertEqual(stat.S_IMODE(self.path.stat().st_mode), 0o600)

    def test_selecting_personal_controller_keeps_history_and_home_references(self):
        seed_state(self.state, self.source_home, self.import_path, "personal")
        actual = self.read_state()
        expected = copy.deepcopy(self.previous["accounts"])
        for account in expected:
            account["controller"] = account["id"] == "personal"
        self.assertEqual(actual["accounts"], expected)
        self.assertEqual(actual["threadOwner"], self.previous["threadOwner"])
        self.assertEqual(json.loads(self.import_path.read_text()), self.previous)

    def test_first_run_without_import_creates_one_controller_at_source_home(self):
        with patch("build_current.time.time", return_value=1700000000):
            seed_state(self.state, self.source_home)
        self.assertEqual(self.read_state(), {
            "version": 1,
            "accounts": [{"id": "primary", "label": "Primary", "codexHome": str(self.source_home),
                          "enabled": True, "controller": True, "createdAt": 1700000000}],
            "threadOwner": {},
        })

    def test_import_refuses_missing_or_disabled_requested_controller(self):
        for requested in ("missing", "dormant"):
            with self.subTest(controller=requested):
                with self.assertRaisesRegex(RuntimeError, "must exist and be enabled"):
                    seed_state(self.state, self.source_home, self.import_path, requested)
                self.assertFalse(self.path.exists())
                self.assertEqual(json.loads(self.import_path.read_text()), self.previous)

    def test_unsupported_import_does_not_create_state(self):
        for invalid in ({"version": 2, "accounts": self.previous["accounts"]}, {"version": 1, "accounts": []}):
            with self.subTest(metadata=invalid):
                self.import_path.write_text(json.dumps(invalid))
                with self.assertRaisesRegex(RuntimeError, "Unsupported account metadata"):
                    seed_state(self.state, self.source_home, self.import_path)
                self.assertFalse(self.path.exists())

    def test_rebuild_preserves_existing_state_exactly_and_ignores_new_import(self):
        existing = json.dumps(self.previous, separators=(",", ":")) + "\n"
        self.path.write_text(existing)
        for requested in (None, "primary"):
            with self.subTest(controller=requested):
                seed_state(self.state, self.root / "different home", self.root / "missing import", requested)
                self.assertEqual(self.path.read_text(), existing)

    def test_rebuild_refuses_controller_change_without_mutating_existing_state(self):
        existing = json.dumps(self.previous)
        self.path.write_text(existing)
        for requested in ("personal", "missing", "dormant"):
            with self.subTest(controller=requested):
                with self.assertRaises(RuntimeError):
                    seed_state(self.state, self.source_home, self.import_path, requested)
                self.assertEqual(self.path.read_text(), existing)

    def test_rebuild_refuses_explicit_disabled_controller_and_preserves_state(self):
        self.previous["accounts"][0]["enabled"] = False
        existing = json.dumps(self.previous)
        self.path.write_text(existing)
        with self.assertRaises(RuntimeError):
            seed_state(self.state, self.source_home, self.import_path, "primary")
        self.assertEqual(self.path.read_text(), existing)


class AsarHeaderHashTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)

    def archive(self, name, header, payload):
        # ASAR starts with the size pickle, then a pickle containing the JSON
        # byte length, the JSON itself, and alignment padding before file data.
        encoded = json.dumps(header, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        padding = b"\0" * (-len(encoded) % 4)
        header_pickle = struct.pack("<II", 4 + len(encoded) + len(padding), len(encoded)) + encoded + padding
        archive = self.root / name
        archive.write_bytes(struct.pack("<II", 4, len(header_pickle)) + header_pickle + payload)
        return archive, encoded

    def test_hash_is_json_header_bytes_without_pickle_padding_or_file_data(self):
        path, encoded = self.archive("sample.asar", {"files": {"café.txt": {"size": 7, "offset": "0"}}}, b"content")
        self.assertEqual(asar_header_hash(path), hashlib.sha256(encoded).hexdigest())
        self.assertNotEqual(asar_header_hash(path), hashlib.sha256(path.read_bytes()).hexdigest())

    def test_file_data_changes_do_not_change_header_hash(self):
        header = {"files": {"one": {"size": 3, "offset": "0"}}}
        first, _ = self.archive("first.asar", header, b"one")
        second, _ = self.archive("second.asar", header, b"two")
        self.assertEqual(asar_header_hash(first), asar_header_hash(second))

    def test_header_changes_change_hash_even_with_identical_file_data(self):
        first, _ = self.archive("first.asar", {"files": {"one": {"size": 3, "offset": "0"}}}, b"one")
        second, _ = self.archive("second.asar", {"files": {"two": {"size": 3, "offset": "0"}}}, b"one")
        self.assertNotEqual(asar_header_hash(first), asar_header_hash(second))


if __name__ == "__main__":
    unittest.main()
