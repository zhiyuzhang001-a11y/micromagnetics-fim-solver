"""Saved-result reloads preserve plotting semantics without native or source reads."""
import copy
import json
import math
import re
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

import fimrun.postprocess as pp
from fimrun.postprocess.analysis import Analysis, _TOKEN, _METRICS, _columns
from fimrun.micromagnetics.native import Native, EVALUATIONS


class CSVLoad(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve()
        self.before = dict(EVALUATIONS)
        self.guard = patch.object(Native, '__init__', side_effect=AssertionError('no Native'))
        self.guard.start()

    def tearDown(self):
        self.guard.stop()
        self.assertEqual(self.before, EVALUATIONS)
        self.tmp.cleanup()

    def result(self):
        rows = []
        for i in range(3):
            row = dict(input_index=i, time_s=i*1e-12, stage='rk4', segment_id='one',
                       run_id='r', tracking_part=0, valid_pair=True, valid_tracking=True,
                       valid_velocity=False, reason_codes='', boundary='periodic_xy',
                       source_bindings=json.dumps({'schema':'source-bindings-v1',
                           'sources':{'A':{'path':str(self.root/'offline.ovf')}},
                           'analysis_options':{'ab_reference':None}}))
            for label in ('A', 'B'):
                for metric in _METRICS:
                    if metric == 'relative' and label == 'B': continue
                    for key, flag in _columns(metric, label):
                        if not flag.startswith('pair_'): row[flag] = True
                        row[key] = 1e-8
                row[label+'_valid_axis'] = False
                row[label+'_axis_rad'] = math.nan
                row[label+'_area_unwrapped_x'] = i*1e-9
                row[label+'_area_unwrapped_y'] = i*2e-9
                row[label+'_valid_geometry'] = i != 1
            rows.append(row)
        return Analysis(_TOKEN, rows, [4,6,8], [], list(rows[0]))

    def test_reload_plot_gaps_and_immutable_rows(self):
        original = self.result()
        path = self.root/'analysis.csv'
        original.to_csv(path)
        loaded = pp.load_csv(path)
        self.assertEqual(loaded.source_indices, (4,6,8))
        self.assertIs(loaded.rows[1]['A_valid_geometry'], False)
        self.assertTrue(math.isnan(loaded.rows[0]['A_axis_rad']))
        for metric in ('radius','helicity','center','axis'):
            strip_audit = lambda svg: re.sub(r'<desc>.*?</desc>', '', svg, flags=re.S)
            self.assertEqual(strip_audit(original.plot(metric).data),
                             strip_audit(loaded.plot(metric).data))
            tree = ET.fromstring(loaded.plot(metric).data)
            if metric in ('radius','center','axis'):
                self.assertFalse([n for n in tree.iter() if n.tag.endswith('path') and n.get('data-series')])
        with self.assertRaises(TypeError): loaded.rows[0]['A_radius_m'] = 0
        self.assertFalse(loaded.csv_source['original_sources_reverified'])
        self.assertIn('未重新读取', loaded.show().data)

    def test_no_original_reads_and_source_overwrite_protected(self):
        path = self.root/'analysis.csv'
        self.result().to_csv(path)
        read = Path.read_bytes
        with patch.object(Path, 'read_bytes', autospec=True, side_effect=lambda p: read(p) if p==path else self.fail('unexpected source read')):
            loaded = pp.load_csv(path)
            loaded.plot('radius')
        with self.assertRaises(ValueError): loaded.to_csv(self.root/'offline.ovf')
        with self.assertRaises(ValueError): loaded.to_csv(path)
        other = self.root/'copy.csv'
        loaded.to_csv(other)
        self.assertEqual(pp.load_csv(other).source_indices, loaded.source_indices)

    def test_scalar_malformed_boolean_duplicate_and_short_rows_rejected(self):
        path = self.root/'analysis.csv'
        self.result().to_csv(path)
        body = path.read_text()
        for damaged in ('time,mean_m\n0,1\n', body.replace('True','false-ish',1),
                        body.replace('input_index,','input_index,input_index,',1),
                        body+'0,1\n'):
            path.write_text(damaged)
            with self.assertRaises(ValueError): pp.load_csv(path)

    def test_explicit_selection_and_ambiguous_stage(self):
        result = self.result()
        result._rows[2]['stage'] = 'sdesc'
        result._rows[2]['segment_id'] = 'two'
        path = self.root/'analysis.csv'
        result.to_csv(path)
        with self.assertRaises(ValueError): pp.load_csv(path)
        self.assertEqual(pp.load_csv(path, stage='rk4').source_indices, (4,6))
        self.assertEqual(pp.load_csv(path, segment='two').source_indices, (8,))

    def test_empty_export_roundtrip(self):
        path = self.root/'empty.csv'
        columns = ['A_area_vx_mps','A_area_vy_mps','B_area_vx_mps','B_area_vy_mps',
                   'AB_radius_difference_m','AB_chi_difference_rad']
        Analysis(_TOKEN, [], [], [], columns).to_csv(path)
        result = pp.load_csv(path)
        self.assertEqual(len(result.rows), 0)
        self.assertIn('No submitted frames', result.show().data)
