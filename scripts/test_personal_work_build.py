import hashlib
from pathlib import Path
import struct
import tempfile
import unittest

from build_personal_work import asar_header_hash, replace_once, seed_state


class BuildTests(unittest.TestCase):
    def test_only_unique_reviewed_anchor_is_replaced(self):
        self.assertEqual(replace_once('a OLD b', 'OLD', 'NEW', 'example'), 'a NEW b')
        for value in ('unrelated', 'OLD OLD'):
            with self.assertRaises(RuntimeError):
                replace_once(value, 'OLD', 'NEW', 'example')

    def test_integrity_uses_json_header_not_whole_archive(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'app.asar'
            header = b'{"files":{}}'
            path.write_bytes(struct.pack('<4I',4,16+len(header),len(header)+4,len(header)) + header + b'file contents')
            self.assertEqual(asar_header_hash(path),hashlib.sha256(header).hexdigest())
            self.assertNotEqual(asar_header_hash(path),hashlib.sha256(path.read_bytes()).hexdigest())

    def test_existing_work_home_referenced_without_copying_tokens(self):
        import json
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp); state=root/'state'; (state/'router').mkdir(parents=True)
            home=root/'existing';home.mkdir();auth=home/'auth.json';auth.write_text('private fixture')
            seed_state(state,home)
            data=json.loads((state/'router/state.json').read_text())
            self.assertEqual(data['routing']['roleAccounts'],{'personal':'','work':'primary'})
            self.assertEqual(data['accounts'][0]['codexHome'],str(home))
            self.assertEqual(list(state.rglob('auth.json')),[])
            self.assertEqual(auth.read_text(),'private fixture')
            data['routing']['defaultMode']='intensive'
            (state/'router/state.json').write_text(json.dumps(data))
            seed_state(state,home)
            self.assertEqual(json.loads((state/'router/state.json').read_text())['routing']['defaultMode'],'intensive')

if __name__ == '__main__':
    unittest.main()
