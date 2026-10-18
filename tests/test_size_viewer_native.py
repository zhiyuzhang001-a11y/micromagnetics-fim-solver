"""Finite native runner and preview invariance; no long daily workflow."""
from pathlib import Path
import contextlib
import io
import tempfile
import unittest
from unittest.mock import patch
import urllib.request
import json
import numpy as np
from fimrun.micromagnetics import *
from fimrun.micromagnetics.native import EVALUATIONS


class NativeRevision(unittest.TestCase):
    def models(self):
        grid=Grid(size=(12e-9,12e-9,3e-9),cell_size=(4e-9,4e-9,3e-9))
        a=Sublattice(Ms=3e5,alpha=.01,gamma_H=2e5)
        return (FM(mesh=grid,material=FMMaterial(Ms=8e5,alpha=.02,gamma_H=2e5),energy=(Zeeman(H_ext=(100.,0.,10.)),)),
                FiM(mesh=grid,material=FiMMaterial(A=a,B=a),energy=(FiMAnisotropy(K1_A=1e4,K1_B=2e4),)))

    def test_real_explicit_runner_and_saves(self):
        model=self.models()[1]
        initial={'A':Uniform((.1,0.,1.),normalize=True),'B':Uniform((0.,.1,-1.),normalize=True)}
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)/'run'
            stages=(Evolve(duration=1e-15),Relax(stop=MaxTransverseField(1.)),SaveState(root/'prepared.state'),
                    SetOutputs(Outputs(directory=root)),SetSolver(RK4(dt=.5e-15)),
                    SetCurrent(FiMSOT(J=(1e11,0.,0.),xi_A=.1,xi_B=.1)),Evolve(duration=1e-15),
                    SaveState(root/'final.state'),SaveState(root/'final.checkpoint',strict=True))
            with contextlib.redirect_stdout(io.StringIO()):
                code=run_script(model=model,initial=initial,solver=RK4(dt=1e-15),outputs=Outputs(directory=root),stages=stages,argv=[])
            self.assertEqual(code,0)
            prepared=Simulation.load_state(root/'prepared.state');final=Simulation.load_state(root/'final.state');strict=Simulation.resume_checkpoint(root/'final.checkpoint')
            try:
                self.assertEqual(prepared.time,1e-15);self.assertEqual(final.time,2e-15)
                np.testing.assert_array_equal(final.m,strict.m)
                self.assertIsNotNone(final.current)
                self.assertFalse(list(root.rglob('*.npz')))
            finally:prepared.close();final.close();strict.close()

    def test_preview_on_off_exact_and_HTTP_zero_fields(self):
        for model in self.models():
            initial=Uniform((.1,.2,1.),normalize=True)
            if isinstance(model,FiM):initial={'A':initial,'B':Uniform((.2,0.,-1.),normalize=True)}
            states=[]
            for enabled in (False,True):
                sim=Simulation(model=model,initial=initial,solver=RK4(dt=1e-15),outputs=Outputs(preview=enabled,preview_port=18787))
                try:
                    with patch('fimrun.micromagnetics.preview.webbrowser.open') as browser:
                        sim.run(duration=3e-15)
                    states.append((sim.m,sim.dissipation.copy(),sim.drive_work.copy(),sim.time,sim.metrics()['fields']))
                    if enabled:
                        browser.assert_called_once()
                        before=dict(EVALUATIONS)
                        with urllib.request.urlopen(sim._preview.url.replace('/?','/api/state?')) as response:state=json.load(response)
                        with urllib.request.urlopen(sim._preview.url.replace('/?','/api/state?')) as response:json.load(response)
                        self.assertEqual(EVALUATIONS,before)
                        self.assertEqual(state['data']['labels'],list(model.labels))
                        self.assertEqual(sim.metrics()['analysis_calls'],0)
                        self.assertEqual(sim.metrics()['snapshot_writes'],0)
                        self.assertIsNone(sim._root)
                finally:sim.close()
            for a,b in zip(states[0][:3],states[1][:3]):np.testing.assert_array_equal(a,b)
            self.assertEqual(states[0][3:],states[1][3:])


if __name__=='__main__':unittest.main()
