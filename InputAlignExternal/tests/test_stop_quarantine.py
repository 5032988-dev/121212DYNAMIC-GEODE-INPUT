"""Stop's engine behavior is not game-equivalent; the runtime must fail closed."""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'worker'))
from predictor import load_simulator, UnsupportedLevel


class StopQuarantineTests(unittest.TestCase):
    def test_stop_is_rejected_before_constructing_any_model(self):
        for suffix in ('', ',57,7,62,1', ',11,1'):
            with self.subTest(suffix=suffix), patch('predictor.build_level', side_effect=AssertionError('model construction reached')) as build:
                with self.assertRaisesRegex(UnsupportedLevel, 'Stop'):
                    load_simulator('kA2,0;1,901,2,10,51,9,57,7,28,100,10,1;'
                                   f'1,1616,2,60,51,7{suffix};')
                build.assert_not_called()
