"""Focused regression for flat Notebook output safety, accepted-state gates and UI."""
import copy
import csv
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace
import numpy as np
from fimrun.notebook import NotebookSimulation, CellStopped, _ACTIVE_NOTEBOOKS
from fimrun import notebook_flat
from fimrun.micromagnetics import *
from fimrun.micromagnetics.simulation import ResidualAndMxh
from fimrun.micromagnetics.preview import LivePreview
from fimrun.micromagnetics.native import EVALUATIONS


def model():
    return FiM(mesh=Grid(cells=(3,3,1),cell_size=(4e-9,4e-9,3e-9)),
        material=FiMMaterial(A=Sublattice(Ms=3e5,alpha=.01,gamma_H=2e5),
                            B=Sublattice(Ms=6e5,alpha=.01,gamma_H=2e5)),
        energy=(FiMAnisotropy(K1_A=1e4,K1_B=2e4),))


class Usability(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name).resolve()
    def tearDown(self):
        for sim in list(_ACTIVE_NOTEBOOKS.values()):
            if sim.directory.is_relative_to(self.root):sim.close()
        self.temp.cleanup()
    def create(self,**kw):
        options=dict(model=model(),initial=Antiparallel(Uniform((0.,0.,1.))),dt=1e-15,output_dir=self.root)
        options.update(kw);return NotebookSimulation(**options)
    def frozen(self,sim):
        core=sim._session.sim
        return (sim.m.tobytes(),sim.time,sim.dt,sim.dissipation.tobytes(),sim.drive_work.tobytes(),
                copy.deepcopy(core.events),copy.deepcopy(core.segments),copy.deepcopy(sim._flat_outputs.settings),
                copy.deepcopy(sim._flat_outputs.cadences),dict(EVALUATIONS),notebook_flat.inventory(list(self.root.iterdir())))
    def test_trio_cadence_continuation_and_restore(self):
        sim=self.create();sim.run(2e-15,every=1e-15,scalars=('time','mean_m','residual','mxh'))
        self.assertEqual({p.name for p in self.root.iterdir()},{'experiment.csv','experiment_ovf','experiment.state'})
        rows=list(csv.DictReader((self.root/'experiment.csv').open()));self.assertEqual(len(rows),3)
        self.assertEqual(len(list((self.root/'experiment_ovf').glob('*.ovf'))),6)
        self.assertIn('mxh_B',rows[-1]);before=sim.m.copy();clock=sim.time
        sim.relax(mxh=1e-5,output_name='static',every=1)
        self.assertEqual(sim.time,clock);np.testing.assert_array_equal(before,sim.m)
        restored=NotebookSimulation.load(self.root/'static.state',output_dir=self.root/'restored')
        np.testing.assert_array_equal(restored.m,sim.m);self.assertEqual(restored.dt,sim.dt)
        restored.run(1e-15,output_name='next',magnetization=False,scalars=())
        self.assertEqual({p.name for p in (self.root/'restored').iterdir()},{'next.state'})
        restored.close()
    def test_declined_overwrite_has_zero_side_effects(self):
        sim=self.create();sim.run(0.)
        before=self.frozen(sim)
        with patch('builtins.input',return_value='no'):
            with self.assertRaisesRegex(CellStopped,'declined'):
                sim.run(2e-15,dt=2e-15,every=None,scalars=(),magnetization=False)
        self.assertEqual(self.frozen(sim),before)
    def test_confirmed_overwrite_removes_owned_old_frames_only(self):
        sim=self.create();sim.run(2e-15,every=1e-15)
        unrelated=self.root/'other.txt';unrelated.write_text('keep')
        with patch('builtins.input',return_value='OVERWRITE'):sim.run(1e-15,every=None)
        self.assertEqual(len(list((self.root/'experiment_ovf').glob('*.ovf'))),2)
        self.assertEqual(len(list(csv.DictReader((self.root/'experiment.csv').open()))),1)
        self.assertEqual(unrelated.read_text(),'keep');self.assertEqual(sim.time,3*1e-15)
    def test_foreign_symlinks_and_invalid_settings_precede_fields(self):
        sim=self.create();core=sim._session.sim;before=(sim.m.tobytes(),sim.dt,dict(EVALUATIONS))
        (self.root/'foreign.csv').write_text('foreign')
        for options in (dict(output_name='foreign'),dict(output_name='../escape'),dict(every=1.5e-15),dict(scalars=['time'])):
            with self.subTest(options=options),self.assertRaises((ValueError,TypeError)):
                sim.run(2e-15,**options)
        (self.root/'link.state').symlink_to(self.root/'foreign.csv')
        with self.assertRaises(ValueError):sim.run(1e-15,output_name='link')
        with self.assertRaises(ValueError):sim.relax(mxh=1e-5,every=1e-12)
        with self.assertRaises(TypeError):sim.relax(1.)
        with self.assertRaises(TypeError):sim.relax(tolerance=1.)
        self.assertEqual((sim.m.tobytes(),sim.dt,dict(EVALUATIONS)),before);self.assertEqual(core.segments,[])
    def test_modified_family_never_offers_overwrite(self):
        sim=self.create();sim.run(0.)
        (self.root/'experiment_ovf'/'user.txt').write_text('preserve')
        before=dict(EVALUATIONS)
        with patch('builtins.input') as ask,self.assertRaisesRegex(ValueError,'foreign'):
            sim.run(1e-15)
        ask.assert_not_called();self.assertEqual(before,EVALUATIONS)
    def test_publication_failure_rolls_back_old_and_preserves_new(self):
        sim=self.create();sim.run(0.);old={p.name:p.read_bytes() for p in self.root.iterdir() if p.is_file()}
        original=notebook_flat.os.link
        def fail(src,dst):
            if Path(dst)==self.root/'experiment.state':raise OSError('injected publication fault')
            return original(src,dst)
        with patch('builtins.input',return_value='OVERWRITE'),patch.object(notebook_flat.os,'link',side_effect=fail):
            with self.assertRaises(CellStopped):sim.run(1e-15)
        for n,data in old.items():self.assertEqual((self.root/n).read_bytes(),data)
        recovery=[p for p in self.root.iterdir() if p.is_dir() and p.name.startswith('.experiment-')]
        self.assertEqual(len(recovery),1);self.assertTrue((recovery[0]/'experiment.state').is_file())
        recovered=Simulation.load_state(recovery[0]/'experiment.state');self.assertEqual(recovered.time,sim.time);recovered.close()
    def test_final_ovf_failure_keeps_accepted_state(self):
        sim=self.create()
        with patch('fimrun.micromagnetics.persistence.export_ovf',side_effect=OSError('injected write failure')):
            with self.assertRaises(CellStopped):sim.run(1e-15)
        recovery=list(self.root.glob('.experiment-*/experiment.state'))
        self.assertEqual(len(recovery),1)
        restored=Simulation.load_state(recovery[0]);self.assertEqual(restored.time,sim.time);restored.close()
    def test_manual_state_retains_output_policy_without_fields(self):
        sim=self.create(every=2e-15,scalars=('time','mxh'),magnetization=False)
        before=dict(EVALUATIONS);saved=sim.save('manual.state')
        restored=NotebookSimulation.load(saved['path'],output_dir=self.root/'manual_restore')
        self.assertEqual(restored._flat_outputs.cadences,{'rk4':2e-15,'sdesc':None})
        self.assertEqual(restored._flat_outputs.settings['scalars'],('time','mxh'))
        self.assertFalse(restored._flat_outputs.settings['magnetization'])
        self.assertEqual(before,EVALUATIONS);restored.close()
    def test_competing_destination_is_not_replaced(self):
        sim=self.create();sim.run(0.);old=(self.root/'experiment.state').read_bytes()
        original=notebook_flat.publish_exclusive
        def competitor(src,dst):
            if dst==self.root/'experiment.state':dst.write_text('competing user file')
            return original(src,dst)
        with patch('builtins.input',return_value='OVERWRITE'),patch.object(notebook_flat,'publish_exclusive',side_effect=competitor):
            with self.assertRaises(CellStopped):sim.run(0.)
        self.assertEqual((self.root/'experiment.state').read_text(),'competing user file')
        recovery=list(self.root.glob('.experiment-*/previous/experiment.state'))
        self.assertEqual(len(recovery),1);self.assertEqual(recovery[0].read_bytes(),old)
    def test_four_gates_use_each_ms_and_minimum(self):
        stop=ResidualAndMxh(tolerance=1.,mxh=1e-6,consecutive=2)
        self.assertTrue(stop.satisfied(np.array([.29,.59]),model()))
        self.assertFalse(stop.satisfied(np.array([.31,.59]),model()))
        self.assertFalse(stop.satisfied(np.array([.29,.61]),model()))
        physical=ResidualAndMxh(tolerance=1.,mxh=1e-5)
        self.assertFalse(physical.satisfied(np.array([1.01,.5]),model()))
        self.assertFalse(physical.satisfied(np.array([.5,1.01]),model()))
    def test_static_iterations_consecutive_and_cancelled_final(self):
        sim=self.create();core=sim._session.sim;shape=core._m.shape
        H=np.zeros(shape);energy=np.zeros(2)
        original=core._m.copy()
        def sd(m,H,prev,gradient,controls):
            c=m.copy();c[...,0]*=-1
            return c,np.zeros_like(m),np.zeros(5)
        engine=SimpleNamespace(sd_step=sd)
        core._field=H;core._energy=energy
        # Deterministic accepted states, no native evaluation: initial qualifies,
        # next fails B, then two distinct states qualify. Refresh does not count.
        residuals=iter(([0.,0.],[0.,2.],[0.,0.],[0.,0.]))
        with patch.object(core,'_engine',return_value=engine),patch.object(core,'_evaluate',return_value=(H,energy)),patch.object(core,'_residual',side_effect=lambda m,H:np.array(next(residuals))):
            sim.relax(mxh=1e-5,residual=1.,consecutive=2,every=1,scalars=('time',),magnetization=False)
        self.assertEqual(core.last_result.steps,3);self.assertEqual(core._sd['consecutive'],2);self.assertEqual(sim.time,0.)
        rows=list(csv.DictReader((self.root/'experiment.csv').open()));self.assertEqual([int(r['iteration']) for r in rows],[0,1,2,3])
        # Interrupt before a candidate commit; final accepted state still output.
        with patch.object(core,'_engine',return_value=SimpleNamespace(sd_step=lambda *a:(_ for _ in ()).throw(KeyboardInterrupt()))),patch.object(core,'_residual',return_value=np.array([2.,2.])):
            with self.assertRaises(CellStopped):sim.relax(mxh=1e-6,output_name='cancelled',scalars=('time',),magnetization=False)
        final=list(csv.DictReader((self.root/'cancelled.csv').open()))[-1];self.assertEqual(final['status'],'cancelled')
        self.assertEqual(core._sd['consecutive'],0)
    def test_preview_cache_and_rebind_reject_old_identity(self):
        sim=self.create();core=sim._session.sim;view=LivePreview(core,18799);view.publish(force=True)
        self.assertIsNone(view.latest['state']['convergence'][0]['mxh'])
        before=dict(EVALUATIONS)
        query={'run_id':[sim.run_id],'instance':[view.instance]}
        state,_=view.response('/api/state',query)
        frame_query={k:[str(v)] for k,v in view.latest['identity'].items()};frame_query['stride']=['1']
        view.response('/api/frame',frame_query)
        other=self.create(initial=Antiparallel(Uniform((1.,0.,0.))))
        view.rebind(other._session.sim)
        with self.assertRaises(ValueError):view.response('/api/state',query)
        with self.assertRaises(ValueError):view.response('/api/frame',frame_query)
        bound,_=view.response('/api/binding',{'instance':[view.instance]});self.assertEqual(bound['run_id'],other.run_id)
        self.assertEqual(before,EVALUATIONS)
    def test_rebind_display_failure_keeps_new_scientific_object(self):
        def start(view):view.server=object()
        def close(view):view.server=None
        with patch.object(LivePreview,'start',start),patch.object(LivePreview,'close',close):
            old=self.create(preview=True)
            before=dict(EVALUATIONS)
            with patch.object(LivePreview,'rebind',side_effect=ValueError('injected display failure')):
                with self.assertWarnsRegex(RuntimeWarning,'reset completed'):
                    new=self.create(preview=True,initial=Antiparallel(Uniform((1.,0.,0.))))
            self.assertTrue(old.closed);self.assertFalse(new.closed)
            self.assertEqual(new.time,0.);self.assertIsNone(new._session.sim._preview)
            self.assertEqual(before,EVALUATIONS)
    def test_strict_combo_checkpoint_roundtrip(self):
        sim=self.create();sim.relax(mxh=1e-5,consecutive=1,magnetization=False)
        path=self.root/'strict.state';sim._session.sim.save_checkpoint(path)
        restored=Simulation.resume_checkpoint(path)
        self.assertEqual(restored._sd['criterion']['mxh'],1e-5)
        with self.assertRaises(ValueError):restored.relax(method='sdesc',stop=ResidualAndMxh(tolerance=1.,mxh=1e-6))
        restored.close()
