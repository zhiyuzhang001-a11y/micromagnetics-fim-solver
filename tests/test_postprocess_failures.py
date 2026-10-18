"""Adversarial offline controls; no native models or field evaluations."""
import json,struct,unittest
from unittest.mock import patch
import numpy as np
import test_skyrmion_postprocess as support
from fimrun.postprocess import analyze_ovf,read_ovf,frames_from_state
from fimrun.postprocess.geometry import measure,image
from fimrun.postprocess.calibration import texture

class Failures(support.Offline):
    def test_polygon_moments_exact_and_singular_triangle(self):
        from fimrun.postprocess.geometry import moments
        v=np.array([[-3.,-2.],[3.,-2.],[3.,2.],[-3.,2.]])*1e-9
        angle=.73;rot=np.array([[np.cos(angle),-np.sin(angle)],[np.sin(angle),np.cos(angle)]])
        origin=np.array([1.2e-6,-.7e-6]);v=v@rot.T+origin
        area,center,cov,_,_=moments(v)
        self.assertAlmostEqual(area/1e-18,24.,places=9);np.testing.assert_allclose(center,origin,rtol=0,atol=2e-22)
        np.testing.assert_allclose(cov,rot@np.diag([3e-18,4e-18/3])@rot.T,rtol=2e-13,atol=1e-31)
        m=np.zeros((4,4,3));m[...,2]=1;m[1,1,2]=-1
        raw=measure(m,np.array([1e-9]*3),np.zeros(3),'periodic_xy')
        self.assertGreater(raw['singular_triangles'],0);self.assertFalse(raw['valid_topology'])
    def test_uniform_multiple_and_open_cut(self):
        c=json.loads(support.CAL.read_text())
        m,h,o,_=texture(cells=80)
        uniform=np.zeros_like(m);uniform[...,2]=1
        self.assertFalse(measure(uniform,h,o,'periodic_xy',calibration=c)['valid_geometry'])
        one,h,o,_=texture(cells=80,center=(64e-9,128e-9),radius=18e-9)
        two,_,_,_=texture(cells=80,center=(180e-9,128e-9),radius=18e-9)
        multi=one.copy();mask=two[...,2]<1;multi[mask]=two[mask]
        v=measure(multi,h,o,'periodic_xy',calibration=c)
        self.assertFalse(v['valid_geometry']);self.assertEqual(v['core_count'],2)
        cut,h,o,_=texture(cells=80,center=(1e-9,128e-9))
        self.assertFalse(measure(cut,h,o,'open',calibration=c)['valid_geometry'])
        p=self.root/'uniform.ovf';support.write_ovf(p,uniform,h,o,'A',{'boundary':'periodic_xy'})
        r=analyze_ovf([{'A':p}],self.root/'invalid.csv',calibration=support.CAL)[0]
        self.assertTrue(np.isnan(r['A_radius_m']));self.assertFalse(r['A_valid_geometry']);self.assertTrue(np.isnan(r['B_chi_rad']))
    def test_half_box_and_unrecoverable_full_winding(self):
        frames=[]
        for i,x in enumerate((20e-9,148e-9,151e-9)):
            entry={}
            for label,flip in (('A',False),('B',True)):
                m,h,o,_=texture(cells=112,center=(x,100e-9),flip=flip)
                p=self.root/f'{i}_{label}.ovf';support.write_ovf(p,m,h,o,label,dict(boundary='periodic_xy',run_id='half',segment_id='s',stage='rk4',time_s=i*1e-10));entry[label]=p
            frames.append(entry)
        r=analyze_ovf(frames,self.root/'half.csv',calibration=support.CAL,assume_temporal_sampling=True)
        self.assertFalse(r[1]['valid_tracking']);self.assertIn('ambiguous_temporal_image',r[1]['reason_codes']);self.assertFalse(any(x['valid_velocity'] for x in r))
        # The same saved array can represent any integer number of full turns.
        # This is a mathematical ambiguity, not a detectable validity gate.
        m,h,o,_=texture(cells=80,center=(23e-9,117e-9));other,_,_,_=texture(cells=80,center=(23e-9+256e-9,117e-9))
        np.testing.assert_allclose(m,other,atol=2e-14,rtol=0)
        np.testing.assert_allclose(image(np.array([256e-9,0]),np.array([256e-9]*2)),[0,0])
    def test_topology_failure_clears_only_topology_history(self):
        frames=self.frames();from fimrun.postprocess import pipeline
        original=pipeline.measure;count=0
        def damaged(*args,**kwargs):
            nonlocal count
            v=original(*args,**kwargs)
            if count in (4,5):v['valid_topology']=False;v['reasons'].append('injected_topology_gap')
            count+=1;return v
        with patch.object(pipeline,'measure',side_effect=damaged):
            r=analyze_ovf(frames,self.root/'topogap.csv',calibration=support.CAL,assume_temporal_sampling=True)
        self.assertTrue(r[2]['valid_tracking']);self.assertTrue(np.isnan(r[2]['A_topo_unwrapped_x']))
        self.assertTrue(np.isnan(r[2]['A_topo_x']));self.assertNotIn('A_topo_vx_mps',r[3]);self.assertTrue(r[3]['valid_velocity'])
        self.assertEqual(r[3]['A_topo_image_x'],0)
    def test_binary32_assumption_both_endians_and_no_silent_default(self):
        m,h,o,_=texture(cells=80);m=m.astype('f4').astype('f8')
        for endian in ('<','>'):
            p=self.root/('le.ovf' if endian=='<' else 'be.ovf');support.write_ovf(p,m,h,o,'A',{})
            head=p.read_bytes().split(b'# Begin: Data Text')[0]
            p.write_bytes(head+b'# Begin: Data Binary 8\n'+struct.pack(endian+'d',123456789012345.)+m.astype(endian+'f8').tobytes()+b'\n# End: Data Binary 8\n# End: Segment\n')
            with self.assertRaisesRegex(ValueError,'normalization'):read_ovf(p)
            d=read_ovf(p,legacy={'normalization_roundoff':'binary32-gamma12'})
            self.assertEqual(d['normalization']['roundoff_assumption'],'binary32-gamma12')
    def test_immutable_source_snapshot_and_metadata_rejection(self):
        frames=self.frames();p=frames[0]['A'];raw=p.read_bytes()
        original=type(p).read_bytes
        def changing(path):
            if path==p:
                p.write_bytes(raw.replace(b'0.0',b'9.9',1));return raw
            return original(path)
        with patch.object(type(p),'read_bytes',changing):d=read_ovf(p)
        self.assertEqual(d['sha256'],__import__('hashlib').sha256(raw).hexdigest());self.assertEqual(d['fields']['time_s'],'0.0')
        p.write_bytes(raw.replace(b'# xmin: 0',b'# xmin: 1'))
        with self.assertRaisesRegex(ValueError,'bounding box'):read_ovf(p)
        p.write_bytes(raw.replace(b'# Desc: sublattice=A',b'# Desc: sublattice=A\n# Desc: quantity=magnetization_Apm'))
        with self.assertRaisesRegex(ValueError,'quantity/units'):read_ovf(p)
        p.write_bytes(b'')
        r=analyze_ovf([frames[0]],self.root/'empty.csv',calibration=support.CAL)[0]
        self.assertIn('unsupported OVF',r['reason_codes'])
