"""Reuse requires identical input and a freshly validated reconstructed state."""
from dataclasses import replace
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'worker'))
from predictor import Predictor, load_simulator
from protocol import Header, FRAME, VALID, state_tuple


class PredictionReuseTests(unittest.TestCase):
    def setUp(self):
        self.predictor = Predictor(load_simulator('kA2,0;1,8,2,30,3,55;'))
        self.predictor.native = Mock(wraps=self.predictor.native)
        actual = state_tuple(self.predictor.sim.view(self.predictor.state))
        self.frame = (Header(FRAME,1,2,1), (*actual[:4], actual[4]|VALID), 0,0,80,20000,0)

    def test_identical_verified_query_uses_one_native_search(self):
        first = self.predictor.forecast(*self.frame)
        self.assertIsNotNone(first)
        for _ in range(10):
            self.assertEqual(self.predictor.forecast(*self.frame), first)
        self.assertEqual(self.predictor.native.call_count, 1)

    def test_changed_query_parameters_cannot_reuse_a_decision(self):
        self.predictor.forecast(*self.frame)
        for index, value in [(0, replace(self.frame[0],epoch=1)),
                             (0, replace(self.frame[0],hi=3)),
                             (0, replace(self.frame[0],lo=3)),
                             (1, (self.frame[1][0]+.01, *self.frame[1][1:])),
                             (2,1), (4,81), (5,19000), (6,1)]:
            changed = list(self.frame); changed[index] = value
            before = self.predictor.native.call_count
            self.predictor.forecast(*changed)
            self.assertEqual(self.predictor.native.call_count, before+1)
            self.predictor.forecast(*self.frame)

    def test_reconstructed_state_identity_is_required(self):
        self.predictor.forecast(*self.frame)
        self.predictor.state = self.predictor.sim.initial_state()
        self.predictor.forecast(*self.frame)
        self.assertEqual(self.predictor.native.call_count,2)

    def test_disabled_query_cannot_return_cached_success(self):
        self.predictor.forecast(*self.frame)
        disabled=list(self.frame)
        disabled[1]=(*disabled[1][:4],disabled[1][4]&~VALID)
        self.assertIsNone(self.predictor.forecast(*disabled))
        disabled=list(self.frame); disabled[4]=0
        self.assertIsNone(self.predictor.forecast(*disabled))
        self.assertEqual(self.predictor.native.call_count,1)

    def test_new_attempt_does_not_reuse_the_previous_decision(self):
        self.predictor.forecast(*self.frame)
        new = list(self.frame); new[0] = replace(new[0], session=2)
        self.predictor.forecast(*new)
        self.assertEqual(self.predictor.native.call_count,2)

    def test_cache_never_skips_divergence_validation(self):
        self.predictor.forecast(*self.frame)
        self.predictor.sim.view = Mock(side_effect=RuntimeError('inspection failed'))
        with self.assertRaises(RuntimeError): self.predictor.forecast(*self.frame)
        self.assertTrue(self.predictor.rejected)
        self.assertEqual(self.predictor.native.call_count,1)

    def test_incomplete_queries_are_retried(self):
        real = self.predictor.native
        for result in (0,2,3):
            with self.subTest(result=result):
                self.predictor.native = Mock(return_value=result)
                self.assertIsNone(self.predictor.forecast(*self.frame))
                self.assertIsNone(self.predictor.forecast(*self.frame))
                self.assertEqual(self.predictor.native.call_count,2)
        self.predictor.native = real
        self.assertIsNotNone(self.predictor.forecast(*self.frame))

    def test_reference_search_is_independent_of_native_cache(self):
        expected=self.predictor.forecast(*self.frame)
        self.assertEqual(self.predictor.forecast(*self.frame, clock=lambda:0.), expected)
        self.assertEqual(self.predictor.native.call_count,1)
