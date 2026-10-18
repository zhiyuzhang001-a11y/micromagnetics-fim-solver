"""Independent zero-field regressions for the three review P1s."""
from pathlib import Path
import hashlib
import json
import tempfile
import unittest
from unittest.mock import patch
import numpy as np
from fimrun.micromagnetics import *
from fimrun.micromagnetics import native


class P1Regression(unittest.TestCase):
    def make(self):
        model=FiM(mesh=Grid(cells=(3,3,1),cell_size=(4e-9,4e-9,3e-9)),
                  material=FiMMaterial(A=Sublattice(Ms=3e5,alpha=.01,gamma_H=2e5),B=Sublattice(Ms=6e5,alpha=.02,gamma_H=2e5)))
        return Simulation(model=model,initial={'A':Uniform((0.,0.,1.)),'B':Uniform((0.,0.,-1.))},solver=RK4(dt=1e-15))

    def test_cancel_stops_all_later_mutations_and_native_work(self):
        sim=self.make()
        before=dict(native.EVALUATIONS)
        try:
            with patch.object(sim,'_current_evaluation',return_value=(np.zeros_like(sim.m),np.zeros(7))),patch.object(sim,'_rk4_step',side_effect=KeyboardInterrupt),patch.object(sim,'set_field') as field,patch.object(sim,'set_current') as current:
                results=sim.execute((Evolve(duration=1e-15),SetField(H_ext=(1.,0.,0.)),SetCurrent(None),Evolve(duration=1e-15)))
            self.assertEqual([r.status for r in results],['cancelled'])
            self.assertEqual(len(sim.segments),1)
            self.assertEqual(sim.last_result.status,'cancelled')
            field.assert_not_called();current.assert_not_called()
            self.assertEqual(native.EVALUATIONS,before)
        finally:sim.close()

    def test_failed_qualification_never_calls_generator_or_reference(self):
        sim=self.make();model=sim.model
        key=native.kernel_key(model)
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);folder=root/'build-script-api/kernel-cache'/hashlib.sha256(json.dumps(key,sort_keys=True).encode()).hexdigest();folder.mkdir(parents=True)
            np.zeros((6,6,6),dtype='<f8').tofile(folder/'kernel.f64')
            meta={'key':key,'sha256':native.sha(folder/'kernel.f64'),'source':'script-api-mpfr128-asym40',
                  'verification':{'passed':False,'engineering_reference_error':1.,'reference_samples':[{'i':0,'j':0,'error':1.,'reference_precision_drift':1.}]}}
            (folder/'manifest.json').write_text(json.dumps(meta))
            with patch.object(native,'ROOT',root),patch.object(native,'kernel_key',return_value=key),patch.object(native.subprocess,'run') as generate:
                with self.assertRaises(ValueError):native.kernel_for(model)
                generate.assert_not_called()
            payload=folder/'kernel.f64'
            mutations=[{}, {'passed':True}, {'passed':False}, {'passed':True,'reciprocity_max':1.}, {'passed':True,'reciprocity_max':float('nan')}]
            for verification in mutations:
                bad={**meta,'verification':verification}
                with patch.object(native,'kernel_key',return_value=key):
                    with self.assertRaises(ValueError):native.validate_qualification(model,payload,bad)
        sim.close()

    def test_static_output_failures_commit_change_once_and_persist(self):
        for failure in ('observe','finish'):
            sim=self.make()
            class Engine:
                def sd_step(self,m,H,prev,grad,controls):return m.copy(),np.zeros_like(m),controls.copy()
            count=[0]
            def residual(m,H):
                count[0]+=1
                return np.array([10.,10.]) if count[0]==1 else np.array([0.,0.])
            real_finish=sim._finish
            finish_count=[0]
            def finish(*args,**kwargs):
                finish_count[0]+=1
                if finish_count[0]==1:raise OSError('injected finish disk failure')
                return real_finish(*args,**kwargs)
            with patch.object(sim,'_current_evaluation',return_value=(np.ones_like(sim.m),np.array([5.,0,0,0,0,0,0]))),patch.object(sim,'_residual',side_effect=residual),patch.object(sim,'_engine',return_value=Engine()),patch.object(sim,'_evaluate',return_value=(np.zeros_like(sim.m),np.array([2.,0,0,0,0,0,0]))):
                target=patch.object(sim,'_observe',side_effect=OSError('injected observe disk failure')) if failure=='observe' else patch.object(sim,'_finish',side_effect=finish)
                with target:
                    with self.assertRaises(OSError):sim.relax(method='sdesc',stop=MaxTransverseField(1.))
            self.assertEqual(sim.last_result.status,'failed')
            self.assertEqual(sim.energy_changes,-3.)
            self.assertEqual(len([e for e in sim.events if e['kind']=='static_change']),1)
            with tempfile.TemporaryDirectory() as temp:
                p=Path(temp)/'failed.state';sim.save_state(p)
                loaded=Simulation.load_state(p)
                self.assertEqual(loaded.energy_changes,-3.)
                self.assertEqual(len([e for e in loaded.events if e['kind']=='static_change']),1)
                loaded.close()
            sim.close()


if __name__=='__main__':unittest.main()
