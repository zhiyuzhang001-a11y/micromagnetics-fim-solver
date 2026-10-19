"""Cached synthetic angle plotting only; no frame parsing or scientific calls."""
import copy
import json
import math
import unittest
import xml.etree.ElementTree as ET
from unittest.mock import patch

from fimrun.postprocess.analysis import Analysis, _TOKEN


def cached(angles, *, stage='rk4'):
    rows = []
    for i, value in enumerate(angles):
        row = dict(run_id='synthetic-wrap', segment_id='same', stage=stage,
                   time_s=i*1e-12 if stage == 'rk4' else None, iteration=i,
                   source_bindings=json.dumps({'analysis_options': {}}))
        for label in ('A', 'B'):
            row.update({label+'_axis_rad': value, label+'_valid_axis': value is not None,
                        label+'_chi_rad': value, label+'_valid_helicity': value is not None})
        rows.append(row)
    return Analysis(_TOKEN, rows, range(len(rows)), (), ())


def joins(result, metric, label='A'):
    svg = ET.fromstring(result.plot(metric, sublattice=label).data)
    return [node for node in svg.iter() if node.tag.endswith('path')
            and node.get('data-series', '').startswith(label+'_')]


class AxisWrap(unittest.TestCase):
    def test_axis_pi_boundary_both_directions_and_stages(self):
        for stage in ('rk4', 'sdesc'):
            for angles in ((math.pi-.02, .02), (.02, math.pi-.02)):
                for label in ('A', 'B'):
                    with self.subTest(stage=stage, angles=angles, label=label):
                        self.assertEqual(joins(cached(angles, stage=stage), 'axis', label), [])

    def test_axis_short_changes_and_half_pi_boundary_still_connect(self):
        for angles in ((.02, .06), (math.pi-.06, math.pi-.02), (0., math.pi/2)):
            for label in ('A', 'B'):
                self.assertEqual(len(joins(cached(angles), 'axis', label)), 1)

    def test_helicity_uses_two_pi_period_not_axis_period(self):
        self.assertEqual(joins(cached((math.pi-.02, -math.pi+.02)), 'helicity'), [])
        self.assertEqual(len(joins(cached((0., math.pi-.02)), 'helicity')), 1)

    def test_invalid_identity_and_reverse_time_do_not_join(self):
        self.assertEqual(joins(cached((.02, None, .06)), 'axis'), [])
        for key, value in (('segment_id', 'other'), ('time_s', -1e-12)):
            result = cached((.02, .06))
            rows = copy.deepcopy(result._rows)
            rows[1][key] = value
            changed = Analysis(_TOKEN, rows, (0, 1), (), ())
            self.assertEqual(joins(changed, 'axis'), [])

    def test_plot_preserves_values_and_never_reanalyzes(self):
        result = cached((math.pi-.02, .02))
        before = copy.deepcopy(result._rows)
        with patch('fimrun.postprocess.analysis._analyze_rows', side_effect=AssertionError('no reanalysis')):
            self.assertEqual(joins(result, 'axis'), [])
        self.assertEqual(before, result._rows)
