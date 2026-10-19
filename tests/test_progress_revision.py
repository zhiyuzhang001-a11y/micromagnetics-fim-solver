"""Zero-field contracts for progress, safe restore and bounded source reads."""
import copy,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import numpy as np
from fimrun.micromagnetics.native import Native,EVALUATIONS
from fimrun.micromagnetics import Outputs
from fimrun.notebook import NotebookSimulation,_ACTIVE_NOTEBOOKS
from fimrun.progress import simulation_snapshot,simulation_text,Progress
from fimrun.postprocess.session import Reads,tracked_reads,read_bytes
from test_notebook_simple import model,INITIAL,SOT

class Revision(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name).resolve();self.before=dict(EVALUATIONS)
  self.guard=patch.object(Native,'__init__',side_effect=AssertionError('native forbidden'));self.guard.start()
 def tearDown(self):
  for sim in list(_ACTIVE_NOTEBOOKS.values()):
   if sim.directory.is_relative_to(self.root):sim.close()
  self.guard.stop();self.assertEqual(EVALUATIONS,self.before);self.tmp.cleanup()
 def create(self):
  sim=NotebookSimulation(model=model(),initial=INITIAL,output_dir=self.root/'old',preview=False)
  c=sim._session.sim;c._field=np.zeros_like(c._m);c._energy=np.zeros(7);return sim
 def test_snapshot_partial_consecutive_and_units(self):
  sim=self.create();c=sim._session.sim
  c.segments=[dict(kind='sdesc',status='running',t_start=0.)];c._preview_stop={'tolerance':1.,'mxh':1e-5,'consecutive':3};c._sd={'consecutive':1,'residual_checked':True}
  snap=simulation_snapshot(c,[.5,.6]);self.assertEqual(snap['phase'],'running');self.assertEqual(snap['consecutive'],1)
  self.assertAlmostEqual(snap['convergence'][0]['mxh'],.5/model().material.A.Ms)
  self.assertIn('连续达标 1/3',simulation_text(snap));self.assertNotIn('已收敛',simulation_text(snap));c.segments=[];c._sd=None
 def test_changed_criterion_never_displays_old_streak(self):
  sim=self.create();c=sim._session.sim
  c.segments=[dict(kind='sdesc',status='running',t_start=0.)]
  c._preview_stop={'tolerance':1.,'mxh':1e-5,'consecutive':5}
  c._sd={'criterion':{'tolerance':1.,'mxh':1e-5,'consecutive':3},'consecutive':3,'residual_checked':True}
  snap=simulation_snapshot(c);self.assertEqual(snap['consecutive'],0);self.assertEqual(c._sd['consecutive'],3)
  c.segments=[];c._sd=None
 def test_zero_duration_progress_and_result(self):
  sim=self.create();result=sim.run(name='zero',dt=1e-15,duration=0,save_interval=None)
  snap=simulation_snapshot(sim._session.sim);self.assertEqual(snap['percent'],100);self.assertEqual(result.mxh,(0.,0.));self.assertEqual(result.accepted_steps,0)
 def test_safe_restore_failure_then_success_current(self):
  sim=self.create();sim.set_current(SOT);target=sim.save('source.state')['path'];m=sim.m.copy();run_id=sim.run_id
  with self.assertRaises(FileNotFoundError):sim.restore(self.root/'absent',output_dir=self.root/'new',backup='keep.state')
  self.assertFalse(sim.closed);self.assertEqual(sim.run_id,run_id);np.testing.assert_array_equal(sim.m,m)
  restored=sim.restore(target,output_dir=self.root/'new',backup='keep.state')
  self.assertEqual(simulation_snapshot(restored._session.sim)['phase'],'restored');self.assertIsNone(simulation_snapshot(restored._session.sim)['target_steps']);self.assertTrue(sim.closed);self.assertFalse(restored.closed);self.assertEqual(restored._session.sim.current,SOT);self.assertTrue((self.root/'old/keep.state').exists());self.assertFalse(restored._session.sim.events[-1]['reset_to_initial'])
 def test_backup_collision_keeps_old_open(self):
  sim=self.create();target=sim.save('target.state')['path'];sim.save('keep.state')
  with self.assertRaises(FileExistsError):sim.restore(target,output_dir=self.root/'new',backup='keep.state')
  self.assertFalse(sim.closed);sim.set_current(SOT);self.assertEqual(sim._session.sim.current,SOT)
 def test_missing_cache_does_not_claim_zero(self):
  sim=self.create();c=sim._session.sim;c._field=None;c._energy=None
  snap=simulation_snapshot(c);self.assertTrue(all(g['mxh'] is None for g in snap['convergence']))
  self.assertIn('待计算',simulation_text(snap))
 def test_history_has_own_progress_snapshot(self):
  from fimrun.micromagnetics.preview import LivePreview
  sim=self.create();c=sim._session.sim
  c.segments=[dict(kind='sdesc',status='running',t_start=0.,id='fixture',index=0)]
  c._preview_stop={'tolerance':1.,'mxh':1e-5,'consecutive':5};c._sd={'consecutive':1,'residual_checked':True}
  p=LivePreview(c,0);p.publish(force=True);first=p.latest
  c._sd['consecutive']=3;p.publish(force=True)
  self.assertEqual(first['frame']['progress']['consecutive'],1)
  self.assertEqual(p.latest['frame']['progress']['consecutive'],3)
  self.assertEqual(first['frame']['configuration']['stop']['consecutive'],5)
  c.segments=[];c._sd=None
 def test_rebind_url_matches_authorized_run(self):
  from fimrun.micromagnetics.preview import LivePreview
  sim=self.create();p=LivePreview(sim._session.sim,18768);p.rebind(sim._session.sim)
  self.assertIn('run_id='+sim.run_id,p.url);self.assertIn('instance='+p.instance,p.url)
 def test_output_failure_not_completed(self):
  from fimrun.notebook import CellStopped
  sim=self.create();c=sim._session.sim
  with patch.object(c,'save_state',side_effect=OSError('fixture output failure')):
   with self.assertRaises(CellStopped):sim.run(name='broken_output',dt=1e-15,duration=0)
  snap=simulation_snapshot(c);self.assertEqual(snap['phase'],'failed');self.assertIn('fixture output failure',str(snap['error']))
 def test_progress_throttle(self):
  log=[];p=Progress('test',interval=999,callback=log.append);p.update('start');p.update('hidden');p.update('end',force=True);self.assertEqual(log,['start','end'])
 def test_per_call_cache_bounds_and_mutation(self):
  p=self.root/'source';p.write_bytes(b'a');r=Reads();self.assertEqual(r.read(p),b'a');p.write_bytes(b'b')
  with self.assertRaises(ValueError):r.verify()
  @tracked_reads
  def once():return read_bytes(p)
  self.assertEqual(once(),b'b');p.write_bytes(b'c');self.assertEqual(once(),b'c')
  r=Reads();r.limit=4
  for n in range(5):
   q=self.root/str(n);q.write_bytes(b'12');r.read(q)
  self.assertLessEqual(r.bytes,4);self.assertLessEqual(len(r.raw),2)

if __name__=='__main__':unittest.main()
