"""Independent-review regressions: relative ambiguity, public images, SVG."""
import json,unittest
from unittest.mock import patch
import numpy as np
import test_skyrmion_postprocess as support
from fimrun.postprocess import analyze_ovf
from fimrun.postprocess.calibration import texture

class Review(unittest.TestCase):
    def setUp(self):
        self.fixture=support.Offline();self.fixture.setUp();self.root=self.fixture.root
    def tearDown(self):self.fixture.tearDown()
    def frames(self,a,b,*,stage='rk4',origin=(0.,0.,0.),tag='case'):
        frames=[]
        for i,(ca,cb) in enumerate(zip(a,b)):
            pair={}
            for label,center,flip in (('A',ca,False),('B',cb,True)):
                m,h,o,_=texture(cells=112,center=center,flip=flip)
                o=np.array(origin);path=self.root/f'{tag}_{i}_{label}.ovf'
                meta=dict(boundary='periodic_xy',mirrors='10,10',run_id=tag,segment_id='s',stage=stage,accepted_index=i,time_s=i*1e-10 if stage=='rk4' else 0.)
                support.write_ovf(path,m,h,o,label,meta);pair[label]=path
            frames.append(pair)
        return frames
    def test_half_box_main_nan_but_diagnostic_survives_all_modes(self):
        for stage,sampling in (('rk4',True),('rk4',False),('sdesc',True)):
            for separation in (128e-9,127.9e-9):
                tag=f'{stage}_{sampling}_{separation}'
                f=self.frames([(20e-9,100e-9)],[(20e-9+separation,100e-9)],stage=stage,tag=tag)
                r=analyze_ovf(f,self.root/(tag+'.csv'),calibration=support.CAL,assume_temporal_sampling=sampling)[0]
                self.assertTrue(r['A_valid_geometry']);self.assertTrue(r['B_valid_topology'])
                for kind in ('area','topo'):
                    self.assertFalse(r['AB_'+kind+'_valid_relative']);self.assertTrue(np.isnan(r['AB_'+kind+'_dx']));self.assertTrue(np.isnan(r['AB_'+kind+'_dy']))
                    self.assertIn('ambiguous',r['AB_'+kind+'_relative_reason']);self.assertTrue(np.isfinite(r['AB_'+kind+'_minimum_image_dx']))
                    self.assertGreater(abs(r['AB_'+kind+'_minimum_image_dx']),127e-9)
                self.assertFalse(r['valid_tracking'])
    def test_static_and_unasserted_short_relative_diagnostics(self):
        for stage in ('rk4','sdesc'):
            f=self.frames([(254e-9,3e-9)],[(4e-9,0.)],stage=stage,tag=stage)
            r=analyze_ovf(f,self.root/(stage+'.csv'),calibration=support.CAL)[0]
            self.assertFalse(r['valid_tracking'])
            for kind in ('area','topo'):
                self.assertTrue(r['AB_'+kind+'_valid_relative'])
                self.assertLess(abs(r['AB_'+kind+'_minimum_image_dx']-6e-9),.1e-9)
                self.assertAlmostEqual(r['AB_'+kind+'_dx'],r['AB_'+kind+'_minimum_image_dx'])
                self.assertTrue(np.isnan(r['B_'+kind+'_image_x']))
    def test_default_example_initial_image_includes_alignment(self):
        rows=analyze_ovf(self.fixture.frames(),self.root/'original-example.csv',calibration=support.CAL,assume_temporal_sampling=True)
        self.assert_images(rows,(0.,0.,0.))
        for kind in ('area','topo'):
            self.assertEqual(rows[0]['B_'+kind+'_image_x'],1)
            self.assertLess(abs(rows[0]['B_'+kind+'_unwrapped_x']-260e-9),.1e-9)
            self.assertLess(abs(rows[0]['B_'+kind+'_x']-4e-9),.1e-9)
    def assert_images(self,rows,origin):
        L=256e-9
        for r in rows:
            if not r['valid_tracking']:continue
            for label in ('A','B'):
                for kind in ('area','topo'):
                    for j,axis in enumerate('xy'):
                        wrapped=r[f'{label}_{kind}_{axis}'];unwrapped=r[f'{label}_{kind}_unwrapped_{axis}'];count=r[f'{label}_{kind}_image_{axis}']
                        self.assertTrue(origin[j]<=wrapped<origin[j]+L)
                        self.assertEqual(count,int(count));self.assertAlmostEqual((unwrapped-wrapped)/L,count,places=12)
    def test_image_identity_both_axes_directions_origins_and_reset(self):
        origin=(1.2e-6,-.7e-6,0.)
        for sign in (1,-1):
            start=np.array([254e-9,3e-9] if sign==1 else [3e-9,254e-9])
            centers=[start+sign*np.array([7e-9,-5e-9])*i for i in range(6)]
            other=[x+np.array([6e-9,-3e-9]) for x in centers]
            frames=self.frames(centers,other,origin=origin,tag=str(sign))
            rows=analyze_ovf(frames,self.root/f'images-{sign}.csv',calibration=support.CAL,assume_temporal_sampling=True)
            self.assertTrue(all(r['valid_tracking'] for r in rows));self.assert_images(rows,origin)
            for kind in ('area','topo'):
                self.assertEqual(rows[0][f'B_{kind}_image_x'],1 if sign==1 else 0)
                self.assertEqual(rows[-1][f'A_{kind}_image_x'],sign)
                self.assertEqual(rows[-1][f'A_{kind}_image_y'],-sign)
            # Missing frame breaks both histories, then reconstructs initial
            # canonical A chart and B image; never inherits lost winding.
            frames[2]['B']=self.root/'missing.ovf'
            rows=analyze_ovf(frames,self.root/f'reset-{sign}.csv',calibration=support.CAL,assume_temporal_sampling=True)
            self.assertFalse(rows[2]['valid_tracking']);self.assertTrue(rows[3]['valid_tracking']);self.assert_images(rows,origin)
            self.assertEqual(rows[3]['A_area_image_x'],0)
    def test_relative_flags_independent_for_each_center_definition(self):
        f=self.frames([(20e-9,100e-9)],[(26e-9,100e-9)])
        from fimrun.postprocess import pipeline
        original=pipeline.measure;count=0
        def shifted(*args,**kwargs):
            nonlocal count
            d=original(*args,**kwargs)
            if count==1:d['topo_x']+=122e-9
            count+=1;return d
        with patch.object(pipeline,'measure',side_effect=shifted):
            r=analyze_ovf(f,self.root/'independent.csv',calibration=support.CAL,assume_temporal_sampling=True)[0]
        self.assertTrue(r['AB_area_valid_relative']);self.assertFalse(r['AB_topo_valid_relative'])
        self.assertTrue(np.isfinite(r['AB_area_dx']));self.assertTrue(np.isnan(r['AB_topo_dx']))
    def test_svg_static_and_unasserted_centers_have_visible_points(self):
        import xml.etree.ElementTree as ET
        from fimrun.postprocess import summary_svg
        for stage in ('sdesc','rk4'):
            f=self.frames([(254e-9,3e-9),(2e-9,5e-9)],[(4e-9,0.),(8e-9,2e-9)],stage=stage,tag='svg-'+stage)
            rows=analyze_ovf(f,self.root/(stage+'-svg.csv'),calibration=support.CAL)
            svg=summary_svg(rows);tree=ET.fromstring(svg);ns={'s':'http://www.w3.org/2000/svg'}
            centers=[e for e in tree.findall('.//s:circle',ns) if e.get('data-panel')=='0']
            self.assertEqual(len(centers),4);self.assertIn('wrapped points',svg)
            for e in tree.findall('.//s:circle',ns):
                self.assertTrue(np.isfinite(float(e.get('cx'))));self.assertTrue(np.isfinite(float(e.get('cy'))))
            self.assertFalse(tree.findall('.//s:script',ns));self.assertNotIn('matplotlib',svg)
