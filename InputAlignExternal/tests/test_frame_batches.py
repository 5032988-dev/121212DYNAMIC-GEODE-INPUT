"""Out-of-order UDP histories must be replayed in physics order before coalescing."""
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'worker'))
from main import coalesce_frames
from predictor import Predictor, load_simulator
from protocol import Header, FRAME, VALID, state_tuple, HEADER, DECISION_BODY


def frames_for(sim, ticks, session=1, varied=False):
    states = {}
    state = sim.initial_state()
    history = 0
    for tick in range(max(ticks) + 1):
        if tick in ticks:
            actual = state_tuple(sim.view(state))
            states[tick] = (Header(FRAME,1,2,session,tick), (*actual[:4], actual[4] | VALID),
                            history,min(tick,64),80,20000,0)
        held = varied and bool(tick // 11 % 2)
        state = sim.step(state,held)
        history = ((history << 1) | held) & ((1 << 64) - 1)
    return [states[tick] for tick in ticks]


class FrameBatchTests(unittest.TestCase):
    def test_empty_batch_is_rejected(self):
        with self.assertRaises(ValueError): coalesce_frames(None, [])
        with self.assertRaises(ValueError): coalesce_frames(None, [None] * 66)

    def test_same_tick_uses_latest_input_epoch(self):
        frames = frames_for(load_simulator('kA2,0;'), [0])
        base = frames[0]
        newest = (Header(FRAME,1,2,1,0,3), *base[1:])
        middle = (Header(FRAME,1,2,1,0,2), *base[1:])
        self.assertIs(coalesce_frames(None, [newest,base,middle]), newest)

    def test_old_attempt_never_replays_after_new_attempt_is_available(self):
        sim = load_simulator('kA2,0;')
        old = frames_for(sim, [60,120],session=1)
        new = frames_for(sim, [0],session=2)[0]
        p = Mock(session=1,tick=0,rejected=False)
        self.assertIs(coalesce_frames(p, [old[1],new,old[0]]), new)
        p.synchronize.assert_not_called()

    def test_reordered_retained_history_recovers_a_real_correction(self):
        # Position a verified overhead-spike fixture ahead of tick120.
        empty = load_simulator('kA2,0;')
        reference = empty.initial_state()
        for _ in range(120): reference = empty.step(reference,False)
        x = empty.view(reference)['x']
        sim = load_simulator(f'kA2,0;1,8,2,{x+30},3,55;')
        p = Predictor(sim)
        batch = frames_for(sim, [120,60,121])
        latest = coalesce_frames(p, batch)
        response = p.forecast(*latest)
        self.assertIsNotNone(response)
        self.assertEqual((p.session,p.tick,p.rejected),(1,121,False))
        values = DECISION_BODY.unpack_from(response,HEADER.size)
        state = p.state
        for _ in range(4 + values[10]): state = sim.step(state,False)
        for _ in range(80):
            state = sim.step(state,bool(values[11]))
            self.assertFalse(sim.view(state)['dead'])

    def test_missing_history_is_not_guessed(self):
        sim = load_simulator('kA2,0;')
        p = Predictor(sim)
        latest = coalesce_frames(p, frames_for(sim, [120,80]))
        with self.assertRaises(ValueError): p.forecast(*latest)
        self.assertTrue(p.rejected)

    def test_ordered_and_reordered_batches_have_identical_native_state(self):
        sim1, sim2 = load_simulator('kA2,0;'), load_simulator('kA2,0;')
        p1, p2 = Predictor(sim1), Predictor(sim2)
        ordered = frames_for(sim1,[40,80,120,160],varied=True)
        scrambled = [ordered[i] for i in (3,1,0,2)]
        p1.synchronize(*coalesce_frames(p1,ordered)[:4])
        p2.synchronize(*coalesce_frames(p2,scrambled)[:4])
        self.assertEqual(sim1.view(p1.state), sim2.view(p2.state))

    def test_divergent_prefix_still_rejects_the_attempt(self):
        sim = load_simulator('kA2,0;')
        p = Predictor(sim)
        batch = frames_for(sim,[120,60])
        old = batch[1]
        wrong = (old[1][0] + 1, *old[1][1:])
        batch[1] = (old[0],wrong,*old[2:])
        latest = coalesce_frames(p,batch)
        with self.assertRaises(ValueError): p.forecast(*latest)
        self.assertTrue(p.rejected)
