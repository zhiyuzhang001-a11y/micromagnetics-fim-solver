"""Zero-field cancellation propagation for runnable examples and daily template."""
from pathlib import Path
import contextlib
import io
import runpy
import os
import sys
import unittest
from unittest.mock import patch
from fimrun.micromagnetics import Simulation, RunResult, FM, FMMaterial, Grid, Uniform, RK4
from fimrun.micromagnetics.native import Native, EVALUATIONS


class ScriptCancellation(unittest.TestCase):
    def test_each_explicit_stage_stops_the_script(self):
        root = Path(__file__).resolve().parents[1]
        scripts = [('examples/script_api/fm_sequence.py', 2),
                   ('examples/script_api/fim_sequence.py', 3),
                   ('examples/script_api/state_branch.py', 3)]
        if os.environ.get('FIMRUN_DESKTOP_SCRIPT'):
            scripts.append((os.environ['FIMRUN_DESKTOP_SCRIPT'], 3))
        initial_counts = dict(EVALUATIONS)
        for name, stages in scripts:
            for cancel_at in range(1, stages + 1):
                with self.subTest(script=name, cancel_at=cancel_at):
                    calls = []
                    number = [0]
                    def operation(kind):
                        def execute(sim, **kwargs):
                            number[0] += 1
                            status = 'cancelled' if number[0] == cancel_at else 'converged' if kind == 'relax' else 'completed'
                            calls.append((kind, status))
                            if kind == 'run' and status == 'completed':
                                sim._time += kwargs['duration']
                            return RunResult(status, 0., sim.time, 0, None, None, 'injected')
                        return execute
                    def mark(name):
                        def execute(*args, **kwargs):calls.append((name, 'called'))
                        return execute
                    def restored(*args, **kwargs):
                        sim = Simulation(model=FM(mesh=Grid(cells=(2,2,1), cell_size=(4e-9,4e-9,3e-9)),
                                                  material=FMMaterial(Ms=8e5,alpha=.02,gamma_H=221088.4)),
                                         initial=Uniform((1.,0.,0.)), solver=RK4(dt=1e-15))
                        sim.restore_grade = 'strict_checkpoint'
                        return sim
                    with contextlib.ExitStack() as stack:
                        stack.enter_context(patch.object(Native, '__init__', side_effect=AssertionError('must remain zero-field')))
                        stack.enter_context(patch.object(Simulation, 'run', operation('run')))
                        stack.enter_context(patch.object(Simulation, 'relax', operation('relax')))
                        for method in ('set_field','set_current','set_outputs','set_solver','save_state','save_checkpoint','export_magnetization'):
                            stack.enter_context(patch.object(Simulation, method, mark(method)))
                        for method in ('load_state','resume_checkpoint'):
                            stack.enter_context(patch.object(Simulation, method, restored))
                        stack.enter_context(patch.object(sys, 'argv', [name]))
                        stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
                        with self.assertRaises(SystemExit) as stopped:
                            runpy.run_path(str(root / name), run_name='__main__')
                    self.assertEqual(stopped.exception.code, 130)
                    self.assertEqual(number[0], cancel_at)
                    self.assertEqual(calls[-1][1], 'cancelled')
        self.assertEqual(EVALUATIONS, initial_counts)


if __name__ == '__main__':unittest.main()
