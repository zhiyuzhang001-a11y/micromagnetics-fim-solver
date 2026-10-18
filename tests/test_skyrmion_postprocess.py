"""Analytic offline end-to-end and provenance regressions; Native forbidden."""
import csv,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import numpy as np
from fimrun.postprocess import analyze_ovf,read_ovf,frames_from_state
from fimrun.postprocess.calibration import texture
from fimrun.postprocess.io import ROOT,sha,tool
from fimrun.micromagnetics.native import Native,EVALUATIONS

CAL=ROOT/'fimrun/postprocess/calibration_v1.json'

def write_ovf(path,m,h,origin,label,metadata):
    ny,nx=m.shape[:2]
    header=['# OOMMF OVF 2.0','# Segment count: 1','# Begin: Segment','# Begin: Header', '# Desc: ordinary prose, never a configuration expression', '# Desc: sublattice='+label, '# Desc: '+'; '.join(k+'='+str(v) for k,v in metadata.items()),'# meshtype: rectangular','# meshunit: m','# valuedim: 3','# valueunits: 1 1 1','# valuelabels: mx my mz']
    for i,(axis,n) in enumerate(zip('xyz',(nx,ny,1))):header += [f'# {axis}nodes: {n}',f'# {axis}base: {origin[i]+h[i]/2:.17g}',f'# {axis}stepsize: {h[i]:.17g}',f'# {axis}min: {origin[i]:.17g}',f'# {axis}max: {origin[i]+n*h[i]:.17g}']
    text='\n'.join(header+['# End: Header','# Begin: Data Text'])+'\n'+'\n'.join(' '.join(format(x,'.17g') for x in row) for row in m.reshape(-1,3))+'\n# End: Data Text\n# End: Segment\n'
    path.write_text(text)


class Offline(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name).resolve();self.before=dict(EVALUATIONS)
        self.forbidden=patch.object(Native,'__init__',side_effect=AssertionError('Native forbidden'));self.forbidden.start()
    def tearDown(self):
        self.forbidden.stop();self.assertEqual(self.before,EVALUATIONS);self.temp.cleanup()
    def frames(self,stage='rk4',missing_time=False):
        frames=[]
        for i,t in enumerate((0.,1e-10,2.5e-10,4.5e-10,7e-10)):
            entry={};center=np.array([254e-9,3e-9])+np.array([10.,-3.])*t
            for label,flip in [('A',False),('B',True)]:
                m,h,o,truth=texture(cells=112,center=center+(np.array([6e-9,-3e-9]) if flip else 0),radius=(24e-9+i*.2e-9)*(1.08 if flip else 1),chi=3.+i*.1+(.15 if flip else 0),flip=flip)
                meta=dict(stage=stage,accepted_index=i,boundary='periodic_xy',mirrors='10,10',run_id='analytic',segment_id=stage)
                if not missing_time:meta['time_s']=repr(t if stage=='rk4' else 1e-9)
                path=self.root/f'{stage}-{i}-{label}.ovf';write_ovf(path,m,h,o,label,meta);entry[label]=path
            frames.append(entry)
        return frames
    def test_periodic_relative_breathing_phase_and_velocity(self):
        rows=analyze_ovf(self.frames(),self.root/'result.csv',calibration=CAL,assume_temporal_sampling=True,ab_reference='antiparallel',velocity_window_s=[0.,7e-10])
        for i,r in enumerate(rows):
            self.assertTrue(r['valid_pair'],r['reason_codes']);self.assertTrue(r['A_valid_geometry']);self.assertTrue(r['A_valid_helicity'],r['reason_codes']);self.assertTrue(r['B_valid_helicity'],r['reason_codes'])
            self.assertLess(abs(r['AB_area_dx']-6e-9),1e-10);self.assertLess(abs(r['AB_area_dy']+3e-9),1e-10)
            self.assertLess(abs(r['AB_chi_difference_rad']-.15),.0025)
            self.assertLess(abs(r['AB_radius_difference_m']-(24e-9+i*.2e-9)*.08),.4e-9)
            binding=json.loads(r['source_bindings']);self.assertIn('source_manifest_sha256',binding['implementation']);self.assertIn('canonical_sha256',binding['calibration']);self.assertTrue(binding['sources']['A']['sha256'])
        self.assertTrue(all(r['valid_velocity'] for r in rows[1:-1]))
        for r in rows[1:-1]:
            self.assertLess(abs(r['A_area_vx_mps']-10),r['A_v_position_envelope_mps']);self.assertLess(abs(r['A_area_vy_mps']+3),r['A_v_position_envelope_mps'])
        self.assertNotIn('A_area_vx_mps',rows[0]);self.assertFalse(rows[-1]['valid_velocity'])
        self.assertGreater(rows[-1]['A_area_unwrapped_x'],256e-9)
        with self.assertRaises(FileExistsError):analyze_ovf([],self.root/'result.csv',calibration=CAL)
    def test_static_and_missing_time_never_velocity(self):
        rows=analyze_ovf(self.frames(stage='sdesc'),self.root/'static.csv',calibration=CAL,assume_temporal_sampling=True)
        self.assertTrue(all(not r['valid_velocity'] and not r['valid_tracking'] for r in rows));self.assertEqual([r['iteration'] for r in rows],list(range(5)))
        rows=analyze_ovf(self.frames(missing_time=True),self.root/'missing.csv',calibration=CAL,assume_temporal_sampling=True)
        self.assertTrue(all('missing_time' in r['reason_codes'] and not r['valid_velocity'] for r in rows))
    def test_desc_duplicates_and_source_conflicts(self):
        frames=self.frames();d=read_ovf(frames[0]['A']);self.assertEqual(len(d['normalization']['descriptions']),3)
        self.assertEqual(d['fields']['time_s'],'0.0');self.assertEqual(d['label'],'A')
        frames[0]['mapping']={'time_s':99.}
        r=analyze_ovf(frames[:1],self.root/'conflict.csv',calibration=CAL)[0]
        self.assertIn('conflicting metadata',r['reason_codes']);self.assertFalse(r['valid_pair'])
        self.assertIn('mapping',json.loads(r['source_bindings'])['sources'])
        frames[0]['mapping'].update(overrides={'time_s':True},override_reason='explicit fixture clock correction')
        r=analyze_ovf(frames[:1],self.root/'override.csv',calibration=CAL)[0]
        self.assertTrue(r['valid_pair']);self.assertEqual(r['time_s'],99.)
        self.assertTrue(json.loads(r['source_bindings'])['facts']['time_s']['override'])
        source=frames[1]['A'];source.write_text(source.read_text().replace('# Desc: sublattice=A','# Desc: sublattice=A\n# Desc: time_s=777'))
        with self.assertRaisesRegex(ValueError,'conflicting Desc'):read_ovf(source)
    def test_legacy_precision_requires_explicit_assumption_and_evidence(self):
        m,h,o,t=texture(cells=80);path=self.root/'A.ovf';write_ovf(path,m,h,o,'A',{})
        # An arbitrary precision override cannot be silently applied to f64 text.
        with self.assertRaisesRegex(ValueError,'binary32'):read_ovf(path,legacy={'normalization_roundoff':'binary32-gamma12'})
    def test_branch_break_and_no_sampling_assumption(self):
        frames=self.frames();r=analyze_ovf(frames,self.root/'none.csv',calibration=CAL)
        self.assertTrue(all(not row['valid_tracking'] for row in r))
        frames[2]['B']=self.root/'missing_B.ovf'
        r=analyze_ovf(frames,self.root/'gap.csv',calibration=CAL,assume_temporal_sampling=True)
        self.assertFalse(r[2]['valid_tracking']);self.assertFalse(any(row['valid_velocity'] for row in r))
