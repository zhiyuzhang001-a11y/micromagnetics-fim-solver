"""Idle replacement and safe OVF contracts; no user kernel or viewer attached."""
import contextlib
import io
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
import numpy as np
from test_notebook_simple import model,INITIAL,SOT
from fimrun.micromagnetics import Uniform,Antiparallel,RunResult,OVF
from fimrun.micromagnetics.initial import generate
from fimrun.micromagnetics.native import Native,EVALUATIONS
from fimrun.notebook import NotebookSimulation,CellStopped,_ACTIVE_NOTEBOOKS


class ZeroReplacementOVF(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.parent=Path(self.temp.name).resolve()
        self.before=dict(EVALUATIONS)
        self.forbidden=patch.object(Native,'__init__',side_effect=AssertionError('native construction forbidden'))
        self.forbidden.start()

    def tearDown(self):
        try:
            for sim in list(_ACTIVE_NOTEBOOKS.values()):
                if sim.directory.is_relative_to(self.parent):sim.close()
            self.assertEqual(self.before,EVALUATIONS)
        finally:self.forbidden.stop();self.temp.cleanup()

    def create(self, **kw):
        opts=dict(model=model(),initial=INITIAL,dt=1e-15,results=self.parent)
        opts.update(kw);return NotebookSimulation(**opts)

    def test_default_reset_and_opt_out_old_files_and_references(self):
        old=self.create();saved=old.save('old.state');data=Path(saved['path']).read_bytes()
        new=self.create(initial=Antiparallel(Uniform((1.,0.,0.))))
        self.assertTrue(old.closed);self.assertFalse(new.closed)
        self.assertNotEqual(new.directory,old.directory);self.assertNotEqual(new.run_id,old.run_id)
        self.assertEqual(new.time,0.);self.assertIsNone(new._session.sim.current)
        self.assertEqual(new._session.sim.events[-1]['kind'],'notebook_reset')
        self.assertEqual(data,Path(saved['path']).read_bytes())
        with self.assertRaisesRegex(RuntimeError,'closed or replaced'):old.run(1e-15)
        with self.assertRaises(RuntimeError):self.create(replace=False)
        self.assertFalse(new.closed)
        with self.assertRaises(RuntimeError):NotebookSimulation.load(saved['path'],results=self.parent,name='experiment')

    def test_preflight_and_setup_failures_preserve_old_state_and_history(self):
        old=self.create();core=old._session.sim;history=object();core._sd=history
        before=(old.run_id,old.directory,old.time,old.dt,list(core.events),list(core.segments))
        bads=({'initial':'bad'}, {'dt':0.}, {'snapshots':1.5e-15}, {'preview':1},
              {'replace':'yes'}, {'snapshot_format':'bad'}, {'scalars':['time']})
        for bad in bads:
            with self.subTest(bad=bad),self.assertRaises((TypeError,ValueError)):self.create(**bad)
            self.assertFalse(old.closed);self.assertIs(core._sd,history)
            self.assertEqual((old.run_id,old.directory,old.time,old.dt,list(core.events),list(core.segments)),before)
        with patch('fimrun.notebook.NotebookSession._claim',side_effect=PermissionError('setup failure')):
            with self.assertRaises(PermissionError):self.create()
        self.assertFalse(old.closed);self.assertIs(core._sd,history)
        with patch.object(old,'close',side_effect=RuntimeError('close failed')):
            with self.assertRaises(RuntimeError):self.create()
        self.assertIs(_ACTIVE_NOTEBOOKS[old._key],old)
        self.assertFalse(old.closed);core._sd=None
        with patch.object(core,'run',return_value=RunResult('completed',0.,0.,0,None,None,'test')):
            self.assertEqual(old.run(0.).status,'completed')

    def test_busy_thread_and_reentrant_run_and_relax_reject_reset_before_preparation(self):
        sim=self.create();core=sim._session.sim
        for method in ('run','relax'):
            entered=threading.Event();release=threading.Event();errors=[]
            def operation(**kwargs):
                entered.set()
                if not release.wait(3):raise AssertionError('test release timed out')
                return RunResult('completed',0.,0.,0,None,None,'test')
            def worker():
                try:sim.run(0.) if method=='run' else sim.relax(1.)
                except BaseException as error:errors.append(error)
            with patch.object(core,method,side_effect=operation):
                thread=threading.Thread(target=worker);thread.start();self.assertTrue(entered.wait(2))
                try:
                    with patch('fimrun.notebook.NotebookSession.start') as start:
                        with self.assertRaisesRegex(RuntimeError,'busy'):self.create()
                        start.assert_not_called()
                    with self.assertRaisesRegex(RuntimeError,'busy'):sim.close()
                finally:release.set();thread.join(3)
            self.assertFalse(thread.is_alive());self.assertEqual(errors,[]);self.assertFalse(sim.closed)
        def reentrant(**kwargs):
            with self.assertRaisesRegex(RuntimeError,'busy'):self.create()
            return RunResult('completed',0.,0.,0,None,None,'test')
        with patch.object(core,'run',side_effect=reentrant):sim.run(0.)

    def test_same_port_handoff_and_nonfatal_post_commit_preview(self):
        occupied={}
        def start(display):
            if display.port in occupied:raise AssertionError('old port still active')
            occupied[display.port]=display;display.server=object()
        def close(display):
            if occupied.get(display.port) is display:del occupied[display.port]
            display.server=None
        with patch('fimrun.micromagnetics.preview.LivePreview.start',start),patch('fimrun.micromagnetics.preview.LivePreview.close',close):
            old=self.create(preview=True,preview_port=18981);display=old._session.sim._preview
            new=self.create(preview=True,preview_port=18981)
            self.assertTrue(old.closed);self.assertIsNone(display.server)
            self.assertIs(occupied[18981],new._session.sim._preview)
            new.close();self.assertEqual(occupied,{})
        # A scientific replacement stays successful even if optional display fails.
        old=self.create()
        with patch('fimrun.micromagnetics.preview.LivePreview.start',side_effect=RuntimeError('preview fail')):
            with self.assertWarns(RuntimeWarning):new=self.create(preview=True)
        self.assertTrue(old.closed);self.assertFalse(new.closed)
        self.assertIs(_ACTIVE_NOTEBOOKS[new._key],new)

    def test_ovf_pair_no_field_readback_units_time_and_safe_names(self):
        sim=self.create();before=(sim.m,sim.time,dict(EVALUATIONS))
        receipt=sim.export_ovf('initial');self.assertTrue(receipt['complete'])
        self.assertEqual(receipt['time_s'],0.);self.assertEqual(set(receipt['sublattices']),{'A','B'})
        loaded=generate(model(),{label:OVF(path=entry['path'],quantity='direction') for label,entry in receipt['sublattices'].items()})
        np.testing.assert_allclose(loaded,before[0],rtol=0,atol=1e-15)
        for i,label in enumerate(('A','B')):
            path=Path(receipt['sublattices'][label]['path'])
            self.assertIn('# valueunits: 1 1 1',path.read_text())
            np.testing.assert_array_equal(np.loadtxt(path).reshape(1,3,3,3),before[0][i])
        for name in ('initial','../escape','/tmp/escape','x/y'):
            with self.assertRaises((ValueError,FileExistsError)):sim.export_ovf(name)
        self.assertEqual(sim.time,before[1]);self.assertEqual(EVALUATIONS,before[2])
        np.testing.assert_array_equal(sim.m,before[0])

    def test_partial_pair_never_complete_and_no_target_overwrite(self):
        sim=self.create()
        import os
        link=os.link
        def fail_b(source,target):
            if Path(target).name=='B.ovf':raise OSError('second publication failed')
            return link(source,target)
        with patch('fimrun.notebook_output.os.link',side_effect=fail_b):
            with self.assertRaises(OSError):sim.export_ovf('partial')
        packet=sim.directory/'exports/partial'
        self.assertFalse((packet/'manifest.json').exists());self.assertTrue((packet/'INCOMPLETE').exists())
        with self.assertRaises(FileExistsError):sim.export_ovf('partial')
        foreign=self.parent/'foreign';foreign.mkdir()
        (sim.directory/'exports/link').symlink_to(foreign,target_is_directory=True)
        with self.assertRaises(ValueError):sim.export_ovf('link')
        self.assertEqual(list(foreign.iterdir()),[])

    def test_ovf_and_none_format_roundtrip_and_legacy_default(self):
        for fmt in ('ovf',None,'npz'):
            sim=self.create(snapshot_format=fmt,snapshots=1e-15)
            saved=sim.save('initial.state');sim.close()
            loaded=NotebookSimulation.load(saved['path'],results=self.parent)
            self.assertEqual(loaded.snapshot_format,fmt)
            if fmt is None:self.assertIsNone(loaded._session.sim.outputs.snapshots)
            checkpoint=loaded.save('strict.state',checkpoint=True);loaded.close()
            strict=NotebookSimulation.load(checkpoint['path'],results=self.parent,checkpoint=True)
            self.assertEqual(strict.snapshot_format,fmt)
            with self.assertRaises(ValueError):strict.set_current(SOT)
            strict.close()

    def test_failed_stage_final_and_viewer_are_independent_of_snapshot_files(self):
        sim=self.create(snapshot_format='ovf',snapshots=1e-15)
        core=sim._session.sim
        with patch.object(core,'_current_evaluation',side_effect=RuntimeError('field failure')),contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaises(CellStopped):sim.run(1e-15)
        self.assertEqual(core.last_result.status,'failed')
        frames=list(sim.directory.rglob('manifest.json'));self.assertEqual(len(frames),1)
        self.assertEqual(json.loads(frames[0].read_text())['time_s'],0.)
        self.assertTrue(list(sim.directory.rglob('accepted.state')))
        sim.close()
        def start(display):display.server=object()
        def close(display):display.server=None
        with patch('fimrun.micromagnetics.preview.LivePreview.start',start),patch('fimrun.micromagnetics.preview.LivePreview.close',close):
            nofiles=self.create(snapshot_format=None,snapshots=1e-15,preview=True)
            nofiles._session.sim._preview.publish(force=True)
            self.assertFalse(list(nofiles.directory.rglob('*.ovf')))
            self.assertFalse(list(nofiles.directory.rglob('*.npz')))
            self.assertEqual(nofiles.metrics()['fields'],0)
            nofiles.close()


class FiniteReplacementOVF(unittest.TestCase):
    def create(self,parent,**kw):
        opts=dict(model=model(),initial=INITIAL,dt=1e-15,results=parent);opts.update(kw)
        return NotebookSimulation(**opts)

    def test_output_formats_exact_trajectory_counts_restore_and_cancel(self):
        with tempfile.TemporaryDirectory() as folder:
            sims=[]
            try:
                for fmt in ('npz','ovf',None):
                    sim=self.create(Path(folder)/str(fmt),snapshots=2e-15,snapshot_format=fmt)
                    sim.set_current(SOT);sim.run(3e-15);sims.append(sim)
                for sim in sims[1:]:
                    np.testing.assert_array_equal(sim.m,sims[0].m)
                    np.testing.assert_array_equal(sim.dissipation,sims[0].dissipation)
                    np.testing.assert_array_equal(sim.drive_work,sims[0].drive_work)
                    self.assertEqual(sim.time,sims[0].time)
                    self.assertEqual(sim.metrics()['fields'],sims[0].metrics()['fields'])
                self.assertTrue(list(sims[0].directory.rglob('m-*.npz')))
                self.assertFalse(list(sims[0].directory.rglob('*.ovf')))
                packets=list(sims[1].directory.rglob('manifest.json'));self.assertEqual(len(packets),3)
                self.assertFalse(list(sims[1].directory.rglob('*.npz')))
                self.assertFalse(list(sims[2].directory.rglob('*.ovf')))
                self.assertFalse(list(sims[2].directory.rglob('*.npz')))
                for sim in sims:self.assertTrue(list(sim.directory.rglob('accepted.state')))
                last=max(packets,key=lambda p:json.loads(p.read_text())['time_s']);frame=json.loads(last.read_text())
                self.assertEqual(frame['time_s'],sims[1].time)
                read=generate(model(),{label:OVF(path=entry['path'],quantity='direction') for label,entry in frame['sublattices'].items()})
                np.testing.assert_allclose(read,sims[1].m,rtol=0,atol=1e-15)
                saved=sims[1].save('saved.state');sims[1].close()
                loaded=NotebookSimulation.load(saved['path'],results=folder,name='loaded')
                try:
                    self.assertEqual(loaded.snapshot_format,'ovf');loaded.run(1e-15)
                    self.assertFalse(list(loaded.directory.rglob('*.npz')))
                    self.assertTrue(list(loaded.directory.rglob('*.ovf')))
                finally:loaded.close()
                cancel=self.create(Path(folder)/'cancel',snapshots=3e-15,snapshot_format='ovf')
                sims.append(cancel);core=cancel._session.sim;step=core._rk4_step;count=0
                def interrupt():
                    nonlocal count
                    if count==1:raise KeyboardInterrupt
                    step();count+=1
                with patch.object(core,'_rk4_step',side_effect=interrupt),contextlib.redirect_stdout(io.StringIO()):
                    with self.assertRaises(CellStopped):cancel.run(3e-15)
                self.assertEqual(cancel.time,1e-15)
                frames=[json.loads(p.read_text()) for p in cancel.directory.rglob('manifest.json')]
                self.assertEqual(sorted(f['time_s'] for f in frames),[0.,1e-15])
            finally:
                for sim in sims:sim.close()

    def test_failed_reset_keeps_continuation_success_resets_and_static_final(self):
        with tempfile.TemporaryDirectory() as folder:
            old=self.create(folder);new=static=None
            try:
                old.run(1e-15);old.set_current(SOT);before=old.m;time=old.time
                with self.assertRaises(ValueError):self.create(folder,initial='bad')
                np.testing.assert_array_equal(old.m,before);self.assertEqual(old.time,time);self.assertFalse(old.closed)
                old.run(1e-15)
                state=old.save('old.state');data=Path(state['path']).read_bytes()
                new=self.create(folder,initial=Antiparallel(Uniform((1.,0.,0.))))
                self.assertTrue(old.closed);self.assertIsNone(old._session.sim._native)
                self.assertEqual(new.time,0.);self.assertIsNone(new._session.sim.current)
                new.run(1e-15);self.assertEqual(data,Path(state['path']).read_bytes())
                static=self.create(Path(folder)/'static',snapshots=1e-15,snapshot_format='ovf')
                static.relax(1.);self.assertEqual(static.time,0.)
                packets=list(static.directory.rglob('manifest.json'));self.assertEqual(len(packets),1)
                self.assertEqual(json.loads(packets[0].read_text())['time_s'],0.)
            finally:
                old.close()
                if new:new.close()
                if static:static.close()
