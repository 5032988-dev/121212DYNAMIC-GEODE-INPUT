"""Protect both original archives when building a worker repair bundle."""
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import package_worker_fix as packaging


class ArchivePreservationTests(unittest.TestCase):
    def test_rejects_original_paths_and_aliases_before_reading_or_writing(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            originals = [root / 'InputAlignExternal-windows.zip',
                         root / 'InputAlignExternal-v0.3-source.zip']
            for path in originals:
                path.write_bytes(b'original archive placeholder')
            with patch.object(packaging, 'ROOT', root):
                for path in originals:
                    alias = root / ('alias-' + path.name)
                    os.link(path, alias)
                    for destination in (path, alias):
                        with self.subTest(destination=destination.name):
                            with self.assertRaisesRegex(ValueError, 'overwrite'):
                                packaging.package(destination)
                            self.assertEqual(path.read_bytes(), b'original archive placeholder')

class TransactionalOutputTests(unittest.TestCase):
    def test_validation_and_replace_failures_preserve_previous_output(self):
        import io
        import json
        import zipfile
        replacements = ['worker/main.py', 'worker/predictor.py', 'worker/cpu_isolation.py',
                        'worker/cpu-isolation.json', 'worker/obstacles.py', 'worker/obstacle-sensor.json',
                        'GUIA-INSTALACION.md', 'README.md']
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in replacements:
                path = root / 'InputAlignExternal' / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b'replacement')
            inner = io.BytesIO()
            with zipfile.ZipFile(inner, 'w') as z:
                z.writestr('original', b'original')
                z.writestr('build-provenance.json', json.dumps({'sha256': {'original': packaging.sha(b'original')}}))
            with zipfile.ZipFile(root / 'InputAlignExternal-windows.zip', 'w') as z:
                z.writestr('InputAlignExternal-windows.zip', inner.getvalue())
            (root / 'InputAlignExternal-v0.3-source.zip').write_bytes(b'source')
            output = root / 'bundle.zip'
            output.write_bytes(b'previous bundle')
            with patch.object(packaging, 'ROOT', root):
                with patch.object(zipfile.ZipFile, 'testzip', side_effect=[None, None, 'corrupt']):
                    with self.assertRaisesRegex(ValueError, 'output ZIP CRC'):
                        packaging.package(output)
                self.assertEqual(output.read_bytes(), b'previous bundle')
                self.assertEqual(list(root.glob('bundle.zip.*.tmp')), [])
                with patch.object(packaging.os, 'replace', side_effect=OSError('replace failed')):
                    with self.assertRaisesRegex(OSError, 'replace failed'):
                        packaging.package(output)
                self.assertEqual(output.read_bytes(), b'previous bundle')
                self.assertEqual(list(root.glob('bundle.zip.*.tmp')), [])
                packaging.package(output)
                with zipfile.ZipFile(output) as z:
                    self.assertEqual(z.read('InputAlignWorker/main.py'), b'replacement')


if __name__ == '__main__':
    unittest.main()
