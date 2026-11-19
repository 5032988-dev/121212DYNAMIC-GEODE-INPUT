"""Distance filtering must not weaken physics validation or invent geometry."""
import sys
from pathlib import Path
from types import SimpleNamespace
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'worker'))
from obstacles import ObstacleSensor


def box(ident, left, right, **extra):
    return SimpleNamespace(id=ident, x0=left, x1=right, y0=90., y1=120.,
                           category=extra.get('category', 'hazard'), dynamic=extra.get('dynamic', False))


def sensor(objects, distance=100, **options):
    return ObstacleSensor(SimpleNamespace(objects=objects), distance=distance, **options)


class ObstacleTests(unittest.TestCase):
    def test_detects_transformed_bounds_not_object_id_or_artwork(self):
        s = sensor([box(999999, 240, 280)])
        result = s.query(150)
        self.assertEqual((result.object_id, result.distance), (999999, 90))
        self.assertEqual(s.query(139).reason, 'clear')
        self.assertEqual(s.query(140).distance, 100)
        self.assertEqual(s.query(280).distance, 0)
        self.assertEqual(s.query(281).reason, 'clear')

    def test_nested_wide_hitboxes_are_not_skipped_by_binary_search(self):
        s = sensor([box(1, -100, 1000), box(2, 1, 2), box(3, 4, 5)])
        self.assertEqual(s.query(500).object_id, 1)

    def test_distance_does_not_limit_search_unless_explicitly_requested(self):
        self.assertTrue(sensor([]).should_search(sensor([]).query(0)))
        limited = sensor([], limit_search=True)
        self.assertFalse(limited.should_search(limited.query(0)))
        self.assertTrue(limited.should_search(sensor([box(1, 50, 60)]).query(0)))

    def test_dynamic_world_or_invalid_geometry_cannot_report_clear(self):
        for objects in ([box(1, 500, 600, dynamic=True)],
                        [box(2, float('nan'), 600)], [box(3, 60, 50)]):
            s = sensor(objects, limit_search=True)
            self.assertEqual(s.query(0).reason, 'unavailable')
            self.assertTrue(s.should_search(s.query(0)))

    def test_only_damage_and_support_geometry_counts_as_obstacles(self):
        s = sensor([box(1, 10, 20, category='orb'), box(2, 30, 40, category='solid')])
        self.assertEqual(s.query(0).object_id, 2)

    def test_rejects_invalid_distance_and_position(self):
        for distance in (-1, 12001, float('nan'), float('inf'), True):
            with self.assertRaises(ValueError): sensor([], distance=distance)
        s = sensor([], limit_search=True)
        self.assertEqual(s.query(float('nan')).reason, 'unavailable')

class PredictionDistanceTests(unittest.TestCase):
    def make_predictor(self, distance, limit=True):
        from unittest.mock import Mock
        from predictor import Predictor, load_simulator
        from protocol import Header, FRAME, VALID, state_tuple
        p = Predictor(load_simulator('kA2,0;1,8,2,30,3,55;'),
                      sensor_settings={'distance':distance, 'limit_search':limit})
        p.native = Mock(wraps=p.native)
        actual = state_tuple(p.sim.view(p.state))
        frame = (Header(FRAME,1,2,1), (*actual[:4], actual[4] | VALID), 0,0,80,20000,0)
        return p, frame

    def test_range_filter_preserves_original_search_and_horizon_when_near(self):
        p, frame = self.make_predictor(600)
        self.assertIsNotNone(p.forecast(*frame))
        self.assertEqual(p.native.call_count, 1)
        self.assertEqual(p.native.call_args.args[2], 80)
        self.assertEqual(p.last_obstacle.reason, 'hitbox')

    def test_out_of_range_skips_search_but_still_validates_real_state(self):
        from unittest.mock import Mock
        p, frame = self.make_predictor(0)
        self.assertIsNone(p.forecast(*frame))
        self.assertEqual(p.native.call_count, 0)
        p.sim.view = Mock(side_effect=RuntimeError('diverged'))
        with self.assertRaises(RuntimeError): p.forecast(*frame)
        self.assertTrue(p.rejected)

    def test_default_observation_cannot_suppress_a_valid_correction(self):
        p, frame = self.make_predictor(0, False)
        self.assertIsNotNone(p.forecast(*frame))
        self.assertEqual(p.last_obstacle.reason, 'clear')

    def test_sensor_never_enables_unknown_object_physics(self):
        from predictor import load_simulator, UnsupportedLevel
        with self.assertRaisesRegex(UnsupportedLevel, 'desconocido'):
            load_simulator('kA2,0;1,999999,2,30,3,55;')

class SensorBoundaryTests(unittest.TestCase):
    def test_interval_index_matches_brute_force_on_overlaps_and_wide_bounds(self):
        import random
        rng = random.Random(2081)
        boxes = [box(i, left := rng.uniform(-200, 500), left + rng.uniform(1, 200)) for i in range(500)]
        s = sensor(boxes)
        for x in range(-250, 800, 3):
            distances = [max(0, b.x0 - x) for b in boxes if b.x1 >= x and b.x0 <= x + 100]
            result = s.query(x)
            self.assertEqual(result.distance, min(distances) if distances else None)

    def test_config_and_cli_override_are_validated(self):
        import tempfile
        from obstacles import read_settings
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)
            self.assertEqual(read_settings(path), {'distance':600, 'limit_search':False})
            config = path / 'obstacle-sensor.json'
            config.write_text('{"distance":100,"limit_search":true}')
            self.assertEqual(read_settings(path, 200), {'distance':200, 'limit_search':True})
            for text in ('[]', '{"distance":"bad"}', '{"limit_search":1}', '{"unknown":1}', 'x'*4097):
                config.write_text(text)
                with self.subTest(text=text[:30]), self.assertRaises(ValueError): read_settings(path)
