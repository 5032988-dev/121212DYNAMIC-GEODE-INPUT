"""CPU isolation must be physically disjoint and restore only its own changes."""
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'worker'))
from cpu_isolation import Core, choose_masks, AffinityLease, parse_cores
import struct

class FakeWindows:
    def __init__(self):
        self.worker='worker'; self.game='game'; self.masks={'worker':255,'game':255}
        self.fail_game=False; self.events=[]
    def affinity(self,h):return self.masks[h]
    def set_affinity(self,h,mask):
        if h=='game' and self.fail_game:raise OSError('denied')
        self.events.append((h,mask));self.masks[h]=mask

class IsolationTests(unittest.TestCase):
    def cores(self):return [Core(3),Core(12),Core(48),Core(192)]
    def test_reserves_both_smt_threads_and_leaves_three_cores(self):
        game,worker=choose_masks(self.cores(),255,255,None)
        self.assertEqual((game,worker),(63,192));self.assertEqual(game&worker,0)
    def test_refuses_small_hybrid_or_partial_core(self):
        with self.assertRaises(ValueError):choose_masks(self.cores()[:2],15,15,None)
        hybrid=[Core(3,1),Core(12,1),Core(48,0),Core(192,0)]
        with self.assertRaises(ValueError):choose_masks(hybrid,255,255,None)
        self.assertEqual(choose_masks(hybrid,255,255,0),(252,3))
        with self.assertRaises(ValueError):choose_masks(self.cores(),255,127,3)
    def test_restores_masks_and_preserves_external_change(self):
        api=FakeWindows();lease=AffinityLease(api,63,192);lease.apply();lease.close()
        self.assertEqual(api.masks,{'game':255,'worker':255})
        lease=AffinityLease(api,63,192);lease.apply();api.masks['game']=15;lease.close()
        self.assertEqual(api.masks,{'game':15,'worker':255})
        lease.close()
    def test_partial_application_rolls_back_worker(self):
        api=FakeWindows();api.fail_game=True;lease=AffinityLease(api,63,192)
        with self.assertRaises(OSError):lease.apply()
        self.assertEqual(api.masks,{'game':255,'worker':255})
    def test_topology_decoding_and_invalid_records(self):
        records=b''
        for core in self.cores():
            record=bytearray(48);struct.pack_into('<II',record,0,0,48)
            struct.pack_into('<H',record,30,1);struct.pack_into('<QH',record,32,core.mask,0)
            records+=record
        self.assertEqual(parse_cores(records),self.cores())
        for broken in (records[:-1],b'\0'*48):
            with self.assertRaises(ValueError):parse_cores(broken)

class ContextTests(unittest.TestCase):
    def run_context(self, config=None, mode=None, interrupt_setup=False):
        import contextlib
        import io
        import json
        import tempfile
        from types import SimpleNamespace
        from unittest.mock import patch
        import cpu_isolation
        api = FakeWindows()
        api.cores = lambda: [Core(3), Core(12), Core(48), Core(192)]
        api.on_close = lambda cleanup: None
        api.close = lambda: api.events.append('close')
        original_set = api.set_affinity
        if interrupt_setup:
            def interrupted_set(handle, mask):
                original_set(handle, mask)
                if handle == 'worker' and mask == 192:
                    raise KeyboardInterrupt
            api.set_affinity = interrupted_set
        output = io.StringIO()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            if config is not None:
                (path / 'cpu-isolation.json').write_text(json.dumps(config))
            with patch.object(cpu_isolation, 'os', SimpleNamespace(name='nt', getppid=lambda: 123)), \
                    patch.object(cpu_isolation, 'WindowsCPU', return_value=api) as factory, \
                    contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
                inside = None
                try:
                    with cpu_isolation.isolation(path, mode):
                        inside = dict(api.masks)
                        raise RuntimeError('simulate worker failure')
                except (RuntimeError, KeyboardInterrupt):
                    pass
        return api, inside, output.getvalue(), factory.call_args

    def test_context_restores_on_worker_error_and_uses_parent_pid(self):
        api, inside, output, call = self.run_context()
        self.assertEqual(inside, {'worker':192, 'game':63})
        self.assertEqual(api.masks, {'worker':255, 'game':255})
        self.assertEqual(api.events[-1], 'close')
        self.assertEqual(call.args, (123,))
        self.assertIn('aislamiento activo', output)

    def test_interrupt_during_assignment_restores_masks(self):
        api, inside, output, call = self.run_context(interrupt_setup=True)
        self.assertIsNone(inside)
        self.assertEqual(api.masks, {'worker':255, 'game':255})
        self.assertEqual(api.events[-1], 'close')

    def test_disabled_or_invalid_config_never_opens_game(self):
        for config, mode in [({'enabled':False},None), ({'enabled':True},'off'),
                             ([],None), ({'worker_core':True},None),
                             ({'game_pid':-1},None), ({'unknown':True},None),
                             ({'worker_core':50},None)]:
            with self.subTest(config=config, mode=mode):
                api, inside, output, call = self.run_context(config, mode)
                self.assertEqual(inside, {'worker':255,'game':255})
                self.assertEqual(api.masks, inside)
                if config != {'worker_core':50}:
                    self.assertIsNone(call)
                self.assertNotIn('aislamiento activo', output)

    def test_explicit_pid_and_command_override(self):
        api, inside, output, call = self.run_context({'enabled':False,'game_pid':456}, 'auto')
        self.assertEqual(call.args, (456,))
        self.assertEqual(inside, {'worker':192,'game':63})

    def test_rejects_partial_physical_cores_and_expanding_original_affinity(self):
        cores = [Core(3), Core(12), Core(48), Core(192)]
        with self.assertRaises(ValueError):
            choose_masks(cores, 127, 255, 0)
        api = FakeWindows()
        api.masks['worker'] = 3
        with self.assertRaises(ValueError):
            AffinityLease(api, 63, 192)
        self.assertEqual(api.events, [])

    def test_external_change_before_apply_is_preserved(self):
        api = FakeWindows()
        lease = AffinityLease(api, 63, 192)
        api.masks['game'] = 15
        with self.assertRaises(OSError):
            lease.apply()
        self.assertEqual(api.masks, {'game':15,'worker':255})

class LauncherTests(unittest.TestCase):
    def test_main_wraps_worker_in_affinity_context(self):
        from contextlib import contextmanager
        from unittest.mock import patch
        import main as worker_main
        events = []
        @contextmanager
        def fake_isolation(directory, mode):
            events.append(('enter', directory, mode))
            try:
                yield
            finally:
                events.append('restore')
        def fail_serve(directory):
            events.append('serve')
            raise KeyboardInterrupt
        with patch.object(sys, 'argv', ['main.py','--bridge','.','--cpu-isolation','off']), \
                patch.dict(worker_main.os.environ, {'GDGEN_SIM_LIB':'synthetic-no-load'}), \
                patch.object(worker_main, 'isolation', fake_isolation), \
                patch.object(worker_main, 'serve', fail_serve):
            self.assertEqual(worker_main.main(), 0)
        self.assertEqual(events[0], ('enter', worker_main.bundle, 'off'))
        self.assertEqual(events[1:], ['serve','restore'])
