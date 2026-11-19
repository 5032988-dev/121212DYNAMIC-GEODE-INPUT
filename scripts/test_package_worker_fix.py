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


if __name__ == '__main__':
    unittest.main()
