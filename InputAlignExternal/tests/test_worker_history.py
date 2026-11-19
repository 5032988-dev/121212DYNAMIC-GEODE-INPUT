"""Regression coverage for failures while preserving queued UDP history."""
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'worker'))
from main import newer_frame
from protocol import FRAME, Header
from predictor import Predictor


def frame(tick, count=64, session=1):
    return (Header(FRAME, 11, 22, session, tick), (0., 0., 0., 1., 256),
            0, min(count, tick), 400, 6000, 0)


class HistoryTests(unittest.TestCase):
    def predictor(self):
        return Mock(session=1, tick=0, rejected=False)

    def test_replay_failure_rejects_attempt_and_keeps_latest_frame(self):
        for error in (RuntimeError('native state error'), ValueError('divergence'),
                      OverflowError('invalid state')):
            with self.subTest(error=type(error).__name__):
                predictor = self.predictor()
                predictor.synchronize.side_effect = error
                current, queued = frame(60), frame(100)
                self.assertIs(newer_frame(predictor, current, queued), queued)
                self.assertTrue(predictor.rejected)
                predictor.synchronize.assert_called_once_with(*current[:4])
                newer_frame(predictor, queued, frame(120))
                self.assertEqual(predictor.synchronize.call_count, 1)

    def test_real_predictor_blocks_failed_attempt_and_resets_on_restart(self):
        predictor = object.__new__(Predictor)
        predictor.session, predictor.tick, predictor.rejected = 1, 0, False
        predictor.state = object()
        predictor.sim = Mock(unsupported={})
        predictor.sim.step.side_effect = RuntimeError('native replay error')
        predictor.native = Mock()
        queued = newer_frame(predictor, frame(60), frame(100))
        with self.assertRaisesRegex(ValueError, 'Estado divergente'):
            predictor.forecast(*queued)
        predictor.native.assert_not_called()
        predictor.sim.step.side_effect = None
        predictor.sim.view.return_value = dict(x=0., y=0., y_vel=0., speed=1.,
            mode='cube', mini=False, upside_down=False, on_ground=False, held=False, dead=False)
        restart = list(frame(0, session=2))
        restart[1] = (0., 0., 0., 1., 0)  # Correction disabled for this telemetry packet.
        self.assertIsNone(predictor.forecast(*restart))
        self.assertFalse(predictor.rejected)
        self.assertEqual(predictor.session, 2)
        predictor.sim.initial_state.assert_called_once()
        predictor.native.assert_not_called()

    def test_replay_retains_history_before_window_moves(self):
        predictor = self.predictor()
        current, queued = frame(60), frame(100)
        self.assertIs(newer_frame(predictor, current, queued), queued)
        predictor.synchronize.assert_called_once_with(*current[:4])
        self.assertFalse(predictor.rejected)

    def test_no_replay_when_history_already_covers_gap(self):
        predictor = self.predictor()
        queued = frame(30)
        self.assertIs(newer_frame(predictor, frame(20), queued), queued)
        predictor.synchronize.assert_not_called()

    def test_old_packet_does_not_rewind(self):
        predictor = self.predictor()
        current = frame(60)
        self.assertIs(newer_frame(predictor, current, frame(50)), current)
        predictor.synchronize.assert_not_called()

    def test_next_attempt_remains_available(self):
        predictor = self.predictor()
        predictor.rejected = True
        queued = frame(1, session=2)
        self.assertIs(newer_frame(predictor, frame(60), queued), queued)
        predictor.synchronize.assert_not_called()

    def test_delayed_old_attempt_cannot_reset_the_current_attempt(self):
        predictor = object.__new__(Predictor)
        predictor.session, predictor.tick, predictor.rejected = 2, 10, True
        predictor.sim = Mock(unsupported={})
        predictor.state = object()
        with self.assertRaisesRegex(ValueError, 'antiguo'):
            predictor.synchronize(*frame(0, session=1)[:4])
        self.assertEqual((predictor.session, predictor.tick, predictor.rejected), (2, 10, True))
        predictor.sim.initial_state.assert_not_called()

    def test_direct_replay_errors_suspend_until_the_next_attempt(self):
        for error in (ValueError('bad state'), OverflowError('overflow'), RuntimeError('native error')):
            with self.subTest(error=type(error).__name__):
                predictor = object.__new__(Predictor)
                predictor.session, predictor.tick, predictor.rejected = 1, 0, False
                predictor.state = object()
                predictor.sim = Mock(unsupported={})
                predictor.sim.step.side_effect = error
                predictor.native = Mock()
                with self.assertRaises(type(error)):
                    predictor.forecast(*frame(1))
                self.assertTrue(predictor.rejected)
                predictor.sim.step.reset_mock(side_effect=True)
                with self.assertRaisesRegex(ValueError, 'Estado divergente'):
                    predictor.forecast(*frame(1))
                predictor.sim.step.assert_not_called()
                predictor.native.assert_not_called()

    def test_delayed_same_tick_older_input_epoch_is_not_selected(self):
        predictor = self.predictor()
        newer = list(frame(20))
        newer[0] = Header(FRAME, 11, 22, 1, 20, 5)
        older = list(frame(20))
        older[0] = Header(FRAME, 11, 22, 1, 20, 4)
        self.assertIs(newer_frame(predictor, newer, older), newer)
        self.assertIs(newer_frame(predictor, older, newer), newer)
        predictor.synchronize.assert_not_called()

    def test_stale_previous_session_is_not_replayed_when_new_session_is_known(self):
        predictor = self.predictor()
        predictor.session, predictor.tick = 2, 0
        previous, queued = frame(60, session=1), frame(100, session=2)
        self.assertIs(newer_frame(predictor, previous, queued), queued)
        predictor.synchronize.assert_not_called()
        self.assertFalse(predictor.rejected)

    def test_failed_new_attempt_initialization_is_not_retried_in_same_attempt(self):
        predictor = object.__new__(Predictor)
        predictor.session, predictor.tick, predictor.rejected = 1, 10, False
        predictor.state = object()
        predictor.sim = Mock(unsupported={})
        predictor.sim.initial_state.side_effect = RuntimeError('cannot initialize')
        with self.assertRaises(RuntimeError):
            predictor.synchronize(*frame(0, session=2)[:4])
        self.assertEqual(predictor.session, 2)
        self.assertTrue(predictor.rejected)
        with self.assertRaisesRegex(ValueError, 'Estado divergente'):
            predictor.synchronize(*frame(0, session=2)[:4])
        predictor.sim.initial_state.assert_called_once()


if __name__ == '__main__':
    unittest.main()
