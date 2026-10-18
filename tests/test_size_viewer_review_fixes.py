"""Zero-field runner ownership regressions for the independent review P2."""
import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import numpy as np
from fimrun.micromagnetics import *
from fimrun.micromagnetics import script
from fimrun.micromagnetics.native import Native, EVALUATIONS


class ReviewFixes(unittest.TestCase):
    def setUp(self):
        self.before = dict(EVALUATIONS)
        self.native = patch.object(Native, '__init__', side_effect=AssertionError('native work forbidden'))
        self.native.start()
        material = Sublattice(Ms=3e5, alpha=.01, gamma_H=2e5)
        self.model = FiM(mesh=Grid(cells=(3, 3, 1), cell_size=(4e-9, 4e-9, 3e-9)),
                         material=FiMMaterial(A=material, B=material))
        self.initial = {'A': Uniform((0., 0., 1.)), 'B': Uniform((0., 0., -1.))}

    def tearDown(self):
        self.native.stop()
        self.assertEqual(EVALUATIONS, self.before)

    @staticmethod
    def cached_field(sim):
        sim._field = np.zeros_like(sim.m)
        sim._energy = np.zeros(7)
        return sim._field, sim._energy

    def run_script(self, root, stages, *, argv=None):
        with contextlib.redirect_stdout(io.StringIO()), \
             patch.object(Simulation, '_current_evaluation', self.cached_field):
            return run_script(model=self.model, initial=self.initial, solver=RK4(dt=1e-15),
                              outputs=Outputs(directory=root), stages=stages, argv=[] if argv is None else argv)

    def test_initial_save_then_first_dynamic_or_static_and_continuation(self):
        for static_first in (False, True):
            with self.subTest(static_first=static_first), tempfile.TemporaryDirectory() as folder:
                root = Path(folder)/'parent'/'experiment'
                evolve, relax = Evolve(duration=0.), Relax(stop=MaxTransverseField(1.))
                operations = (relax, evolve) if static_first else (evolve, relax)
                stages = (SaveState(root/'nested'/'initial.state'), *operations,
                          Evolve(duration=0.), SaveState(root/'final.state'))
                with Simulation(model=self.model, initial=self.initial, solver=RK4(dt=1e-15),
                                outputs=Outputs(directory=root)) as sim:
                    plan = check_stages(sim, stages)
                self.assertEqual(plan['output_root'], str(root.resolve()))
                self.assertFalse(root.exists())
                self.assertEqual(self.run_script(root, stages), 0)
                for filename in ('nested/initial.state', 'final.state'):
                    with Simulation.load_state(root/filename) as loaded:
                        self.assertEqual(loaded.time, 0.)
                        self.assertEqual(loaded.metrics()['fields'], 0)
                metadata = json.loads((root/'segments.json').read_text())
                self.assertEqual([s['status'] for s in metadata['segments']],
                                 ['converged' if s is relax else 'completed' for s in (*operations, evolve)])
                self.assertEqual(len(list(root.glob('segment-*'))), 3)

    def test_initial_save_then_cancel_keeps_accepted_state_and_stops_later_save(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)/'experiment'
            stages = (SaveState(root/'initial.state'), Evolve(duration=1e-15),
                      SaveState(root/'must-not-exist.state'), Evolve(duration=0.))
            with patch.object(Simulation, '_rk4_step', side_effect=KeyboardInterrupt):
                self.assertEqual(self.run_script(root, stages), 130)
            self.assertTrue((root/'initial.state').is_file())
            self.assertFalse((root/'must-not-exist.state').exists())
            result = json.loads((root/'segment-00000'/'result.json').read_text())
            self.assertEqual((result['status'], result['steps']), ('cancelled', 0))
            self.assertEqual(len(list(root.glob('segment-*'))), 1)

    def test_external_directory_existing_save_repetition_and_claim_race_reject(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)/'experiment'; root.mkdir()
            unrelated = root/'unrelated.txt'; unrelated.write_bytes(b'keep unchanged')
            with self.assertRaises(FileExistsError):
                self.run_script(root, (SaveState(root/'initial.state'), Evolve(duration=0.)))
            self.assertEqual(list(root.iterdir()), [unrelated])
            self.assertEqual(unrelated.read_bytes(), b'keep unchanged')
            destination = Path(folder)/'existing.state'; destination.write_bytes(b'original')
            for stages in ((SaveState(destination), Evolve(duration=0.)),
                           (SaveState(Path(folder)/'duplicate.state'),)*2):
                with self.assertRaises(FileExistsError):
                    self.run_script(Path(folder)/'fresh', stages)
            self.assertEqual(destination.read_bytes(), b'original')
            self.assertFalse((Path(folder)/'fresh').exists())
            self.assertFalse((Path(folder)/'duplicate.state').exists())
            race = Path(folder)/'race'
            original_check = script.check_stages
            def raced_check(*args):
                result = original_check(*args)
                race.mkdir(); (race/'foreign.txt').write_bytes(b'other owner')
                return result
            with patch.object(script, 'check_stages', side_effect=raced_check):
                with self.assertRaises(FileExistsError):
                    self.run_script(race, (SaveState(race/'initial.state'), Evolve(duration=0.)))
            self.assertEqual([p.name for p in race.iterdir()], ['foreign.txt'])
            self.assertEqual((race/'foreign.txt').read_bytes(), b'other owner')

    def test_entire_reserved_namespace_rejects_before_any_write(self):
        names = ('segments.json', 'SEGMENTS.JSON', 'segments.json/child.state', 'segment-00000',
                 'segment-00000/initial.state', 'segment-00001/custom.state',
                 'segment-99999/custom.state', 'segment-100000/custom.state')
        for name in names:
            with self.subTest(target=name), tempfile.TemporaryDirectory() as folder:
                base = Path(folder); root = base/'new-parent'/'experiment'
                sentinel = base/'must-not-be-written.state'
                stages = (SaveState(sentinel), SaveState(root/name), Evolve(duration=0.))
                with self.assertRaises(ValueError):
                    self.run_script(root, stages)
                self.assertEqual(list(base.iterdir()), [])
        managed = ('accepted.state', 'ACCEPTED.STATE', 'result.json', 'scalars.csv',
                   'm-000000000000.npz', 'm-999999999999.npz', 'm-1000000000000.npz')
        for name in managed:
            for suffix in ('', '/child.state'):
                with self.subTest(managed=name, suffix=suffix), tempfile.TemporaryDirectory() as folder:
                    base = Path(folder); root = base/'experiment'
                    stages = (SaveState(base/'must-not-be-written.state'), Evolve(duration=0.),
                              SaveState(root/('segment-00000/'+name+suffix)))
                    with self.assertRaises(ValueError):
                        self.run_script(root, stages)
                    self.assertEqual(list(base.iterdir()), [])
        # A future directory cannot be created even by a custom save between stages.
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)/'experiment'
            with self.assertRaises(ValueError):
                self.run_script(root, (Evolve(duration=0.), SaveState(root/'segment-00001/custom.state'),
                                       Evolve(duration=0.)))
            self.assertEqual(list(Path(folder).iterdir()), [])
        for argv in ([], ['--check']):
            with self.subTest(argv=argv), tempfile.TemporaryDirectory() as folder:
                root = Path(folder)/'experiment'
                with self.assertRaises(ValueError):
                    self.run_script(root, (Evolve(duration=0.), SaveState(root/'segments.json')), argv=argv)
                self.assertEqual(list(Path(folder).iterdir()), [])

    def test_normalized_paths_and_ancestor_conflicts_reject_without_side_effects(self):
        for relation in ('root', 'root-parent', 'normalized-index', 'save-ancestor', 'save-descendant'):
            with self.subTest(relation=relation), tempfile.TemporaryDirectory() as folder:
                base = Path(folder); root = base/'new-parent'/'experiment'
                bad = {'root': root, 'root-parent': root.parent,
                       'normalized-index': root/'custom/../segments.json',
                       'save-ancestor': root/'custom', 'save-descendant': root/'custom/child.state'}[relation]
                stages = (SaveState(root/'custom/child.state'), SaveState(bad), Evolve(duration=0.)) \
                         if relation == 'save-ancestor' else \
                         (SaveState(root/'custom'), SaveState(bad), Evolve(duration=0.)) \
                         if relation == 'save-descendant' else (SaveState(bad), Evolve(duration=0.))
                with self.assertRaises((ValueError, FileExistsError)):
                    self.run_script(root, stages)
                self.assertEqual(list(base.iterdir()), [])
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder); root = base/'experiment'; alias = base/'alias'
            alias.symlink_to(root, target_is_directory=True)
            with self.assertRaises(ValueError):
                self.run_script(root, (SaveState(alias/'segments.json'), Evolve(duration=0.)))
            self.assertEqual(list(base.iterdir()), [alias])
            broken = base/'broken.state'; broken.symlink_to(base/'missing.state')
            with self.assertRaises(FileExistsError):
                self.run_script(root, (SaveState(broken), Evolve(duration=0.)))
            self.assertTrue(broken.is_symlink()); self.assertFalse(root.exists())
            parent_file = base/'existing-file'; parent_file.write_bytes(b'keep')
            with self.assertRaises(FileExistsError):
                self.run_script(root, (SaveState(parent_file/'child.state'), Evolve(duration=0.)))
            self.assertEqual(parent_file.read_bytes(), b'keep'); self.assertFalse(root.exists())
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)/'experiment'
            with self.assertRaises(FileExistsError):
                self.run_script(root, (SaveState(root/'Custom.state'),
                                       SaveState(root/'custom.state/child.state'), Evolve(duration=0.)))
            self.assertEqual(list(Path(folder).iterdir()), [])

    def test_legal_normalized_and_established_segment_saves_preserve_actual_outputs(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)/'experiment'
            stages = (SaveState(root/'segment-00000/../initial.state'),
                      SaveState(root/'nested/initial.state'), Evolve(duration=0.),
                      SaveState(root/'segment-00000/custom/accepted.state'),
                      SaveState(root/'segment-00000/user.state'), Evolve(duration=0.),
                      SaveState(root/'final.state'))
            with contextlib.redirect_stdout(io.StringIO()), \
                 patch.object(Simulation, '_current_evaluation', self.cached_field):
                code = run_script(model=self.model, initial=self.initial, solver=RK4(dt=1e-15),
                                  outputs=Outputs(directory=root, scalars=('time',), snapshot_times=(0.,)),
                                  stages=stages, argv=[])
            self.assertEqual(code, 0)
            for relative in ('initial.state', 'nested/initial.state', 'segment-00000/custom/accepted.state',
                             'segment-00000/user.state', 'final.state'):
                with Simulation.load_state(root/relative) as loaded:
                    self.assertEqual(loaded.time, 0.)
            for index in (0, 1):
                segment = root/f'segment-{index:05d}'
                for name in ('accepted.state', 'result.json', 'scalars.csv', 'm-000000000000.npz'):
                    self.assertTrue((segment/name).is_file(), name)
            self.assertEqual(json.loads((root/'segments.json').read_text())['schema'], 'micromagnetics-segments-v1')

    def test_segment_numbering_includes_stages_without_disk_output(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)/'experiment'
            outputs = Outputs(directory=root)
            stages = (SetOutputs(Outputs()), Evolve(duration=0.), SetOutputs(outputs),
                      Evolve(duration=0.), SaveState(root/'segment-00001/user.state'))
            self.assertEqual(self.run_script(root, stages), 0)
            self.assertFalse((root/'segment-00000').exists())
            self.assertTrue((root/'segment-00001/user.state').is_file())
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)/'experiment'
            with self.assertRaises(ValueError):
                self.run_script(root, (SetOutputs(Outputs()), Evolve(duration=0.),
                                       SetOutputs(Outputs(directory=root)), Evolve(duration=0.),
                                       SaveState(root/'segment-00000/user.state')))
            self.assertEqual(list(Path(folder).iterdir()), [])


if __name__ == '__main__':
    unittest.main()
