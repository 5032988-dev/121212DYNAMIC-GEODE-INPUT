import importlib.util
from pathlib import Path
import tempfile
import unittest
import zipfile
import hashlib
from unittest.mock import patch
spec=importlib.util.spec_from_file_location('packaging_selection',Path(__file__).resolve().parents[1]/'scripts/package-windows.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)

class PackagingSelectionTests(unittest.TestCase):
    def test_ambiguous_dll_rejected_and_exact_tested_dll_shipped(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'Release').mkdir()
            (root/'mod.geode').write_bytes(b'mod')
            (root/'gdsim.dll').write_bytes(b'old')
            tested=root/'Release/gdsim.dll';tested.write_bytes(b'tested')
            runtime=root/'runtime.zip'
            with zipfile.ZipFile(runtime,'w') as z:
                for name in ('python.exe','python312.dll','python312.zip'):z.writestr(name,b'fixture')
            self.enterContext(patch.object(module, 'PYTHON_RUNTIME_SHA256', hashlib.sha256(runtime.read_bytes()).hexdigest()))
            output=root/'result.zip'
            with self.assertRaisesRegex(ValueError,'ambiguous'):
                module.package(root,runtime,output)
            module.package(root,runtime,output,native=tested)
            with zipfile.ZipFile(output) as z:
                self.assertEqual(z.read('InputAlignWorker/gdsim.dll'),b'tested')

    def test_missing_runtime_rejected_before_output(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            (root/'mod.geode').write_bytes(b'mod');(root/'gdsim.dll').write_bytes(b'dll')
            runtime=root/'runtime.zip'
            with zipfile.ZipFile(runtime,'w') as z:z.writestr('python.exe',b'fixture')
            self.enterContext(patch.object(module, 'PYTHON_RUNTIME_SHA256', hashlib.sha256(runtime.read_bytes()).hexdigest()))
            output=root/'result.zip'
            with self.assertRaisesRegex(ValueError,'runtime files'):
                module.package(root,runtime,output)
            self.assertFalse(output.exists())

    def test_untrusted_runtime_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            (root/'mod.geode').write_bytes(b'mod'); (root/'gdsim.dll').write_bytes(b'dll')
            runtime=root/'runtime.zip';runtime.write_bytes(b'untrusted')
            with self.assertRaisesRegex(ValueError,'Untrusted'):
                module.package(root,runtime,root/'result.zip')

    def test_worker_cannot_replace_runtime(self):
        import json
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); project=root/'project'; build=root/'build'
            vendor=project/'worker/vendor';vendor.mkdir(parents=True);build.mkdir()
            (vendor/'UPSTREAM.json').write_text(json.dumps({'files':[]}))
            for name in ('README.md','GUIA-INSTALACION.md','IMPLEMENTATION-NOTES.md','LICENSE'):(project/name).write_bytes(b'fixture')
            (project/'worker/python.exe').write_bytes(b'bad overlay')
            (build/'mod.geode').write_bytes(b'mod');(build/'gdsim.dll').write_bytes(b'dll')
            runtime=root/'runtime.zip'
            with zipfile.ZipFile(runtime,'w') as z:
                for name in ('python.exe','python312.dll','python312.zip'):z.writestr(name,b'fixture')
            with patch.object(module,'ROOT',project), patch.object(module,'PYTHON_RUNTIME_SHA256',hashlib.sha256(runtime.read_bytes()).hexdigest()):
                with self.assertRaisesRegex(ValueError,'collides'):
                    module.package(build,runtime,root/'result.zip')

    def test_build_checkout_preserves_worker_and_includes_referenced_guides(self):
        import json
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory) / 'build' / 'project'
            vendor = project / 'worker/vendor'
            vendor.mkdir(parents=True)
            (vendor / 'UPSTREAM.json').write_text(json.dumps({'files': []}))
            for name in ('README.md', 'GUIA-INSTALACION.md', 'IMPLEMENTATION-NOTES.md', 'LICENSE'):
                (project / name).write_text(name)
            (project / 'worker/main.py').write_text('worker')
            (project / 'worker/build').mkdir()
            (project / 'worker/build/scratch.txt').write_text('exclude')
            build = project / 'artifacts'
            build.mkdir()
            (build / 'mod.geode').write_bytes(b'mod')
            (build / 'gdsim.dll').write_bytes(b'dll')
            runtime = project / 'runtime.zip'
            with zipfile.ZipFile(runtime, 'w') as z:
                for name in ('python.exe', 'python312.dll', 'python312.zip'): z.writestr(name, b'fixture')
            output = project / 'result.zip'
            with patch.object(module, 'ROOT', project), patch.object(module, 'PYTHON_RUNTIME_SHA256', hashlib.sha256(runtime.read_bytes()).hexdigest()):
                module.package(build, runtime, output)
            with zipfile.ZipFile(output) as z:
                self.assertEqual(z.read('InputAlignWorker/main.py'), b'worker')
                for name in ('GUIA-INSTALACION.md', 'IMPLEMENTATION-NOTES.md'):
                    self.assertEqual(z.read(name), name.encode())
                self.assertNotIn('InputAlignWorker/build/scratch.txt', z.namelist())
