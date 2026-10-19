"""Isolated tests for the single-object facade; native runs separately budgeted."""
import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import numpy as np
from fimrun.micromagnetics import (Grid, Sublattice, FiM, FiMMaterial, FiMAnisotropy,
    Uniform, Antiparallel, RK4, MaxTransverseField, FiMSOT, Simulation, Outputs)
from fimrun.micromagnetics.native import Native, EVALUATIONS
from fimrun.notebook import NotebookSimulation, NotebookResult, CellStopped, _ACTIVE_NOTEBOOKS


def model():
    sub = Sublattice(Ms=3e5, alpha=.01, gamma_H=2e5)
    return FiM(mesh=Grid(cells=(3,3,1),cell_size=(4e-9,4e-9,3e-9)),
               material=FiMMaterial(A=sub,B=sub),
               energy=(FiMAnisotropy(K1_A=1e4,K1_B=2e4),))


INITIAL = Antiparallel(Uniform((0.,0.,1.)))
SOT = FiMSOT(J=(1e11,0.,0.),xi_A=.1,xi_B=.1)


class ZeroSimple(unittest.TestCase):
    def setUp(self):
        self.before = dict(EVALUATIONS)
        self.temporary = tempfile.TemporaryDirectory()
        self.parent = Path(self.temporary.name)
        self.forbidden = patch.object(Native,'__init__',side_effect=AssertionError('native construction forbidden'))
        self.forbidden.start()

    def tearDown(self):
        for sim in list(_ACTIVE_NOTEBOOKS.values()):
            if sim.directory.is_relative_to(self.parent.resolve()):sim.close()
        self.forbidden.stop()
        self.assertEqual(self.before,EVALUATIONS)
        self.temporary.cleanup()

    def create(self, **kwargs):
        return NotebookSimulation(model=model(),initial=INITIAL,dt=1e-15,results=self.parent,**kwargs)

    def test_duplicate_rejected_before_side_effect_and_close_releases(self):
        sim=self.create();old=sim.m;identity=sim.run_id
        with patch('fimrun.notebook.NotebookSession.start') as start:
            with self.assertRaises(RuntimeError):self.create(replace=False)
            start.assert_not_called()
        with patch('fimrun.notebook.NotebookSession.load') as load:
            with self.assertRaises(RuntimeError):NotebookSimulation.load('missing',results=self.parent,name='experiment')
            load.assert_not_called()
        self.assertEqual(sim.run_id,identity);np.testing.assert_array_equal(sim.m,old)
        with self.assertRaises(RuntimeError):self.create(name='EXPERIMENT',replace=False)
        sim.close();sim.close()
        with self.assertRaises(RuntimeError):sim.run(1e-15)
        with self.assertRaises(RuntimeError):sim.preview()
        fresh=self.create();self.assertNotEqual(fresh.run_id,identity);self.assertEqual(fresh.time,0.)
        self.assertNotEqual(fresh.directory,sim.directory)

    def test_invalid_constructor_no_directory_or_active_name(self):
        for kwargs in ({'dt':0.},{'dt':None},{'dt':True},{'every':1.5e-15},{'snapshots':0.},
                       {'preview':1},{'name':'../escape'},{'initial':'invalid'}):
            with self.subTest(kwargs=kwargs):
                options=dict(model=model(),initial=INITIAL,dt=1e-15,results=self.parent/'unused');options.update(kwargs)
                with self.assertRaises((ValueError,TypeError)):NotebookSimulation(**options)
                self.assertFalse((self.parent/'unused').exists())
        self.create()

    def test_invalid_duration_and_sampling_do_not_mutate_solver_state_or_history(self):
        sim=self.create(every=2e-15,snapshots=2e-15,snapshot_times=(0.,2e-15))
        core=sim._session.sim;history=object();core._sd=history
        before=(sim.dt,sim.time,list(core.events),len(core.segments),len(list(sim.directory.iterdir())))
        for duration,dt in ((-1e-15,2e-15),(None,2e-15),(float('nan'),2e-15),
                            (3e-15,2e-15),(0.,2e-15),(2e-15,1.5e-15),(2e-15,0.)):
            with self.subTest(duration=duration,dt=dt),self.assertRaises((ValueError,TypeError)):
                sim.run(duration,dt=dt)
            self.assertEqual((sim.dt,sim.time,list(core.events),len(core.segments),len(list(sim.directory.iterdir()))),before)
            self.assertIs(core._sd,history)
        core._sd=None

    def test_current_requires_explicit_disable_for_relax_and_readonly_copies(self):
        sim=self.create();before=sim.m
        sim.set_current(SOT)
        with self.assertRaises(ValueError):sim.relax(1.)
        self.assertEqual(sim._session.sim.current,SOT);self.assertFalse(sim._session.sim.segments)
        for tolerance in (0.,-1.,None):
            with self.assertRaises((ValueError,TypeError)):sim.relax(tolerance)
        sim.set_current(None)
        np.testing.assert_array_equal(sim.m,before)
        copy=sim.m;copy[:]=0.;np.testing.assert_array_equal(sim.m,before)
        copy=sim.dissipation;copy[:]=1.;np.testing.assert_array_equal(sim.dissipation,[0.,0.])
        copy=sim.drive_work;copy[:]=1.;np.testing.assert_array_equal(sim.drive_work,[0.,0.])
        for name in ('m','time','dt','dissipation','drive_work'):
            with self.assertRaises(AttributeError):setattr(sim,name,None)

    def test_safe_save_load_settings_and_closed_preview(self):
        def start(display, *, open_browser=True):display.server=object()
        def close(display):display.server=None
        with patch('fimrun.micromagnetics.preview.LivePreview.start',start),patch('fimrun.micromagnetics.preview.LivePreview.close',close):
            sim=self.create(every=2e-15,snapshots=2e-15,preview=True,preview_port=8971)
            display=sim._session.sim._preview
            self.assertIsNotNone(display.server)
            saved=sim.save('initial.state');content=Path(saved['path']).read_bytes()
            for name in ('initial.state','../bad.state','/tmp/bad.state','states/file'):
                with self.assertRaises((ValueError,FileExistsError)):sim.save(name)
            self.assertEqual(content,Path(saved['path']).read_bytes())
            sim.close();self.assertIsNone(display.server)
            restored=NotebookSimulation.load(saved['path'],results=self.parent,name='experiment')
            self.assertNotEqual(restored.directory,sim.directory)
            self.assertEqual(restored.dt,sim.dt)
            outputs=restored._session.sim.outputs
            self.assertEqual((outputs.every,outputs.snapshots,outputs.preview,outputs.preview_port),(2e-15,2e-15,True,8971))
            self.assertIsNotNone(restored._session.sim._preview.server)
            np.testing.assert_array_equal(restored.m,sim.m)
            strict=restored.save('initial.checkpoint',checkpoint=True);restored.close()
            locked=NotebookSimulation.load(strict['path'],results=self.parent,checkpoint=True)
            with self.assertRaises(ValueError):locked.run(2e-15,dt=2e-15)
            self.assertEqual(locked.dt,1e-15)
            with self.assertRaises(ValueError):locked.set_current(SOT)
            locked.close()

    def test_cancelled_and_failed_raise_at_call_even_if_result_not_displayed(self):
        sim=self.create();core=sim._session.sim;actions=[]
        with patch.object(core,'_current_evaluation',side_effect=KeyboardInterrupt),contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaises(CellStopped):
                result=sim.run(1e-15)
                actions.append('queued')
        self.assertEqual(actions,[]);self.assertEqual(core.last_result.status,'cancelled');self.assertFalse(core._busy)
        with patch.object(core,'_current_evaluation',side_effect=RuntimeError('injected field failure')),contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaises(CellStopped) as caught:
                result=sim.run(1e-15)
                actions.append('queued')
        self.assertIsInstance(caught.exception.__cause__,RuntimeError)
        self.assertEqual(core.last_result.status,'failed');self.assertFalse(core._busy)
        self.assertEqual(actions,[]);self.assertEqual(sim.time,0.)
        # Static cancellation follows the same call-time contract.
        with patch.object(core,'_current_evaluation',side_effect=KeyboardInterrupt),contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaises(CellStopped):sim.relax(1.)
        self.assertEqual(core.last_result.status,'cancelled')


class FiniteSimple(unittest.TestCase):
    """Budget enforced by the external runner before every Native.evaluate."""
    def equal(self, new, old):
        np.testing.assert_array_equal(new.m,old.m)
        np.testing.assert_array_equal(new.dissipation,old.dissipation)
        np.testing.assert_array_equal(new.drive_work,old.drive_work)
        self.assertEqual(new.time,old.time)
        self.assertEqual(new.metrics()['fields'],old.metrics()['fields'])

    def test_old_new_exact_dynamic_static_dynamic_dt_and_restore(self):
        with tempfile.TemporaryDirectory() as folder:
            parent=Path(folder)
            new=NotebookSimulation(model=model(),initial=INITIAL,dt=1e-15,results=parent,
                                   every=2e-15,snapshots=2e-15,scalars=('time','mean_m'))
            old=Simulation(model=model(),initial=INITIAL,solver=RK4(dt=1e-15),
                           outputs=Outputs(directory=parent/'old',every=2e-15,snapshots=2e-15,scalars=('time','mean_m')))
            loaded=locked=None
            try:
                identity=new.run_id
                result=new.run(2e-15);old.run(duration=2e-15);self.equal(new,old)
                self.assertIsInstance(result,NotebookResult);self.assertEqual(result.accepted_steps,2)
                self.assertIn('completed',repr(result))
                with self.assertRaises(AttributeError):result.status='failed'
                # Large consecutive count is unnecessary: this aligned case is already stationary.
                before=new.time;new.relax(1.);old.relax(method='sdesc',stop=MaxTransverseField(1.))
                self.equal(new,old);self.assertEqual(new.time,before)
                new.set_current(SOT);old.set_current(SOT)
                new.run(2e-15,dt=2e-15);old.set_solver(RK4(dt=2e-15));old.run(duration=2e-15);self.equal(new,old)
                new.run(2e-15);old.run(duration=2e-15);self.equal(new,old)
                self.assertEqual(new.run_id,identity);self.assertEqual(new.dt,2e-15)
                # Scalar and snapshot intervals survived all operations/dt changes.
                a=new.directory/'trajectory';b=parent/'old'
                for segment in sorted(a.glob('segment-*')):
                    other=b/segment.name
                    snapshots=sorted(p.name for p in segment.glob('m-*.npz'))
                    self.assertEqual(snapshots,sorted(p.name for p in other.glob('m-*.npz')))
                    for name in snapshots:
                        with np.load(segment/name) as x,np.load(other/name) as y:
                            for key in x.files:np.testing.assert_array_equal(x[key],y[key])
                saved=new.save('accepted.state');new.close()
                loaded=NotebookSimulation.load(saved['path'],results=parent)
                baseline=Simulation.load_state(saved['path'],outputs=Outputs(directory=parent/'loaded-old',every=2e-15,snapshots=2e-15,scalars=('time','mean_m')))
                try:
                    self.equal(loaded,baseline)
                    loaded.run(2e-15);baseline.run(duration=2e-15);self.equal(loaded,baseline)
                finally:baseline.close()
                checkpoint=loaded.save('accepted.checkpoint',checkpoint=True);loaded.close()
                locked=NotebookSimulation.load(checkpoint['path'],results=parent,name='strict',checkpoint=True)
                baseline=Simulation.resume_checkpoint(checkpoint['path'],outputs=Outputs(directory=parent/'strict-old',every=2e-15,snapshots=2e-15,scalars=('time','mean_m')))
                try:
                    locked.run(2e-15);baseline.run(duration=2e-15);self.equal(locked,baseline)
                finally:baseline.close()
            finally:
                new.close();old.close()
                if loaded:loaded.close()
                if locked:locked.close()
