"""CodeRabbit-generated: bounded queries over the model's static obstacle bounds.

Broad phase only: proximity is not a collision or survival proof. Unknown object
IDs are still rejected by load_simulator; this module never supplies new physics.
"""
from __future__ import annotations

from bisect import bisect_left
from dataclasses import dataclass
import json
import math
from pathlib import Path
from types import SimpleNamespace


@dataclass(frozen=True)
class Detection:
    reason: str
    object_id: int | None = None
    distance: float | None = None

    def label(self) -> str:
        if self.reason == 'hitbox':
            return f'Hitbox {self.object_id}: {self.distance:.0f}u'
        return 'Sensor: sin obstaculo cercano' if self.reason == 'clear' else 'Sensor: no disponible (sin filtro)'


class ObstacleSensor:
    """O(log N) nearest forward X interval query, including overlapping wide boxes.

Distance is measured from the player's center to the nearest obstacle AABB edge
in GD units, ignoring Y deliberately. Over-detection cannot authorize a click.
"""
    def __init__(self, level, *, distance: float = 600, limit_search: bool = False):
        if type(distance) not in (int, float) or not math.isfinite(distance) or not 0 <= distance <= 12000:
            raise ValueError('Distancia del sensor fuera de 0..12000 unidades GD')
        if type(limit_search) is not bool:
            raise ValueError('limit_search debe ser true o false')
        self.distance = distance
        self.limit_search = limit_search
        self.available = True
        intervals = []
        for obj in level.objects:
            if obj.dynamic:
                self.available = False
            if obj.category not in ('solid', 'slope', 'hazard'):
                continue
            if (not all(math.isfinite(v) for v in (obj.x0, obj.x1, obj.y0, obj.y1))
                    or obj.x1 < obj.x0 or obj.y1 < obj.y0):
                self.available = False
                continue
            intervals.append((obj.x0, obj.x1, obj.id))
        self.intervals = sorted(intervals)
        self.ends = []
        end = -math.inf
        for _, right, _ in self.intervals:
            end = max(end, right)
            self.ends.append(end)

    def query(self, x: float) -> Detection:
        if not self.available or not math.isfinite(x):
            return Detection('unavailable')
        # The first prefix max reaching x identifies the first unpassed interval,
        # even if a very wide earlier object contains many short later objects.
        index = bisect_left(self.ends, x)
        if index < len(self.intervals):
            left, _, ident = self.intervals[index]
            distance = max(0., left - x)
            if distance <= self.distance:
                return Detection('hitbox', ident, distance)
        return Detection('clear')

    def should_search(self, detection: Detection) -> bool:
        # Missing/uncertain geometry never disables the existing search.
        return not self.limit_search or detection.reason != 'clear'


def read_settings(directory: Path, override: float | None = None) -> dict:
    path = directory / 'obstacle-sensor.json'
    config = {}
    if path.is_file():
        with path.open(encoding='utf-8') as stream:
            text = stream.read(4097)
        if len(text) > 4096:
            raise ValueError('Configuracion del sensor demasiado grande')
        config = json.loads(text)
    if not isinstance(config, dict) or set(config) - {'distance', 'limit_search'}:
        raise ValueError('Configuracion del sensor desconocida')
    if override is not None:
        config['distance'] = override
    # Reuse exact validation before any native model is constructed.
    probe = ObstacleSensor(SimpleNamespace(objects=()), **config)
    return {'distance': probe.distance, 'limit_search': probe.limit_search}
