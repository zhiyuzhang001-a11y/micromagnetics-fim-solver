"""Output lifecycle fault injection. No native engine or numerical integration."""
import csv
from fractions import Fraction
import json
from pathlib import Path
import tempfile
import sysconfig
import unittest
from unittest.mock import patch
import numpy as np
from fimrun.notebook import NotebookSimulation, CellStopped
from fimrun.micromagnetics import Antiparallel, Uniform
from fimrun.micromagnetics.native import Native, EVALUATIONS, ROOT
from fimrun import notebook_flat
import fimrun.postprocess as pp
from fimrun.output_snapshot import frames_from_output
from test_notebook_usability import model


class VisibleOutputs(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name).resolve()
        self.native=patch.object(Native,'__init__',side_effect=AssertionError('Native forbidden'));self.native.start()
        self.identity=patch('fimrun.micromagnetics.persistence.strict_identity',return_value={'test':'zero-native-output-fixture'});self.identity.start()
        payload=ROOT if (ROOT/'build-script-api/libfim.dylib').is_file() else Path(sysconfig.get_path('purelib'))/'fimrun/_runtime'
        self.payload=patch('fimrun.micromagnetics.native.ROOT',payload);self.payload.start()
        self.before=dict(EVALUATIONS)
        self.sim=NotebookSimulation(model=model(),initial=Antiparallel(Uniform((0.,0.,1.))),dt=1e-15,output_dir=self.root)
        self.core=self.sim._session.sim
        self.core._field=np.zeros_like(self.core._m);self.core._energy=np.zeros(2)
    def tearDown(self):
        self.sim.close();self.identity.stop();self.native.stop();self.payload.stop()
        self.assertEqual(self.before,EVALUATIONS);self.temp.cleanup()
    def folders(self):return list(self.root.glob('experiment-running-*'))
    def fake_step(self):
        # Advance only the synthetic fixture clock; no LLG update or evaluation.
        self.core._clock+=Fraction.from_float(self.core.solver.dt)
        self.core._time=float(self.core._clock);self.core.total_steps+=1
    def test_visible_while_running_analyzable_and_legacy_success_paths(self):
        original=self.sim._flat_outputs.observe;seen=[]
        def observe(segment,step,**kw):
            original(segment,step,**kw)
            folder=self.folders()[0]
            if not kw.get('final'):
                progress=json.loads((folder/'progress.json').read_text())
                self.assertEqual(progress['status'],'running')
                self.assertTrue((folder/'experiment.csv').exists())
                self.assertFalse((self.root/'experiment.state').exists())
                results=pp.analyze(folder)
                self.assertTrue(all(r['valid_pair'] for r in results.rows))
                seen.append(len(results.rows))
        with patch.object(self.core,'_rk4_step',side_effect=self.fake_step),patch.object(self.core,'_observe',side_effect=observe):
            self.sim.run(2e-15,save_interval=1e-15)
        self.assertEqual(seen,[1,2,3]);self.assertEqual(self.folders(),[])
        self.assertEqual({p.name for p in self.root.iterdir()},{'experiment.csv','experiment_ovf','experiment.state'})
        self.assertEqual(len(pp.frames_from_state(self.root/'experiment.state')),3)
    def test_state_save_failure_keeps_latest_frames_and_usable_analysis(self):
        with patch.object(self.core,'_rk4_step',side_effect=self.fake_step),patch.object(self.core,'save_state',side_effect=FileNotFoundError('missing cached kernel')):
            with self.assertRaisesRegex(CellStopped,'saved output directory'):self.sim.run(2e-15,save_interval=1e-15)
        folder=self.folders()[0];progress=json.loads((folder/'progress.json').read_text())
        self.assertEqual(progress['status'],'failed');self.assertIn('missing cached kernel',progress['error'])
        self.assertEqual(len(frames_from_output(folder)),3)
        self.assertTrue(all(r['valid_pair'] for r in pp.analyze(folder).rows))
        with (folder/'experiment.csv').open() as stream:
            self.assertEqual(len(list(csv.DictReader(stream))),3)
    def test_partial_pair_never_committed_previous_pairs_survive(self):
        from fimrun.micromagnetics.persistence import export_ovf
        def export(core,paths):
            if core.time>0:
                export_ovf(core,paths)
                paths['B'].unlink()
                raise OSError('B write failed')
            return export_ovf(core,paths)
        with patch.object(self.core,'_rk4_step',side_effect=self.fake_step),patch('fimrun.micromagnetics.persistence.export_ovf',side_effect=export):
            with self.assertRaises(CellStopped):self.sim.run(1e-15,save_interval=1e-15)
        folder=self.folders()[0]
        self.assertEqual(len(frames_from_output(folder)),1)
        self.assertTrue((folder/'experiment.state').exists())
        self.assertTrue(pp.analyze(folder).rows[0]['valid_pair'])
    def test_old_family_survives_publication_failure(self):
        self.sim.run(0.)
        old=notebook_flat.inventory([self.root/'experiment.csv',self.root/'experiment_ovf',self.root/'experiment.state'])
        original=notebook_flat.publish_exclusive
        def fail(src,dst):
            if dst==self.root/'experiment.state':raise OSError('publication failed')
            return original(src,dst)
        with patch('builtins.input',return_value='OVERWRITE'),patch.object(notebook_flat,'publish_exclusive',side_effect=fail):
            with self.assertRaises(CellStopped):self.sim.run(0.)
        self.assertEqual(notebook_flat.inventory([self.root/'experiment.csv',self.root/'experiment_ovf',self.root/'experiment.state']),old)
        folder=self.folders()[0];self.assertTrue(pp.analyze(folder).rows[0]['valid_pair'])
        self.assertEqual(json.loads((folder/'progress.json').read_text())['status'],'failed')
    def test_tampered_committed_frame_rejected(self):
        with patch.object(self.core,'save_state',side_effect=OSError('state failed')):
            with self.assertRaises(CellStopped):self.sim.run(0.)
        folder=self.folders()[0];frame=frames_from_output(folder)[0]
        frame['B'].write_text('corrupted')
        with self.assertRaisesRegex(ValueError,'hash mismatch'):pp.analyze(folder)
    def test_analysis_freezes_manifest_while_progress_advances(self):
        with patch.object(self.core,'save_state',side_effect=OSError('state failed')):
            with self.assertRaises(CellStopped):self.sim.run(0.)
        folder=self.folders()[0]
        from fimrun.postprocess.analysis import _analyze_rows
        def advance(*args,**kwargs):
            path=folder/'progress.json';snapshot=json.loads(path.read_text())
            snapshot['time_s']=99.;path.write_text(json.dumps(snapshot))
            return _analyze_rows(*args,**kwargs)
        with patch('fimrun.postprocess.analysis._analyze_rows',side_effect=advance):
            result=pp.analyze(folder)
        self.assertEqual(result.rows[0]['time_s'],0.)
        self.assertTrue(result.rows[0]['valid_pair'])

    def test_scalar_only_failed_run_preserves_csv_and_reports_no_frames(self):
        with patch.object(self.core,'save_state',side_effect=OSError('state failed')):
            with self.assertRaises(CellStopped):self.sim.run(0.,magnetization=False)
        folder=self.folders()[0];self.assertTrue((folder/'experiment.csv').exists())
        with self.assertRaisesRegex(ValueError,'No complete saved frames'):pp.analyze(folder)

if __name__=='__main__':unittest.main()
