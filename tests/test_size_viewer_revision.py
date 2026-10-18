"""Zero-field interface/source regressions for the size and unified viewer revision."""
from dataclasses import asdict, replace
from pathlib import Path
import contextlib
import io
import math
import tempfile
import threading
import unittest
from unittest.mock import patch
import numpy as np
from fimrun.micromagnetics import *
from fimrun.micromagnetics.preview import LivePreview, IDENTITY
from fimrun.micromagnetics.native import Native, EVALUATIONS, kernel_key


class Revision(unittest.TestCase):
    def make(self, fim=True):
        grid=Grid(size=(12e-9,12e-9,3e-9),cell_size=(4e-9,4e-9,3e-9))
        material=Sublattice(Ms=3e5,alpha=.01,gamma_H=2e5)
        model=FiM(mesh=grid,material=FiMMaterial(A=material,B=replace(material,Ms=6e5))) if fim else FM(mesh=grid,material=FMMaterial(Ms=3e5,alpha=.01,gamma_H=2e5))
        initial={'A':Uniform((1.,0.,0.)), 'B':Uniform((0.,1.,0.))} if fim else Uniform((1.,0.,0.))
        return Simulation(model=model,initial=initial,solver=RK4(dt=1e-15))

    def test_size_normalization_and_old_state(self):
        a=Grid(size=(500e-9,500e-9,3e-9),cell_size=(4e-9,4e-9,3e-9))
        b=Grid(cells=(125,125,1),cell_size=(4e-9,4e-9,3e-9))
        self.assertEqual(a,b);self.assertEqual(asdict(a),asdict(b))
        for kwargs in ({'size':(11e-9,12e-9,3e-9)}, {'size':(12e-9,12e-9,6e-9)}, {'size':(0,12e-9,3e-9)}, {'size':(12e-9,12e-9,3e-9),'cells':(3,3,1)}, {}):
            with self.assertRaises(ValueError):Grid(cell_size=(4e-9,4e-9,3e-9),**kwargs)
        near=Grid(size=(math.nextafter(12e-9,math.inf),12e-9,3e-9),cell_size=(4e-9,4e-9,3e-9))
        self.assertEqual(near.cells,(3,3,1))
        sim=self.make()
        try:
            child=sim.branch(name='same-grid',model=replace(sim.model,mesh=Grid(cells=(3,3,1),cell_size=(4e-9,4e-9,3e-9))))
            self.assertEqual(child.events[-1]['cumulative_baseline'],'inherited');child.close()
            with tempfile.TemporaryDirectory() as temp:
                path=Path(temp)/'size.state';sim.save_state(path)
                loaded=Simulation.load_state(path)
                self.assertEqual(loaded.model.mesh.requested_size,sim.model.mesh.requested_size);loaded.close()
        finally:sim.close()

    def test_preflight_and_cancel_without_native(self):
        sim=self.make()
        try:
            with patch.object(Native,'__init__',side_effect=AssertionError('unexpected native work')):
                with contextlib.redirect_stdout(io.StringIO()):
                    result=run_script(model=sim.model,initial=dict(zip(sim.labels,sim.m)),solver=sim.solver,
                                      stages=(Evolve(duration=2e-15),Relax(stop=MaxTransverseField(1.))),argv=['--check'])
                self.assertEqual(result,0)
                with self.assertRaises(ValueError):
                    check_stages(sim,(Evolve(duration=1e-15),SetSolver(RK4(dt=2e-15)),Evolve(duration=1e-15)))
                with tempfile.TemporaryDirectory() as temp:
                    path=Path(temp)/'must-not-exist.state'
                    cancelled=RunResult('cancelled',0.,0.,0,None,'cancelled','test')
                    with patch.object(Simulation,'run',return_value=cancelled),patch.object(Simulation,'set_current') as current,contextlib.redirect_stdout(io.StringIO()):
                        result=run_script(model=sim.model,initial=dict(zip(sim.labels,sim.m)),solver=sim.solver,
                                          stages=(Evolve(duration=1e-15),SaveState(path),SetCurrent(None)),argv=[])
                    self.assertEqual(result,130);self.assertFalse(path.exists())
                    # One preflight mutation is permitted; execution stops before the second.
                    self.assertEqual(current.call_count,1)
        finally:sim.close()

    def test_atomic_bounded_packets_identity_and_real_field_count(self):
        before=dict(EVALUATIONS)
        for fim in (False,True):
            sim=self.make(fim=fim);source=LivePreview(sim,18788)
            try:
                query={'run_id':[sim.run_id],'instance':[source.instance]}
                source.publish(force=True)
                state,_=source.response('/api/state',query)
                frameq={**query,**{k:[str(state[k])] for k in IDENTITY},'step':[str(state['data']['frame_seq'])],'stride':['1']}
                source.publish(force=True)
                frame,_=source.response('/api/frame',frameq)
                self.assertEqual(len(frame['vectors']),2 if fim else 1)
                self.assertEqual(frame['vectors'][0][0],[1.,0.,0.])
                if fim:self.assertEqual(frame['vectors'][1][0],[0.,1.,0.])
                with self.assertRaises(ValueError):source.response('/api/state',{**query,'instance':['wrong']})
                for _ in range(20):source.publish(force=True)
                self.assertLessEqual(len(source.frames),16)
                with self.assertRaises(ValueError):source.response('/api/frame',frameq)
                current,_=source.response('/api/state',query)
                previous_epoch=current['stage_epoch']
                sim._begin('sdesc');sim._preview_stop={'tolerance':1.,'consecutive':2};source.publish(force=True)
                current,_=source.response('/api/state',query)
                self.assertGreater(current['stage_epoch'],previous_epoch)
                self.assertIsNone(current['data']['target_steps']);self.assertIsNone(current['data']['time_ps'])
                self.assertEqual(len(source.frames),1)
                with self.assertRaises(ValueError):source.response('/api/frame',frameq)
                snap=source.latest['m'].copy();sim._m=np.roll(sim._m,1,axis=-1)
                np.testing.assert_array_equal(source.latest['m'],snap)
                with patch.object(sim,'_current_evaluation',side_effect=AssertionError('HTTP requested physics')):
                    source.response('/api/state',query)
                sim._busy=False
            finally:sim.close()
        self.assertEqual(EVALUATIONS,before)

    def test_concurrent_packets_and_browser_failure_are_not_physics(self):
        sim=self.make();source=LivePreview(sim,18786)
        query={'run_id':[sim.run_id],'instance':[source.instance]}
        source.publish(force=True)
        errors=[]
        def writer():
            for step in range(50):
                value=np.zeros_like(sim.m);value[0,...,step%2]=1.;value[1,...,2]=1.
                sim._m=value;sim._active_steps=step
                source.publish(force=True)
        worker=threading.Thread(target=writer);worker.start()
        for _ in range(50):
            state,_=source.response('/api/state',query)
            request={**query,**{k:[str(state[k])] for k in IDENTITY},'step':[str(state['data']['frame_seq'])]}
            try:
                frame,_=source.response('/api/frame',request)
                self.assertEqual(frame['vectors'][1][0],[0.,0.,1.])
                expected=[0.,0.,0.];expected[frame['step']%2]=1.
                self.assertEqual(frame['vectors'][0][0],expected)
            except ValueError:pass
        worker.join()
        state,_=source.response('/api/state',query)
        request={**query,**{k:[str(state[k])] for k in IDENTITY},'step':[str(state['data']['frame_seq'])]}
        source.response('/api/frame',request)
        self.assertLessEqual(len(source.frame_cache),2)
        with patch('fimrun.micromagnetics.preview.ThreadingHTTPServer') as server,patch('fimrun.micromagnetics.preview.webbrowser.open',side_effect=RuntimeError('browser failed')):
            with self.assertWarns(RuntimeWarning):source.start()
            server.return_value.server_close.assert_called_once()
            self.assertIsNone(source.server)
        sim.close()


if __name__=='__main__':unittest.main()
