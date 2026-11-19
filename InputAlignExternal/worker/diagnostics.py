"""Bounded local diagnostics; observed mismatches never become correction evidence."""
from __future__ import annotations

import json
import math
import os
from pathlib import Path


class DivergenceJournal:
    """At most one record per increasing attempt, two bounded JSONL files.

    No bridge tokens or level data are recorded. Writes occur after rejection,
    and I/O errors disable this journal without changing prediction eligibility.
    """
    def __init__(self, path: Path, *, max_bytes: int = 2 * 1024 * 1024):
        if not 4096 <= max_bytes <= 16 * 1024 * 1024:
            raise ValueError('Diagnostic size outside limits')
        self.path = path
        self.max_bytes = max_bytes
        self.last_attempt = -1
        self.disabled = False

    def record(self, predictor, header, actual, history, count, error):
        if self.disabled or header.session <= self.last_attempt:
            return
        self.last_attempt = header.session
        try:
            try:
                model = predictor.sim.view(predictor.state, include_lists=False)
            except (ValueError, RuntimeError, OverflowError):
                model = None
            names = ('x','y','y_vel','speed','flags')
            observed = dict(zip(names, actual))
            delta = ({key: observed[key] - model[key] for key in names[:4]}
                     if model is not None else None)
            record = {'schemaVersion': 1, 'generatedBy': 'InputAlignExternal',
                      'attempt': header.session, 'tick': header.tick, 'epoch': header.epoch,
                      'model_tick': predictor.tick, 'reason': str(error)[:512],
                      'actual': observed, 'model': model, 'delta': delta,
                      'history_count': count, 'history_bits': history,
                      'verification': 'partial wire state; correction suspended'}
            def finite(value):
                if isinstance(value, float) and not math.isfinite(value):
                    return None
                if isinstance(value, dict):
                    return {k: finite(v) for k,v in value.items()}
                if isinstance(value, (tuple,list)):
                    return [finite(v) for v in value]
                return value
            encoded = (json.dumps(finite(record), allow_nan=False, separators=(',',':'))+'\n').encode('utf-8')
            if len(encoded) > self.max_bytes:
                self.disabled = True
                return
            size = self.path.stat().st_size if self.path.exists() else 0
            if size + len(encoded) > self.max_bytes:
                os.replace(self.path, self.path.with_suffix('.previous.jsonl'))
            with self.path.open('ab') as stream:
                stream.write(encoded)
        except (OSError, ValueError, TypeError, OverflowError):
            self.disabled = True


class QueryStats:
    """Constant-space counters over a reporting window, no per-frame file I/O."""
    def __init__(self):
        self.queries = self.proposals = self.deadlines = self.deferred = self.over_budget = self.cached = 0
        self.elapsed = self.cpu = self.maximum = 0.

    def observe(self, outcome: str, elapsed: float, cpu: float, budget_us: int):
        self.queries += 1
        self.proposals += outcome == 'correction'
        self.deadlines += outcome == 'deadline'
        self.deferred += outcome == 'deferred'
        self.cached += outcome == 'cached'
        self.over_budget += elapsed * 1e6 > budget_us
        self.elapsed += elapsed
        self.cpu += cpu
        self.maximum = max(self.maximum, elapsed)

    def report(self, seconds: float):
        return {'queries': self.queries, 'proposals': self.proposals, 'deadlines': self.deadlines,
                'deferred': self.deferred, 'over_budget': self.over_budget, 'cached': self.cached,
                'mean_ms': self.elapsed * 1000 / max(1,self.queries), 'max_ms': self.maximum * 1000,
                'cpu_percent': self.cpu * 100 / max(.001,seconds)}
