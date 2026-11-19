"""Bounded failure evidence and constant-space query measurements."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'worker'))
from diagnostics import DivergenceJournal, QueryStats
from predictor import Predictor, load_simulator
from protocol import Header, FRAME, state_tuple

class JournalTests(unittest.TestCase):
    def test_real_mismatch_logs_once_per_attempt_without_tokens(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'divergences.jsonl'
            sim=load_simulator('kA2,0;')
            predictor=Predictor(sim, diagnostics=DivergenceJournal(path))
            expected=state_tuple(sim.view(predictor.state))
            for session in (1,1,2):
                with self.assertRaises(ValueError):
                    predictor.synchronize(Header(FRAME,123456789,987654321,session), (expected[0]+5,*expected[1:]),0,0)
            records=[json.loads(line) for line in path.read_text().splitlines()]
            self.assertEqual([r['attempt'] for r in records],[1,2])
            self.assertEqual(records[0]['delta']['x'],5)
            self.assertIn('robot_boost',records[0]['model'])
            self.assertNotIn('123456789',path.read_text())
            self.assertNotIn('987654321',path.read_text())
            self.assertTrue(predictor.rejected)

    def test_nonfinite_model_is_recorded_as_null_without_hiding_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            journal=DivergenceJournal(Path(directory)/'trace.jsonl')
            predictor=Mock(tick=1)
            predictor.sim.view.return_value={'x':float('nan'),'y':105.,'y_vel':0.,'speed':.9}
            journal.record(predictor,Header(FRAME,1,2,1,1),(1.,105.,0.,.9,0),0,1,ValueError('divergence'))
            record=json.loads(journal.path.read_text())
            self.assertIsNone(record['model']['x'])
            self.assertIsNone(record['delta']['x'])

    def test_rotation_and_io_failure_never_authorize_a_query(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'log.jsonl'
            sim=load_simulator('kA2,0;')
            predictor=Predictor(sim,diagnostics=DivergenceJournal(path,max_bytes=4096))
            expected=state_tuple(sim.view(predictor.state))
            for session in range(1,30):
                with self.assertRaises(ValueError):
                    predictor.synchronize(Header(FRAME,1,2,session),(expected[0]+1,*expected[1:]),0,0)
            self.assertLessEqual(path.stat().st_size,4096)
            self.assertLessEqual(path.with_suffix('.previous.jsonl').stat().st_size,4096)
            predictor.diagnostics=DivergenceJournal(Path(directory))  # Writing a directory fails.
            with self.assertRaises(ValueError): predictor.synchronize(Header(FRAME,1,2,30),(expected[0]+1,*expected[1:]),0,0)
            self.assertTrue(predictor.rejected)

class StatsTests(unittest.TestCase):
    def test_counts_search_results_without_calling_them_applied_corrections(self):
        stats=QueryStats()
        stats.observe('correction',.001,.0005,6000)
        stats.observe('deadline',.007,.004,6000)
        stats.observe('cached',.0001,.0001,3000)
        report=stats.report(1.)
        self.assertEqual(report['queries'],3)
        self.assertEqual(report['proposals'],1)
        self.assertEqual(report['deadlines'],1)
        self.assertEqual(report['over_budget'],1)
        self.assertEqual(report['cached'],1)
        self.assertAlmostEqual(report['cpu_percent'],.46)

class WorkerTimingTests(unittest.TestCase):
    def test_retained_prefix_stage_is_included_in_query_metrics(self):
        import main
        import socket
        import threading
        import time
        from unittest.mock import patch
        from protocol import FRAME_BODY
        with tempfile.TemporaryDirectory() as directory, socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as game:
            game.bind(('127.0.0.1',0));game.settimeout(5)
            path=Path(directory)
            (path/'bridge.json').write_text(json.dumps({'version':1,'port':game.getsockname()[1],'tokenHi':'b','tokenLo':'16'}))
            (path/'level.txt').write_text('kA2,0;')
            predictor=Mock(session=1,tick=0,rejected=False,last_obstacle=None,last_outcome='direct')
            predictor.forecast.return_value=None
            stats=Mock()
            original=main.coalesce_frames
            def expensive_prefix(*args):
                time.sleep(.03)
                until=time.process_time()+.006
                while time.process_time()<until: pass
                return original(*args)
            stop=threading.Event();errors=[]
            def serve():
                try: main.serve(path,stop=stop)
                except Exception as error: errors.append(error)
            with patch.object(main,'load_simulator'),patch.object(main,'Predictor',return_value=predictor),patch.object(main,'QueryStats',return_value=stats),patch.object(main,'coalesce_frames',side_effect=expensive_prefix):
                thread=threading.Thread(target=serve)
                thread.start()
                try:
                    _,endpoint=game.recvfrom(2048)
                    game.sendto(Header(FRAME,11,22,1).pack()+FRAME_BODY.pack(0,105,0,.9,0,0,0,0,6000,0),endpoint)
                    game.recvfrom(2048)
                finally:
                    stop.set();thread.join(timeout=5)
                self.assertFalse(thread.is_alive())
            self.assertFalse(errors,errors)
            outcome,elapsed,cpu,budget=stats.observe.call_args.args
            self.assertGreaterEqual(elapsed,.03)
            self.assertGreaterEqual(cpu,.006)
            self.assertEqual((outcome,budget),('direct',6000))
