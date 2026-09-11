"""Unknown or failed updates must leave the working install and account state intact."""
import argparse
import json
from pathlib import Path
import plistlib
import tempfile
import unittest
from unittest.mock import patch

import build_current
import update_router


class UpdatePreparationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.state = self.root / 'state'
        self.app = self.root / 'Working.app'
        self.app.mkdir()
        (self.app / 'working').write_text('working release')
        (self.state / 'router').mkdir(parents=True)
        (self.state / 'router/state.json').write_text('{"accounts":["unchanged"],"threadOwner":{"saved":"work"}}')
        self.source = self.root / 'Official.app'
        (self.source / 'Contents/Resources').mkdir(parents=True)
        self.current = {'app': str(self.app), 'sourceBuild': '8576', 'codexHome': str(self.root / 'account')}
        (self.state / 'build.json').write_text(json.dumps(self.current))
        self.args = argparse.Namespace(state=self.state, destination=None, source=self.source, codex_home=self.root / 'account')
        self.before = {p: p.read_bytes() for p in (self.state / 'build.json', self.state / 'router/state.json', self.app / 'working')}

    def source_info(self, version, build):
        (self.source / 'Contents/Info.plist').write_bytes(plistlib.dumps({'CFBundleShortVersionString': version, 'CFBundleVersion': build}))
        (self.source / 'Contents/Resources/app.asar').write_bytes(b'unknown archive')

    def unchanged(self):
        for p, content in self.before.items():
            self.assertEqual(p.read_bytes(), content)
        self.assertFalse((self.state / 'updates/pending.json').exists())

    def test_unknown_future_build_refuses_before_build_or_state_write(self):
        self.source_info('99.0', '999999')
        with patch.object(build_current, 'build') as build:
            with self.assertRaisesRegex(RuntimeError, 'Unsupported official build'):
                update_router.prepare(self.args)
            build.assert_not_called()
        self.unchanged()

    def test_known_version_changed_archive_is_rejected(self):
        self.source_info(*build_current.VERSION)
        with patch.object(build_current, 'build') as build:
            with self.assertRaisesRegex(RuntimeError, 'unreviewed ASAR hash'):
                update_router.prepare(self.args)
            build.assert_not_called()
        self.unchanged()

    def test_failed_candidate_does_not_change_current_report_or_accounts(self):
        with patch.object(build_current, 'reviewed_source', return_value=({}, ('26.908.40834', '8881'), 'verified')):
            with patch.object(build_current, 'build', side_effect=RuntimeError('anchor drift')) as build:
                with self.assertRaisesRegex(RuntimeError, 'anchor drift'):
                    update_router.prepare(self.args)
                supplied = build.call_args.args[0]
                self.assertFalse(supplied.record_build)
                self.assertNotEqual(supplied.destination, self.app)
        self.unchanged()

    def test_older_official_app_cannot_silently_downgrade_new_router(self):
        self.current['sourceBuild'] = '8881'
        (self.state / 'build.json').write_text(json.dumps(self.current))
        self.before[self.state / 'build.json'] = (self.state / 'build.json').read_bytes()
        with patch.object(build_current, 'reviewed_source', return_value=({}, build_current.VERSION, 'verified')):
            with self.assertRaisesRegex(RuntimeError, 'older than'):
                update_router.prepare(self.args)
        self.unchanged()


if __name__ == '__main__':
    unittest.main()
