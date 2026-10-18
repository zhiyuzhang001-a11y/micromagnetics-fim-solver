"""Finite developer acceptance cases; production operations contain no test budgets."""
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from dataclasses import replace
from unittest.mock import patch
import numpy as np
from fimrun.micromagnetics import *
from fimrun.micromagnetics.native import EVALUATIONS


CHILD_FIELDS = {'fm': 0, 'fim': 0}


class InterfaceAcceptance(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.live = []

    def tearDown(self):
        for sim in self.live:
            sim.close()
        self.tmp.cleanup()

    def fm(self, *, energy=(), outputs=None, initial=None):
        model = FM(mesh=Grid(cells=(2, 2, 1), cell_size=(4e-9, 4e-9, 3e-9)),
                   material=FMMaterial(Ms=8e5, alpha=.02, gamma_H=221088.4), energy=energy)
        sim = Simulation(model=model, initial=initial if initial is not None else Uniform((1., .03, .02), normalize=True),
                         solver=RK4(dt=1e-15), outputs=outputs)
        self.live.append(sim)
        return sim

    def fim(self, *, energy=(), outputs=None, initial=None):
        model = FiM(mesh=Grid(cells=(3, 3, 1), cell_size=(4e-9, 4e-9, 3e-9)),
                    material=FiMMaterial(A=Sublattice(Ms=3e5, alpha=.01, gamma_H=221276.1569),
                                         B=Sublattice(Ms=6e5, alpha=.02, gamma_H=221276.1569)), energy=energy)
        initial = initial if initial is not None else {'A': Uniform((.1, .02, 1.), normalize=True), 'B': Uniform((.02, -.1, -1.), normalize=True)}
        sim = Simulation(model=model, initial=initial, solver=RK4(dt=1e-15), outputs=outputs)
        self.live.append(sim)
        return sim

    def test_01_models_defaults_and_legal_nonequilibrium(self):
        a = self.fm()
        b = self.fim()
        self.assertEqual(a.m.shape, (1, 1, 2, 2, 3))
        self.assertEqual(b.m.shape, (2, 1, 3, 3, 3))
        self.assertFalse(np.array_equal(b.m[0], -b.m[1]))
        for sim in (a, b):
            self.assertEqual(sim.metrics()['fields'], 0)
            self.assertEqual(sim.run(duration=2e-15).status, 'completed')
            self.assertEqual(sim.metrics()['subfields'], len(sim.labels))
            self.assertEqual(sim.metrics()['fft_transforms'], 0)
            self.assertEqual(sim.metrics()['analysis_calls'], 0)
            self.assertEqual(sim.metrics()['preview_starts'], 0)
            self.assertEqual(sim.metrics()['snapshot_writes'], 0)
            self.assertIsNone(sim.describe()['resource_budgets'])
        with self.assertRaises(TypeError):
            FMMaterial(Ms=8e5, alpha=.01, gamma_H=2e5, B=0.)
        with self.assertRaises(ValueError):
            Sublattice(Ms=0., alpha=.01, gamma_H=2e5)
        with self.assertRaises(TypeError):
            replace(a.model, energy=(DMI(D_A=.001, D_B=.001),))
        with self.assertRaises(TypeError):
            a.set_current(FiMSOT(J=(1e11, 0., 0.), xi_A=.1, xi_B=.1))
        with self.assertRaises(NotImplementedError):
            a.relax(method='sdesc', stop=MaxTransverseField(1.))
        with self.assertRaises(ValueError):
            a.run(duration=1.5e-15)
        with self.assertRaises(ValueError):
            Simulation(model=b.model, initial={'A': b.m[0]}, solver=b.solver)

    def test_02_one_field_zeeman_and_full_volume_energy(self):
        sim = self.fm(energy=(Zeeman(H_ext=(0., 0., 1000.)),))
        H, parts = sim._current_evaluation()
        np.testing.assert_array_equal(H, np.broadcast_to((0., 0., 1000.), sim.m.shape))
        volume = np.prod(sim.model.mesh.cell_size)
        expected = -4 * np.pi * 1e-7 * volume * 8e5 * np.sum(sim.m[0, ..., 2]) * 1000
        self.assertAlmostEqual(parts.sum() / expected, 1., places=14)
        self.assertEqual(sim._engine().counters()['subfields'], 1)

    def test_03_fim_local_field_matches_independent_existing_reference(self):
        from fimrun.bridge import legacy
        import importlib
        legacy()
        evaluate = importlib.import_module('user_fields').evaluate
        energy = (FiMExchange(A_A=5e-12, A_B=6e-12), OnsiteCoupling(Ah=-1e5),
                  DMI(D_A=.0001, D_B=-.0002), FiMAnisotropy(K1_A=1e4, K1_B=2e4, K2_A=100., K2_B=200.),
                  Zeeman(H_ext=(10., 20., 30.)))
        sim = self.fim(energy=energy)
        rng = np.random.default_rng(2)
        m = rng.normal(size=sim.m.shape)
        m /= np.linalg.norm(m, axis=-1, keepdims=True)
        sim.initialize({'A': m[0], 'B': m[1]})
        # Zero tensor isolates the local equations in the unchanged independent oracle.
        kernel = self.root / 'zero.f64'
        np.zeros((6, 6, 6), dtype='<f8').tofile(kernel)
        case = {'geometry': {'n': [3, 3, 1], 'cell_nm': [4., 4., 3.], 'pbc': [0, 0, 0]},
                'material': {'Ms_Apm': [3e5, 6e5], 'A_Jpm': [5e-12, 6e-12], 'Anh_Jpm': 0., 'Ah_Jpm3': -1e5,
                             'D_Jpm2': [.0001, -.0002], 'K1_Jpm3': [1e4, 2e4], 'K2_Jpm3': [100., 200.],
                             'axes': [[0., 0., 1.], [0., 0., 1.]], 'active': [1, 1, 1, 1]}, 'field': {'H_Apm': [10., 20., 30.]}}
        H, E = sim._current_evaluation()
        ref_H, ref_E = evaluate(sim.m, case, kernel)
        np.testing.assert_allclose(H, ref_H, rtol=1e-13, atol=1e-8)
        np.testing.assert_allclose(E, ref_E, rtol=1e-13, atol=1e-35)
        self.assertEqual(sim.metrics()['fft_transforms'], 0)
        self.assertIsNone(sim._engine().kernel)

    def test_04_demag_true_dispatch_and_one_cell_fm_oracle(self):
        model = FM(mesh=Grid(cells=(1, 1, 1), cell_size=(4e-9, 4e-9, 4e-9)),
                   material=FMMaterial(Ms=8e5, alpha=.02, gamma_H=221088.4), energy=(Demag(),))
        sim = Simulation(model=model, initial=Uniform((1., 0., 0.)), solver=RK4(dt=1e-15))
        self.live.append(sim)
        H, _ = sim._current_evaluation()
        np.testing.assert_allclose(H[0, 0, 0, 0], (-8e5 / 3, 0., 0.), atol=1e-8)
        self.assertEqual(sim.metrics()['fft_transforms'], 6)
        self.assertEqual(sim.metrics()['subfields'], 1)
        plain = self.fm()
        plain.run(duration=1e-15)
        self.assertEqual(plain.metrics()['fft_transforms'], 0)
        self.assertFalse(plain.metrics()['demag_cache_allocated'])

    def test_05_whole_split_exact_rk4_fm_and_fim(self):
        for factory in (self.fm, self.fim):
            whole = factory(energy=(Zeeman(H_ext=(100., 20., 1000.)),))
            split = factory(energy=(Zeeman(H_ext=(100., 20., 1000.)),))
            whole.run(duration=4e-15)
            split.run(duration=2e-15)
            path = self.root / (type(whole.model).__name__ + '.checkpoint')
            split.save_checkpoint(path)
            restored = Simulation.resume_checkpoint(path)
            self.live.append(restored)
            restored.run(duration=2e-15)
            np.testing.assert_array_equal(whole.m, restored.m)
            np.testing.assert_array_equal(whole.dissipation, restored.dissipation)
            np.testing.assert_array_equal(whole.drive_work, restored.drive_work)
            self.assertEqual(whole.time, restored.time)
            with self.assertRaises(ValueError):
                restored.set_field(H_ext=(0., 0., 0.))

    def test_06_current_switch_zero_dispatch_and_checkpoint_power(self):
        sot = FiMSOT(J=(1e11, 0., 0.), xi_A=.1, xi_B=.2)
        whole, split = self.fim(), self.fim()
        for sim in (whole, split):
            sim.set_current(sot)
        whole.run(duration=4e-15)
        split.run(duration=2e-15)
        path = self.root / 'sot.checkpoint'
        split.save_checkpoint(path)
        restored = Simulation.resume_checkpoint(path)
        self.live.append(restored)
        restored.run(duration=2e-15)
        np.testing.assert_array_equal(whole.m, restored.m)
        np.testing.assert_array_equal(whole.drive_work, restored.drive_work)
        before = whole.m
        whole.set_current(sot.with_current_density(J=(0., 0., 0.)))
        n = whole.metrics()['sot_rhs_calls']
        whole.run(duration=1e-15)
        self.assertEqual(whole.metrics()['sot_rhs_calls'], n)
        self.assertGreater(whole.time, 4e-15)
        self.assertTrue(np.array_equal(before, whole.m))

    def test_07_field_switch_branch_parent_and_clock(self):
        parent = self.fm(energy=(Zeeman(H_ext=(0., 0., 100.)),))
        parent.run(duration=2e-15)
        original = parent.m
        child = parent.branch(name='new-field', clock='inherit')
        zero = parent.branch(name='zero-clock', clock='zero')
        self.live.extend((child, zero))
        child.set_field(H_ext=(0., 100., 0.))
        np.testing.assert_array_equal(parent.m, original)
        np.testing.assert_array_equal(child.m, original)
        self.assertEqual(child.time, parent.time)
        self.assertEqual(zero.time, 0.)
        np.testing.assert_array_equal(zero.dissipation, np.zeros(1))
        self.assertEqual(child.events[-1]['kind'], 'field_switch')
        child.run(duration=1e-15)
        self.assertEqual(parent.time, 2e-15)
        changed = parent.branch(name='material', model=replace(parent.model, material=FMMaterial(Ms=7e5, alpha=.03, gamma_H=221088.4)))
        self.live.append(changed)
        self.assertIsNone(changed.energy_origin)
        np.testing.assert_array_equal(changed.dissipation, np.zeros(1))

    def test_08_physical_state_noncollinear_and_ovf_roundtrip(self):
        sim = self.fim()
        sim.run(duration=1e-15)
        state = self.root / 'physical.state'
        sim.save_state(state)
        loaded = Simulation.load_state(state)
        self.live.append(loaded)
        np.testing.assert_array_equal(sim.m, loaded.m)
        self.assertEqual(sim.time, loaded.time)
        self.assertIn('private history rebuilt', loaded.restore_grade)
        with self.assertRaises(ValueError):
            Simulation.resume_checkpoint(state)
        paths = {'A': self.root / 'A.ovf', 'B': self.root / 'B.ovf'}
        sim.export_magnetization(paths)
        again = self.fim(initial={label: OVF(path=str(path), quantity='direction') for label, path in paths.items()})
        np.testing.assert_allclose(sim.m, again.m, atol=1e-15, rtol=0)
        self.assertEqual(again.time, 0.)
        with self.assertRaises(ValueError):
            sim.export_magnetization({'A': paths['A'], 'B': paths['A']})

    def test_09_static_no_hidden_dynamics_and_checkpoint_history(self):
        sim = self.fim(initial={'A': Uniform((0., 0., 1.)), 'B': Uniform((0., 0., -1.))},
                       energy=(OnsiteCoupling(Ah=-1e5),))
        result = sim.relax(method='sdesc', stop=MaxTransverseField(1.))
        self.assertEqual(result.status, 'converged')
        self.assertEqual(result.steps, 0)
        self.assertEqual(sim.time, 0.)
        self.assertEqual(sim.metrics()['fields'], 1)
        path = self.root / 'static.checkpoint'
        sim.save_checkpoint(path)
        restored = Simulation.resume_checkpoint(path)
        self.live.append(restored)
        np.testing.assert_array_equal(sim._sd['controls'], restored._sd['controls'])
        self.assertEqual(restored.relax(method='sdesc', stop=MaxTransverseField(1.)).status, 'converged')

    def test_10_outputs_segments_and_no_analysis_default(self):
        out = self.root / 'experiment'
        sim = self.fm(outputs=Outputs(directory=out, scalars=('time', 'mean_m', 'energy'), every=1e-15))
        sim.run(duration=1e-15)
        sim.set_field(H_ext=(0., 0., 100.))
        sim.run(duration=1e-15)
        joined = read_segments(out)
        self.assertEqual(len(sim.segments), 2)
        self.assertEqual(joined['events'][-1]['kind'], 'field_switch')
        self.assertGreater(len(joined['rows']), 2)
        self.assertFalse(list(out.rglob('*.npz')))
        self.assertEqual(sim.metrics()['analysis_calls'], 0)
        self.assertFalse(any('m_B' in key for row in joined['rows'] for key in row))

    def test_11_cancellation_numeric_error_and_atomic_save(self):
        sim = self.fm()
        sim.run(duration=1e-15)
        before = sim.m
        clock = sim.time
        with patch.object(sim, '_rk4_step', side_effect=KeyboardInterrupt):
            result = sim.run(duration=2e-15)
        self.assertEqual(result.status, 'cancelled')
        np.testing.assert_array_equal(before, sim.m)
        self.assertEqual(clock, sim.time)
        with patch.object(sim, '_rk4_step', side_effect=FloatingPointError('injected numeric failure')):
            with self.assertRaises(FloatingPointError):
                sim.run(duration=2e-15)
        self.assertEqual(sim.last_result.status, 'failed')
        state = self.root / 'good.state'
        sim.save_state(state)
        saved = state.read_bytes()
        with patch('fimrun.micromagnetics.persistence.os.replace', side_effect=OSError('injected full disk')):
            with self.assertRaises(OSError):
                sim.save_state(state)
        self.assertEqual(saved, state.read_bytes())
        state.write_bytes(saved[:-10])
        with self.assertRaises(Exception):
            Simulation.load_state(state)

    def test_12_inert_stages_and_mutability(self):
        sim = self.fm()
        stages = (Evolve(duration=1e-15), SetField(H_ext=(0., 0., 100.)), Evolve(duration=1e-15))
        self.assertEqual(sim.metrics()['fields'], 0)
        results = sim.execute(stages)
        self.assertEqual(results[-1].status, 'completed')
        self.assertEqual(sim.time, 2e-15)
        with self.assertRaises(AttributeError):
            sim.model = sim.model

    def test_13_nontrivial_static_BB_strict_resume(self):
        energy = (FiMAnisotropy(K1_A=1e4, K1_B=2e4),)
        whole, split = self.fim(energy=energy), self.fim(energy=energy)
        from fimrun.micromagnetics.native import Native
        actual = Native.sd_step
        calls = [0]
        def bounded(engine, *args):
            calls[0] += 1
            if calls[0] > 5000:
                raise AssertionError('developer test watchdog; static did not converge')
            return actual(engine, *args)
        with patch.object(Native, 'sd_step', bounded):
            result = whole.relax(method='sdesc', stop=MaxTransverseField(1.))
        self.assertGreater(result.steps, 1)
        n = [0]
        def interrupted(engine, *args):
            n[0] += 1
            if n[0] == 3:
                raise KeyboardInterrupt
            return actual(engine, *args)
        with patch.object(Native, 'sd_step', interrupted):
            self.assertEqual(split.relax(method='sdesc', stop=MaxTransverseField(1.)).status, 'cancelled')
        self.assertEqual(split._sd['controls'][0], 2)
        path = self.root / 'bb.checkpoint'
        split.save_checkpoint(path)
        restored = Simulation.resume_checkpoint(path)
        self.live.append(restored)
        with patch.object(Native, 'sd_step', bounded):
            restored.relax(method='sdesc', stop=MaxTransverseField(1.))
        np.testing.assert_array_equal(whole.m, restored.m)
        np.testing.assert_array_equal(whole._sd['controls'], restored._sd['controls'])
        np.testing.assert_array_equal(whole._sd['gradient'], restored._sd['gradient'])
        self.assertEqual(whole.time, 0.)

    def test_14_fim_demag_periodic_Anh_and_independent_field(self):
        from fimrun.micromagnetics.native import Native
        from fimrun.bridge import legacy
        import importlib
        legacy()
        model = FiM(mesh=Grid(cells=(3,3,1), cell_size=(4e-9,4e-9,3e-9), boundary='periodic_xy', mirrors=(0,0)),
                    material=FiMMaterial(A=Sublattice(Ms=3e5,alpha=.01,gamma_H=221276.1569), B=Sublattice(Ms=6e5,alpha=.02,gamma_H=221276.1569)),
                    energy=(FiMExchange(A_A=5e-12,A_B=5e-12,Anh=-5e-12),Demag()))
        sim = Simulation(model=model, initial={'A':Smooth(amplitude=.01), 'B':Uniform((.03,0.,-1.),normalize=True)},solver=RK4(dt=1e-15))
        self.live.append(sim)
        H,E = sim._current_evaluation()
        case={'geometry':{'n':[3,3,1],'cell_nm':[4.,4.,3.],'pbc':[1,1,0]},
              'material':{'Ms_Apm':[3e5,6e5],'A_Jpm':[5e-12,5e-12],'Anh_Jpm':-5e-12,'Ah_Jpm3':0.,'D_Jpm2':[0.,0.],
                          'K1_Jpm3':[0.,0.],'K2_Jpm3':[0.,0.],'axes':[[0.,0.,1.],[0.,0.,1.]],'active':[1,0,0,0]},'field':{'H_Apm':[0.,0.,0.]}}
        ref_H,ref_E=importlib.import_module('user_fields').evaluate(sim.m,case,sim._engine().kernel)
        np.testing.assert_allclose(H,ref_H,rtol=1e-12,atol=1e-8)
        np.testing.assert_allclose(E,ref_E,rtol=1e-12,atol=1e-34)
        self.assertEqual(sim.metrics()['fft_transforms'],6)
        path=self.root/'demag.state';sim.save_state(path)
        restored=Simulation.load_state(path);self.live.append(restored)
        restored_H,restored_E=restored._current_evaluation()
        np.testing.assert_array_equal(H,restored_H)
        np.testing.assert_array_equal(E,restored_E)

    def test_15_cross_process_state_and_snapshot_analysis_switches(self):
        import subprocess,sys
        sim=self.fim(outputs=Outputs(directory=self.root/'snapshots',snapshots=1e-15))
        sim.run(duration=1e-15)
        self.assertGreater(sim.metrics()['snapshot_writes'],0)
        self.assertEqual(sim.metrics()['analysis_calls'],0)
        path=self.root/'portable.state';sim.save_state(path)
        code='from fimrun.micromagnetics import Simulation; import sys; s=Simulation.load_state(sys.argv[1]); assert s.time==1e-15; assert s.m.shape==(2,1,3,3,3); assert s.metrics()["fields"]==0; print(s.describe()["model"])'
        result=subprocess.run([sys.executable,'-c',code,str(path)],capture_output=True,text=True,check=True)
        self.assertEqual(result.stdout.strip(),'FiM')
        before=sim.metrics()['fields']
        observed=sim.analyze('structure')
        self.assertEqual(set(observed),{'A','B'})
        self.assertEqual(sim.metrics()['analysis_calls'],1)
        self.assertEqual(sim.metrics()['fields'],before)

    def test_16_state_corruption_version_and_strict_identity(self):
        import hashlib,zipfile
        sim=self.fm();sim.run(duration=1e-15)
        path=self.root/'strict.checkpoint';sim.save_checkpoint(path)
        with zipfile.ZipFile(path) as z:
            data={name:z.read(name) for name in z.namelist()}
        value=json.loads(data['manifest.json']);value['implementation']={'fake':'not-current'}
        data['manifest.json']=json.dumps(value).encode()
        data['manifest.sha256']=hashlib.sha256(data['manifest.json']).hexdigest().encode()
        with zipfile.ZipFile(path,'w') as z:
            for name,body in data.items():z.writestr(name,body)
        with self.assertRaises(ValueError):Simulation.resume_checkpoint(path)
        physical=Simulation.load_state(path);self.live.append(physical)
        self.assertEqual(physical.time,sim.time)


    def test_17_real_cross_process_continuation(self):
        import subprocess,sys
        for name,factory in (('fm',self.fm),('fim',self.fim)):
            whole=factory(energy=(Zeeman(H_ext=(20.,30.,1000.)),))
            split=factory(energy=(Zeeman(H_ext=(20.,30.,1000.)),))
            if name=='fim':
                for sim in (whole,split):sim.set_current(FiMSOT(J=(1e11,0.,0.),xi_A=.1,xi_B=.2))
            whole.run(duration=4e-15);split.run(duration=2e-15)
            source=self.root/(name+'.state');destination=self.root/(name+'.npz')
            split.save_state(source)
            code='from fimrun.micromagnetics import Simulation; from fimrun.micromagnetics.native import EVALUATIONS; import sys,numpy as np,json; s=Simulation.load_state(sys.argv[1]); s.run(duration=2e-15); np.savez(sys.argv[2],m=s.m,D=s.dissipation,P=s.drive_work,time=s.time); print(json.dumps(EVALUATIONS)); s.close()'
            result=subprocess.run([sys.executable,'-c',code,str(source),str(destination)],check=True,capture_output=True,text=True)
            costs=json.loads(result.stdout)
            for key,value in costs.items():CHILD_FIELDS[key]+=value
            with np.load(destination,allow_pickle=False) as data:
                np.testing.assert_array_equal(whole.m,data['m'])
                np.testing.assert_array_equal(whole.dissipation,data['D'])
                np.testing.assert_array_equal(whole.drive_work,data['P'])
                self.assertEqual(whole.time,float(data['time']))

    def test_18_actual_native_module_branch_counters(self):
        plain=self.fim();plain.run(duration=1e-15)
        self.assertEqual(set(plain.metrics()['contribution_branches'].values()),{0})
        cases=[(FiMExchange(A_A=0.,A_B=0.),'exchange_and_Anh'),
               (OnsiteCoupling(Ah=0.),'onsite_Ah'),(DMI(D_A=0.,D_B=0.),'DMI'),
               (FiMAnisotropy(K1_A=0.,K1_B=0.),'anisotropy')]
        for term,enabled in cases:
            sim=self.fim(energy=(term,));sim._current_evaluation()
            counts=sim.metrics()['contribution_branches']
            self.assertGreater(counts[enabled],0)
            self.assertTrue(all(v==0 for k,v in counts.items() if k!=enabled))
            self.assertEqual(sim.metrics()['fft_transforms'],0)
        one=self.fm();one._current_evaluation()
        self.assertEqual(set(one.metrics()['contribution_branches'].values()),{0})

    def test_19_sampling_solver_switch_and_no_hidden_rounding(self):
        sim=self.fm(outputs=Outputs(directory=self.root/'sampling',scalars=('time',),every=2e-15,snapshot_times=(0.,2e-15)))
        sim.run(duration=2e-15)
        self.assertEqual(len(list((self.root/'sampling').rglob('*.npz'))),2)
        old=sim.solver
        with self.assertRaises(ValueError):sim.set_solver(RK4(dt=1.5e-15))
        self.assertEqual(sim.solver,old)
        sim.set_solver(RK4(dt=.5e-15))
        sim.run(duration=2e-15)
        self.assertEqual(sim.time,4e-15)
        fields=sim.metrics()['fields']
        with self.assertRaises(ValueError):sim.run(duration=.5e-15)
        self.assertEqual(sim.metrics()['fields'],fields)
        self.assertEqual(sim.check()['managed_fields'],0)


    def test_20_existing_independent_LLG_SOT_and_power_formulas(self):
        from fimrun.bridge import legacy
        import importlib
        legacy()
        mu0=4*np.pi*1e-7
        H_value=(100.,-200.,300.)
        sim=self.fim(energy=(Zeeman(H_ext=H_value),))
        m=sim.m;H,_=sim._current_evaluation()
        sot=FiMSOT(J=(1e11,2e10,0.),xi_A=.1,xi_B=-.2,field_like_A=.03,field_like_B=-.02)
        rhs,power=sim._engine().rhs(m,H,sot)
        case={'drive':{'incident_direction':sot.incident_direction,'Jc_Apm2':sot.J,'xi':[sot.xi_A,sot.xi_B],
                       'field_like_ratio':[sot.field_like_A,sot.field_like_B],'thickness_m':3e-9},
              'material':{'alpha':[.01,.02],'Ms_Apm':[3e5,6e5]}}
        torque=importlib.import_module('current_case').drive_rhs(m,case)
        expected=np.empty_like(m);loss=[];work=[];V=np.prod(sim.model.mesh.cell_size)
        for i,label in enumerate(sim.labels):
            c=getattr(sim.model.material,label)
            a=np.cross(m[i],H[i]);b=np.cross(m[i],a)
            expected[i]=-c.gamma_H/(1+c.alpha*c.alpha)*(a+c.alpha*b)+torque[i]
            loss.append(mu0*V*c.Ms*c.gamma_H*c.alpha/(2*(1+c.alpha*c.alpha))*np.sum(a*a))
            work.append(-mu0*V*c.Ms/2*np.sum(H[i]*torque[i]))
        scale=max(1.,float(np.max(np.abs(expected))))
        self.assertLessEqual(float(np.max(np.abs(rhs-expected)))/scale,1e-12)
        np.testing.assert_allclose(power,np.array(loss+work),rtol=1e-12,atol=1e-30)
        one=self.fm(energy=(Zeeman(H_ext=H_value),))
        h,_=one._current_evaluation();v=one.m
        k,p=one._engine().rhs(v,h,None)
        c=one.model.material;a=np.cross(v,h);b=np.cross(v,a)
        expected=-c.gamma_H/(1+c.alpha*c.alpha)*(a+c.alpha*b)
        np.testing.assert_allclose(k,expected,rtol=1e-12,atol=1e-7)
        expected_loss=mu0*np.prod(one.model.mesh.cell_size)*c.Ms*c.gamma_H*c.alpha/(1+c.alpha*c.alpha)*np.sum(a*a)
        self.assertLessEqual(abs(p[0]-expected_loss)/max(abs(expected_loss),1e-30),1e-12)
        self.assertEqual(p[2],0.)

    def test_21_static_consecutive_checkpoint_position_and_failed_candidate(self):
        from fimrun.micromagnetics.native import Native
        stop = MaxTransverseField(1000., consecutive=2)
        def make():
            return self.fim(energy=(Zeeman(H_ext=(100., 0., 0.)),),
                            initial={'A': Uniform((0., 0., 1.)), 'B': Uniform((0., 0., -1.))})
        whole = make()
        self.assertEqual(whole.relax(method='sdesc', stop=stop).steps, 1)
        for failure in ('cancel_before_update', 'candidate_field_failure'):
            for checkpoint in (False, True):
                with self.subTest(failure=failure, checkpoint=checkpoint):
                    split = make()
                    if failure == 'cancel_before_update':
                        with patch.object(Native, 'sd_step', side_effect=KeyboardInterrupt):
                            self.assertEqual(split.relax(method='sdesc', stop=stop).status, 'cancelled')
                    else:
                        split._current_evaluation()
                        with patch.object(split, '_evaluate', side_effect=FloatingPointError('injected candidate field failure')):
                            with self.assertRaises(FloatingPointError):
                                split.relax(method='sdesc', stop=stop)
                        self.assertEqual(split.last_result.status, 'failed')
                    self.assertEqual(split._sd['consecutive'], 1)
                    self.assertTrue(split._sd['residual_checked'])
                    if checkpoint:
                        path = self.root / (failure + '.checkpoint')
                        split.save_checkpoint(path)
                        resumed = Simulation.resume_checkpoint(path)
                        self.live.append(resumed)
                        with self.assertRaises(ValueError):
                            resumed.relax(method='sdesc', stop=MaxTransverseField(1000., consecutive=3))
                    else:
                        resumed = split
                    result = resumed.relax(method='sdesc', stop=stop)
                    self.assertEqual((result.status, result.steps), ('converged', 1))
                    np.testing.assert_array_equal(whole.m, resumed.m)
                    for key in ('prev', 'gradient', 'controls'):
                        np.testing.assert_array_equal(whole._sd[key], resumed._sd[key])
                    for key in ('consecutive', 'criterion', 'residual_checked'):
                        self.assertEqual(whole._sd[key], resumed._sd[key])
                    # Calling relax again on the same accepted endpoint cannot count it again.
                    self.assertEqual(resumed.relax(method='sdesc', stop=stop).steps, 0)
                    self.assertEqual(resumed._sd['consecutive'], 2)



if __name__ == '__main__':
    unittest.main()
