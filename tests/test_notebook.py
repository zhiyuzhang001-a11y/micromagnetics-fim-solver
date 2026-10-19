"""Notebook helper contracts; finite native test is separately counted."""
import ast
import contextlib
import io
import json
import os
import subprocess
import sys
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile
import numpy as np
from fimrun.micromagnetics import *
from fimrun.micromagnetics.native import Native, EVALUATIONS
from fimrun.notebook import NotebookSession, summary, CellStopped


def model():
    sub = Sublattice(Ms=3e5, alpha=.01, gamma_H=2e5)
    return FiM(mesh=Grid(cells=(3,3,1), cell_size=(4e-9,4e-9,3e-9)),
               material=FiMMaterial(A=sub, B=sub),
               energy=(FiMAnisotropy(K1_A=1e4,K1_B=2e4),))


INITIAL = {'A': Uniform((0.,0.,1.)), 'B': Uniform((0.,0.,-1.))}


class ZeroNotebook(unittest.TestCase):
    def setUp(self):
        self.before = dict(EVALUATIONS)
        self.no_native = patch.object(Native, '__init__', side_effect=AssertionError('native work forbidden'))
        self.no_native.start()

    def tearDown(self):
        self.no_native.stop()
        self.assertEqual(EVALUATIONS, self.before)

    def start(self, parent, **kwargs):
        return NotebookSession.start(model=model(), initial=INITIAL, solver=RK4(dt=1e-15), parent=parent, **kwargs)

    def test_summary_raises_and_control_sequence_cannot_reach_sentinel(self):
        actions = []
        for status in ('cancelled', 'failed'):
            with contextlib.redirect_stdout(io.StringIO()), self.assertRaises(CellStopped):
                summary(RunResult(status,0.,0.,0,None,'fixture','id'))
                actions.append('must not execute')
        self.assertEqual(actions, [])
        self.assertEqual(summary(RunResult('completed',0.,1e-15,1,None,None,'id'))['status'], 'completed')
        # Actual VS Code queue behavior is a separate required UI acceptance item.

    def test_initial_save_restore_and_repeated_create_guard(self):
        with tempfile.TemporaryDirectory() as folder:
            session = self.start(folder)
            try:
                self.assertFalse(session.trajectory.exists())
                receipt = session.save('initial.state')
                self.assertTrue(zipfile.is_zipfile(receipt['path']))
                self.assertFalse(session.trajectory.exists())
                with self.assertRaises(RuntimeError):self.start(folder, previous=session)
                session.close()
                restored = NotebookSession.load(receipt['path'], parent=folder, previous=session)
                try:
                    self.assertNotEqual(restored.sim.run_id,session.sim.run_id)
                    np.testing.assert_array_equal(restored.sim.m,session.sim.m)
                    self.assertFalse(restored.trajectory.exists())
                    self.assertNotEqual(restored.directory,session.directory)
                finally:restored.close()
            finally:session.close()

    def test_save_new_never_overwrites_or_escapes_and_handles_competing_file(self):
        with tempfile.TemporaryDirectory() as folder:
            session = self.start(folder)
            try:
                session.save('first.state'); original = (session.states/'first.state').read_bytes()
                for name in ('first.state','../trajectory/segments.json','/tmp/escape.state','nested/file','..'):
                    with self.subTest(name=name), self.assertRaises((FileExistsError,ValueError)):
                        session.save(name)
                self.assertEqual((session.states/'first.state').read_bytes(),original)
                (session.states/'broken.state').symlink_to(session.states/'missing')
                with self.assertRaises(FileExistsError):session.save('broken.state')
                real_link=os.link
                def competing(source,target):
                    Path(target).write_bytes(b'foreign file');real_link(source,target)
                with patch('fimrun.notebook.os.link',side_effect=competing),self.assertRaises(FileExistsError):
                    session.save('raced.state')
                self.assertEqual((session.states/'raced.state').read_bytes(),b'foreign file')
                self.assertFalse(list(session.states.glob('.save-*')))
                self.assertFalse(session.trajectory.exists())
            finally:session.close()

    def test_delivered_notebook_fresh_run_all_is_zero_field_and_second_preserves_sim(self):
        notebook=json.loads((Path(__file__).resolve().parents[1]/'tests/fixtures/notebook_contract.ipynb').read_text())
        cells=[''.join(c['source']) for c in notebook['cells'] if c['cell_type']=='code']
        self.assertEqual(len(cells),4)
        for cell in cells:
            for node in ast.walk(ast.parse(cell)):
                if isinstance(node,ast.Call) and isinstance(node.func,ast.Attribute):
                    self.assertNotIn(node.func.attr,('run','relax','save','save_state','save_checkpoint','execute'))
        result = subprocess.run([sys.executable, str(Path(__file__).with_name('notebook_zero_probe.py')), 'run-all'],
                                capture_output=True, text=True, check=True)
        self.assertEqual(json.loads(result.stdout)['fields'], {'fm': 0, 'fim': 0})

    def test_import_origin_and_cache_rejection(self):
        for mode in ('foreign-cache', 'same-path-cache', 'changed-cache', 'source-priority'):
            with self.subTest(mode=mode):
                result = subprocess.run([sys.executable, str(Path(__file__).with_name('notebook_zero_probe.py')), mode],
                                        capture_output=True, text=True, check=True)
                self.assertEqual(json.loads(result.stdout)['fields'], {'fm': 0, 'fim': 0})

    def test_closed_preview_then_start_and_load_cleans_old_resources(self):
        def start_preview(display, *, open_browser=True):
            display.server = object()
        def close_preview(display):
            display.server = None
        with tempfile.TemporaryDirectory() as folder, \
             patch('fimrun.micromagnetics.preview.LivePreview.start', start_preview), \
             patch('fimrun.micromagnetics.preview.LivePreview.close', close_preview):
            session = self.start(folder)
            sim = session.sim
            saved = session.save('initial.state')
            session.preview(sim)
            display = sim._preview
            old_preview = sim.preview
            self.assertIsNotNone(display.server)
            with self.assertRaises(RuntimeError):session.preview(object())
            session.close()
            self.assertIsNone(display.server)
            self.assertIsNone(sim._preview)
            for operation in (old_preview, sim.preview, lambda: session.preview(sim),
                              lambda: sim.run(duration=1e-15), lambda: sim.set_current(None),
                              lambda: sim.save_state(Path(folder)/'forbidden.state')):
                with self.assertRaises(RuntimeError):operation()
            self.assertEqual(sim.time,0.)
            np.testing.assert_array_equal(sim.m, session.sim.m)
            self.assertFalse((Path(folder)/'forbidden.state').exists())
            notebook = json.loads((Path(__file__).resolve().parents[1]/'tests/fixtures/notebook_contract.ipynb').read_text())
            preview_cell = ''.join(next(c for c in notebook['cells'] if c['id']=='initial-preview')['source'])
            with self.assertRaises(RuntimeError):exec(preview_cell, {'session':session, 'sim':sim})
            # Emulate a stale/reopened resource via the unchanged core class API.
            with self.assertRaises(RuntimeError):Simulation.preview(sim)
            stale_display = display
            self.assertIsNone(stale_display.server)
            # Defense in depth: previous.close is called again even with closed=True.
            with patch.object(session, 'close', wraps=session.close) as cleanup:
                fresh = self.start(folder, previous=session)
                cleanup.assert_called_once()
            self.assertIsNone(sim._preview)
            self.assertIsNone(stale_display.server)
            fresh.preview(fresh.sim)
            fresh_display = fresh.sim._preview
            fresh.sim.close()
            self.assertTrue(fresh.closed)
            self.assertIsNone(fresh_display.server)
            with self.assertRaises(RuntimeError):fresh.sim.preview()
            with patch.object(fresh, 'close', wraps=fresh.close) as cleanup:
                restored = NotebookSession.load(saved['path'],parent=folder,previous=fresh)
                cleanup.assert_called_once()
            try:
                restored.preview(restored.sim)
                self.assertIsNotNone(restored.sim._preview.server)
                self.assertIsNone(sim._preview)
                self.assertIsNone(fresh.sim._preview)
            finally:
                restored.close();fresh.close();session.close()



class FiniteNotebook(unittest.TestCase):
    def test_static_then_new_current_cells_repeat_and_both_restore_grades(self):
        with tempfile.TemporaryDirectory() as folder:
            session=NotebookSession.start(model=model(),initial=INITIAL,solver=RK4(dt=1e-15),parent=folder)
            restored=strict=None
            try:
                sim=session.sim;run_id=sim.run_id
                self.assertEqual(summary(sim.relax(method='sdesc',stop=MaxTransverseField(1.)))['status'],'converged')
                state=sim.m;clock=sim.time
                sim.set_current(FiMSOT(J=(1e11,0.,0.),xi_A=.1,xi_B=.1))
                np.testing.assert_array_equal(sim.m,state);self.assertEqual(sim.time,clock)
                first=summary(sim.run(duration=1e-15));second=summary(sim.run(duration=1e-15))
                self.assertEqual(sim.run_id,run_id);self.assertEqual(first['end_s'],second['start_s'])
                self.assertEqual(sim.time,2e-15)
                saved=session.save('driven.state');session.close()
                restored=NotebookSession.load(saved['path'],parent=folder,previous=session)
                np.testing.assert_array_equal(restored.sim.m,sim.m)
                self.assertEqual(restored.sim.time,sim.time)
                summary(restored.sim.run(duration=1e-15))
                saved_cp=restored.save('driven.checkpoint',checkpoint=True)
                strict=NotebookSession.load(saved_cp['path'],parent=folder,checkpoint=True)
                np.testing.assert_array_equal(strict.sim.m,restored.sim.m)
                with self.assertRaises(ValueError):strict.sim.set_current(None)
                summary(strict.sim.run(duration=1e-15))
            finally:
                session.close()
                if restored:restored.close()
                if strict:strict.close()


if __name__=='__main__':unittest.main()
