"""Regression coverage for unsafe simulator API boundaries."""
from concurrent.futures import ThreadPoolExecutor
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'worker/vendor'))
from gdgen.sim import fast
from gdgen.sim.collide import Simulator, StepContacts
from gdgen.sim.level import build_level
from gdgen.sim.triggers import parse_triggers


class SearchBoundaryTests(unittest.TestCase):
    def test_invalid_limits_never_enter_native_search(self):
        sim = object.__new__(fast.FastSimulator)
        sim.level = Mock(length=10)
        sim._lib = Mock()
        sim._h = None
        for key in ('input_period', 'max_frontier'):
            for value in (0, -1):
                with self.subTest(key=key, value=value):
                    with self.assertRaises(ValueError):
                        sim.find_path(max_ticks=1, **{key: value})
        sim._lib.gd_find_path.assert_not_called()

    def test_compilers_use_distinct_temporary_files(self):
        with tempfile.TemporaryDirectory() as directory:
            barrier = threading.Barrier(2)
            paths = []
            def compile_stub(args, **kwargs):
                target = Path(args[args.index('-o') + 1])
                paths.append(target)
                target.write_bytes(b'library')
                barrier.wait(timeout=5)
            with patch.dict(os.environ, GDGEN_SIM_BUILD=directory, CXX='fake-cxx'), \
                    patch.object(fast.subprocess, 'run', side_effect=compile_stub):
                with ThreadPoolExecutor(max_workers=2) as pool:
                    results = list(pool.map(lambda _: fast._compile(), range(2)))
            self.assertEqual(results[0], results[1])
            self.assertEqual(len(set(paths)), 2)
            self.assertEqual(list(Path(directory).iterdir()), [results[0]])

    def test_failed_compiler_cleans_temporary_file(self):
        with tempfile.TemporaryDirectory() as directory:
            def fail(args, **kwargs):
                Path(args[args.index('-o') + 1]).write_bytes(b'partial')
                raise subprocess.CalledProcessError(1, args)
            with patch.dict(os.environ, GDGEN_SIM_BUILD=directory, CXX='fake-cxx'), \
                    patch.object(fast.subprocess, 'run', side_effect=fail):
                with self.assertRaises(subprocess.CalledProcessError): fast._compile()
            self.assertEqual(list(Path(directory).iterdir()), [])


class GeometryBoundaryTests(unittest.TestCase):
    def test_nonfinite_geometry_is_rejected_without_relocation(self):
        for key in ('2', '3', '6', '32', '128', '129'):
            for value in ('nan', 'inf', '-inf'):
                with self.subTest(key=key, value=value):
                    with self.assertRaises(ValueError):
                        build_level({}, [{'1': '1', '2': '100', '3': '15', key: value}])

    def test_move_duration_must_fit_native_ticks(self):
        for duration in ('nan', 'inf', '-inf', '1e100', '-1', str(2**63 / 240)):
            with self.subTest(duration=duration):
                with self.assertRaises(ValueError):
                    parse_triggers([{'1': '901', '10': duration}])
        triggers, _ = parse_triggers([{'1': '901', '10': '0'}])
        self.assertEqual(triggers[0].duration, 0)

    def test_inverted_ship_contacts_use_world_sides(self):
        level = build_level({'kA2': '1'}, [{'1': '1', '2': '100', '3': '90'}])
        sim = Simulator(level)
        block = level.objects[0]
        for upside in (False, True):
            for top in (False, True):
                with self.subTest(upside=upside, top=top):
                    p = sim.initial_state()
                    p.upside_down = upside
                    p.x = p.prev_x = block.x
                    p.y = p.prev_y = block.y0 - p.width / 2 if top else block.y1 + p.width / 2
                    p.y_vel = 1 if top else -1
                    contacts = StepContacts()
                    sim._collide_solid(p, block, contacts)
                    self.assertEqual(contacts.top_uid if top else contacts.bottom_uid, block.index)
                    self.assertEqual(contacts.bottom_uid if top else contacts.top_uid, -1)
    def test_previous_world_top_contact_survives_deep_inverted_overlap(self):
        level = build_level({'kA2': '1'}, [{'1': '1', '2': '100', '3': '90'}])
        sim = Simulator(level)
        block = level.objects[0]
        p = sim.initial_state()
        p.upside_down = True
        p.x = p.prev_x = block.x
        p.y = p.prev_y = block.y0
        p.y_vel = 1
        p.prev_top_uid = block.index
        contacts = StepContacts()
        sim._collide_solid(p, block, contacts)
        self.assertEqual(contacts.top_uid, block.index)
        self.assertFalse(p.dead)


class NativeContactParityTests(unittest.TestCase):
    def test_inverted_ship_block_contacts_match_reference(self):
        from gdgen.sim.fast import FastSimulator, player_fields
        for inverted in (False, True):
            for y in ('0', '60'):
                level = build_level({'kA2': '1', 'kA8': str(int(inverted))},
                                    [{'1': '1', '2': '20', '3': y}])
                py, native = Simulator(level), FastSimulator(level)
                p, n = py.initial_state(), native.initial_state()
                for tick in range(80):
                    hold = bool(tick // 9 % 2)
                    p, n = py.step(p, hold), native.step(n, hold)
                    self.assertEqual(player_fields(p), native.view(n))
                    if p.dead: break
