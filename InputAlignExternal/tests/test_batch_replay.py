"""Native history replay must equal independent step calls, including all fields."""
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'worker'))
from predictor import load_simulator
from gdgen.sim.fast import FastSimulator
from gdgen.sim.level import build_level

class BatchReplayTests(unittest.TestCase):
    def test_all_modes_and_every_history_length_match_separate_steps(self):
        for mode in range(8):
            sim=FastSimulator(build_level({'kA2':str(mode)},[],triggers=False))
            initial=sim.initial_state()
            snapshot=sim.view(initial)
            history=0xCAFE00F012345678
            for count in (0,1,2,31,63,64):
                with self.subTest(mode=mode,count=count):
                    sequential=initial
                    for i in range(count): sequential=sim.step(sequential,bool(history>>(count-i-1)&1))
                    batched=sim.replay(initial,history,count)
                    self.assertEqual(sim.view(sequential),sim.view(batched))
                    self.assertEqual(sim.view(initial),snapshot)

    def test_invalid_limits_and_foreign_state_never_call_native(self):
        sim=load_simulator('kA2,0;')
        state=sim.initial_state()
        for history,count in ((-1,1),(2**64,1),(0,-1),(0,65),(0,1.5)):
            with self.assertRaises(ValueError): sim.replay(state,history,count)
        other=load_simulator('kA2,0;')
        with self.assertRaises(ValueError): sim.replay(other.initial_state(),0,1)

    def test_native_failure_keeps_original_state_owned_and_unchanged(self):
        sim=load_simulator('kA2,0;')
        initial=sim.initial_state();snapshot=sim.view(initial)
        library=sim._lib
        sim._lib=Mock(wraps=library)
        sim._lib.gd_replay.return_value=None
        with self.assertRaises(RuntimeError): sim.replay(initial,0,64)
        sim._lib=library
        self.assertEqual(sim.view(initial),snapshot)

    def test_older_library_falls_back_to_identical_step_calls(self):
        sim=load_simulator('kA2,0;')
        state=sim.initial_state()
        expected=sim.replay(state,0xF0,8)
        library=sim._lib
        sim._lib=Mock(wraps=library)
        sim._lib.gd_replay=None
        result=sim.replay(state,0xF0,8)
        self.assertEqual(sim._lib.gd_step.call_count,8)
        sim._lib=library
        self.assertEqual(sim.view(result),sim.view(expected))

    def test_replay_over_move_toggle_spawn_and_teleport_matches_steps(self):
        cases=[
            'kA2,0;1,1,2,120,3,15,57,5;1,901,2,20,51,5,29,300,10,0.1;',
            'kA2,0;1,1,2,120,3,15,57,5;1,1049,2,20,51,5,56,0;',
            'kA2,0;1,1,2,120,3,15,57,5;1,1268,2,20,51,7,63,0.1;1,1049,2,20,51,5,56,0,57,7,62,1;',
            'kA2,0;1,747,2,60,3,45,54,300;',
            'kA2,0;1,200,2,60,3,15;', # Speed portal changes the persistent speed log.
        ]
        for raw in cases:
            with self.subTest(level=raw):
                sim=load_simulator(raw);initial=sim.initial_state();sequential=initial
                for _ in range(64): sequential=sim.step(sequential,False)
                self.assertEqual(sim.view(sim.replay(initial,0,64)),sim.view(sequential))

    def test_predictor_accepts_older_python_wrapper_without_batch_method(self):
        from predictor import Predictor
        from protocol import Header, FRAME, state_tuple
        sim=load_simulator('kA2,0;')
        state=sim.initial_state()
        for _ in range(10): state=sim.step(state,False)
        sim.replay=None
        predictor=Predictor(sim)
        predictor.synchronize(Header(FRAME,1,2,1,10),state_tuple(sim.view(state)),0,10)
        self.assertEqual(predictor.tick,10)
        self.assertEqual(sim.view(predictor.state),sim.view(state))
