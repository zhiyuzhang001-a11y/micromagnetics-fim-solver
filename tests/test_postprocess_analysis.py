"""New facade contracts and exact d100a00 row/CSV comparison, zero Native."""
import csv
import ast
import hashlib
import json
import subprocess
import types
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch
import xml.etree.ElementTree as ET

import test_skyrmion_postprocess as support
from fimrun.postprocess import analyze, analyze_ovf, read_ovf, generate_demo
from fimrun.postprocess.io import ROOT


class Facade(unittest.TestCase):
    setUp = support.Offline.setUp
    tearDown = support.Offline.tearDown
    frames = support.Offline.frames

    def baseline(self):
        code = (Path(__file__).parent/'fixtures/postprocess_d100a00.py').read_text()
        mod = types.ModuleType('fimrun.postprocess.frozen_pipeline')
        mod.__package__ = 'fimrun.postprocess'
        mod.__file__ = str(ROOT/'fimrun/postprocess/pipeline.py')
        exec(compile(code, 'frozen-d100a00-pipeline', 'exec'), mod.__dict__)
        return mod

    def same(self, a, b):
        # JSON compares NaN representations, all columns, binding facts and order.
        self.assertEqual(json.dumps(a, sort_keys=True), json.dumps(b, sort_keys=True))

    def test_scientific_body_ast_unchanged(self):
        old = (Path(__file__).parent/'fixtures/postprocess_d100a00.py').read_text()
        oldfn = next(n for n in ast.parse(old).body if isinstance(n,ast.FunctionDef) and n.name=='analyze_ovf')
        newfn = next(n for n in ast.parse((ROOT/'fimrun/postprocess/pipeline.py').read_text()).body if isinstance(n,ast.FunctionDef) and n.name=='_analyze_rows')
        self.assertEqual([ast.dump(n) for n in oldfn.body[:-3]], [ast.dump(n) for n in newfn.body[:-1]])

    def test_frozen_rows_and_legacy_csv(self):
        base = self.baseline()
        for stage in ('rk4','sdesc'):
            frames = self.frames(stage)
            options = dict(assume_temporal_sampling=True, ab_reference='antiparallel', velocity_window_s=(0.,7e-10))
            old = base.analyze_ovf(frames, self.root/(stage+'-old.csv'), **options)
            new = analyze_ovf(frames, self.root/(stage+'-new.csv'), **options)
            self.same(old, new)
            self.assertEqual((self.root/(stage+'-old.csv')).read_bytes(), (self.root/(stage+'-new.csv')).read_bytes())
            result = analyze(frames, **options)
            self.same(old, result._rows)
        base.analyze_ovf([],self.root/'old-empty.csv')
        analyze_ovf([],self.root/'new-empty.csv')
        self.assertEqual((self.root/'old-empty.csv').read_bytes(),(self.root/'new-empty.csv').read_bytes())

    def test_invalid_and_missing_frozen(self):
        frames = self.frames(missing_time=True)
        frames.append({'A':self.root/'missing.ovf'})
        expected = self.baseline().analyze_ovf(frames,self.root/'base.csv')
        result = analyze(frames)
        self.same(expected,result._rows)
        self.assertIn('source_or_analysis_error', result.rows[-1]['reason_codes'])
        self.assertIn('No valid samples', analyze([frames[-1]]).plot('radius').data)
        with self.assertRaises(ValueError): analyze([frames[-1]]).to_csv(frames[-1]['A'])

    def test_export_immutable_no_reanalysis(self):
        frames = self.frames()
        result = analyze(frames)
        before = json.dumps(result._rows,sort_keys=True)
        with self.assertRaises(TypeError): result.rows[0]['time_s']=1
        with patch('fimrun.postprocess.analysis._analyze_rows',side_effect=AssertionError('No rerun')):
            result.show(); result.table(metrics=['radius']); result.plot('shape');result.plot('relative')
            p=result.to_csv(self.root/'audit.csv');result.plot('radius', output=self.root/'radius.svg')
        self.assertEqual(before,json.dumps(result._rows,sort_keys=True))
        from fimrun.postprocess.analysis import _valid
        self.assertFalse(_valid(result.rows[0], 'pair_helicity'))
        exported=list(csv.DictReader(p.read_text().splitlines()))
        self.assertEqual([int(r['source_index']) for r in exported],list(range(5)))
        for path in [p,frames[0]['A']]:
            with self.assertRaises((FileExistsError,ValueError)): result.to_csv(path)
        with self.assertRaises(FileExistsError): result.plot('radius',output=self.root/'radius.svg')
        with self.assertRaises(ValueError): result.plot('radius',output=frames[0]['B'])
        dangling=self.root/'dangling.svg';dangling.symlink_to(self.root/'not-created.svg')
        with self.assertRaises(FileExistsError):result.plot('radius',output=dangling)
        self.assertFalse((self.root/'not-created.svg').exists())

    def test_selectors_and_source_indices(self):
        frames=self.frames()
        for frame in frames[1:3]:frame['mapping']={'segment_id':'other','overrides':{'segment_id':True},'override_reason':'fixture declaration'}
        with self.assertRaisesRegex(ValueError,'Ambiguous'):analyze(frames)
        result=analyze(frames, segment='rk4')
        self.assertEqual(result.source_indices,(0,3,4))
        self.assertEqual([r['input_index'] for r in result.rows],[0,1,2])
        self.same(self.baseline().analyze_ovf([frames[i] for i in (0,3,4)],self.root/'selected.csv'),result._rows)
        with self.assertRaises(ValueError):analyze(frames,segment='typo')
        with self.assertRaises(ValueError):analyze(frames+[{'A':self.root/'bad.ovf'}],segment='rk4')

    def test_unknown_and_request_errors(self):
        result=analyze([]);self.assertIn('No submitted frames',result.show().data)
        with self.assertRaises(ValueError):analyze([],assume_temporal_sampling='yes')
        with self.assertRaises(ValueError):analyze([],calibration={'bad':True})
        for source in (result.rows,{'A':'x'},[{'valid_pair':True}]):
            with self.assertRaises(TypeError):analyze(source)
        for call in (lambda:result.plot('typo'),lambda:result.table(metrics=['typo']),lambda:result.plot('relative',sublattice='A'),lambda:analyze([],stage='static')):
            with self.assertRaises(ValueError):call()
        damaged=self.root/'bad.state';damaged.write_bytes(b'bad zip')
        with self.assertRaises(zipfile.BadZipFile):analyze(damaged)

    def test_standalone_context_valid_empty_invalid_and_no_reread(self):
        result=analyze(self.frames(),assume_temporal_sampling=True,ab_reference='antiparallel')
        with patch('pathlib.Path.read_bytes',side_effect=AssertionError('No source reread')), patch('fimrun.postprocess.analysis._analyze_rows',side_effect=AssertionError('No reanalysis')):
            for metric in ('center','topology_center','radius','shape','axis','helicity','topology','relative','velocity'):
                svg=result.plot(metric).data
                text=' '.join(ET.fromstring(svg).itertext())
                for fact in ('run=analytic','stage=rk4','segment=rk4','Selected source indices','Valid selected rows','Reasons:','calibration='):
                    self.assertIn(fact,text)
            self.assertIn('no B-pi correction',result.plot('helicity').data)
            self.assertIn('antiparallel; B-pi correction only where valid',result.plot('relative').data)
            self.assertIn('run=analytic',result.show().data)
            result.plot('helicity',output=self.root/'context.svg')
        self.assertIn('segment=rk4',(self.root/'context.svg').read_text())
        missing=analyze([{'A':self.root/'absent.ovf'}])
        text=' '.join(ET.fromstring(missing.plot('radius').data).itertext())
        self.assertIn('run=unknown',text);self.assertIn('0/1',text);self.assertIn('source_or_analysis_error',text)
        empty=' '.join(ET.fromstring(analyze([]).plot('helicity').data).itertext())
        self.assertIn('stage=unknown',empty);self.assertIn('0/0',empty)
        unasserted=analyze(self.frames())
        self.assertIn('unspecified; no corrected phase comparison',unasserted.plot('relative').data)

    def test_unasserted_xy_is_scatter(self):
        result=analyze(self.frames())
        tree=ET.fromstring(result.plot('center',trajectory=True).data)
        ns={'s':'http://www.w3.org/2000/svg'}
        self.assertTrue(tree.findall('.//s:circle',ns))
        self.assertFalse([e for e in tree.findall('.//s:path',ns) if e.get('data-series')])

    def test_missing_time_scatter_full_partial(self):
        for partial in (False,True):
            frames=self.frames(missing_time=True)
            if partial:frames[0]['mapping']={'time_s':0.}
            r=analyze(frames,assume_temporal_sampling=True)
            for metric in ('radius','shape','helicity'):
                svg=r.plot(metric).data;tree=ET.fromstring(svg);ns={'s':'http://www.w3.org/2000/svg'}
                self.assertIn('not physical time',svg)
                self.assertTrue(tree.findall('.//s:circle',ns))
                self.assertFalse([e for e in tree.findall('.//s:path',ns) if e.get('data-series')])
            self.assertFalse(any(row['valid_velocity'] for row in r.rows))

    def state(self, frames, name='candidate.state', latest='rk4'):
        inv={}
        for i,f in enumerate(frames):
            for label in ('A','B'):
                src=Path(f[label]);target=self.root/f'rk4-{i}_{label}.ovf'
                target.write_bytes(src.read_bytes());inv[target.name]=hashlib.sha256(target.read_bytes()).hexdigest()
        data=read_ovf(frames[0]['A'])
        manifest={'schema':'micromagnetics-state-v1','version':1,'run_id':'analytic',
                  'segments':[{'id':latest,'kind':'rk4'}],
                  'model':{'mesh':{'cells':list(data['cells']),'cell_size':data['h'].tolist(),'origin':data['origin'].tolist(),'boundary':'periodic_xy','mirrors':[10,10]},'material':{}},
                  'notebook_flat':{'inventory':inv}}
        path=self.root/name;body=json.dumps(manifest).encode()
        with zipfile.ZipFile(path,'w') as z:
            z.writestr('manifest.json',body);z.writestr('manifest.sha256',hashlib.sha256(body).hexdigest())
        return path

    def test_latest_state(self):
        result=analyze(self.state(self.frames()))
        self.assertEqual(len(result.rows),5)
        self.assertTrue(all(r['valid_pair'] for r in result.rows))

    def test_state_historical_stage_segment_unknown_conflict(self):
        for mode in ('historical-stage','historical-same-stage','unbound','header-conflict','csv-conflict'):
            frames=self.frames()
            p=frames[0]['A'];text=p.read_text()
            if mode=='historical-stage':text=text.replace('stage=rk4','stage=sdesc')
            elif mode=='historical-same-stage':text=text.replace('segment_id=rk4','segment_id=earlier')
            elif mode=='unbound':
                for f in frames:
                    for path in f.values():path.write_text(path.read_text().replace('; segment_id=rk4',''))
                text=p.read_text()
            elif mode=='header-conflict':text=text.replace('run_id=analytic','run_id=foreign')
            p.write_text(text)
            path=self.state(frames,name=mode+'.state')
            if mode=='csv-conflict':
                with zipfile.ZipFile(path) as z:manifest=json.loads(z.read('manifest.json'))
                csvpath=self.root/'scalars.csv';csvpath.write_text('segment_id,step,time_s,stage\nearlier,0,0,rk4\n')
                manifest['notebook_flat']['inventory'][csvpath.name]=hashlib.sha256(csvpath.read_bytes()).hexdigest()
                body=json.dumps(manifest).encode()
                with zipfile.ZipFile(path,'w') as z:z.writestr('manifest.json',body);z.writestr('manifest.sha256',hashlib.sha256(body).hexdigest())
            with self.assertRaises(ValueError,msg=mode):analyze(path,stage='rk4',segment='rk4')

    def test_demo_loop_free_input(self):
        folder=self.root/'demo';rows=generate_demo(folder)
        result=analyze(json.loads((folder/'inputs.json').read_text()),assume_temporal_sampling=True,ab_reference='antiparallel')
        self.same(rows,result._rows)
        with self.assertRaises(TypeError):analyze(rows)
        with self.assertRaises(FileExistsError):generate_demo(folder)
