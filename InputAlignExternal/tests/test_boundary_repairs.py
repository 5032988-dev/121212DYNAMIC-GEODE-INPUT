"""Validate public search and wire boundaries without running unbounded searches."""
import sys
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'worker'))
from protocol import Header,STATUS_BODY,HEADER,status
from predictor import load_simulator
from gdgen.sim.search import find_path

class BoundaryRepairsTests(unittest.TestCase):
    def test_status_is_utf8_and_null_terminated_at_every_boundary(self):
        for text in ('a'*118+'ó','a'*117+'🙂','á'*70,'plain'):
            data=STATUS_BODY.unpack_from(status(Header(4,1,2),0,text),HEADER.size)[1]
            self.assertEqual(data[-1],0)
            actual=data.split(b'\0',1)[0].decode('utf-8')
            self.assertTrue(text.startswith(actual))

    def test_reference_limits_are_checked_before_step(self):
        initial=SimpleNamespace(x=0,dead=False)
        step=Mock(side_effect=lambda state,hold:SimpleNamespace(x=state.x+1,dead=False))
        for key in ('input_period','max_frontier'):
            for value in (0,-1):
                with self.assertRaises(ValueError):find_path(initial,step,2,2,**{key:value})
        step.assert_not_called()
        self.assertTrue(find_path(initial,step,2,2,max_frontier=1,key=lambda st:st.x).passed)

    def test_native_search_rejects_narrowing_and_error_status(self):
        sim=load_simulator('kA2,0;')
        library=sim._lib
        sim._lib=Mock(wraps=library)
        for key in ('input_period','max_frontier'):
            for value in (2**31,2**32+1):
                with self.assertRaises(ValueError):sim.find_path(max_ticks=1,**{key:value})
        sim._lib.gd_find_path.assert_not_called()
        sim._lib.gd_find_path.return_value=-1
        with self.assertRaises(RuntimeError):sim.find_path(max_ticks=1)
        sim._lib=library
