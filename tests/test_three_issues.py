"""Three interaction fixes. Synthetic/cached data only, no native science."""
import copy,json,math,re,socket,tempfile,unittest,warnings
from pathlib import Path
from dataclasses import replace
from unittest.mock import patch,MagicMock
import xml.etree.ElementTree as ET
import numpy as np
from fimrun.notebook import NotebookSimulation,_ACTIVE_NOTEBOOKS,CellStopped
from fimrun.micromagnetics.native import Native,EVALUATIONS
from fimrun.micromagnetics.preview import _OWNED_PORTS,_RETIRED_PORTS
from fimrun.postprocess.analysis import Analysis,_TOKEN
from fimrun.confirmation import confirm_overwrite,key_allowed,PressReleaseGate,_dialog
from test_notebook_simple import model,INITIAL

class ThreeIssues(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name).resolve();self.before=dict(EVALUATIONS)
  self.g1=patch.object(Native,'__init__',side_effect=AssertionError('no Native'));self.g1.start()
  self.g2=patch.object(Native,'evaluate',side_effect=AssertionError('no fields'));self.g2.start()
  self.browser=patch('webbrowser.open',return_value=True);self.open=self.browser.start()
 def tearDown(self):
  for sim in list(_ACTIVE_NOTEBOOKS.values()):
   if sim.directory.is_relative_to(self.root):sim._session.sim._busy=False;sim.close()
  self.browser.stop();self.g1.stop();self.g2.stop();self.assertEqual(self.before,EVALUATIONS);self.temp.cleanup()
 def make(self,name):
  s=NotebookSimulation(model=model(),initial=INITIAL,output_dir=self.root/name,preview=False)
  c=s._session.sim;c._field=np.zeros_like(c._m);c._energy=np.zeros(7);return s
 def port(self):
  with socket.socket() as s:s.bind(('127.0.0.1',0));return s.getsockname()[1]
 def enable(self,s,port):
  c=s._session.sim;c.set_outputs(replace(c.outputs,preview=True,preview_port=port));s.preview();return c._preview
 def test_idle_same_channel_handoff_keeps_sim_and_engine(self):
  a,b=self.make('a'),self.make('b');port=self.port();v=self.enable(a,port)
  old=a._session.sim;before=old.m.copy();self.enable(b,port)
  self.assertIs(b._session.sim._preview,v);self.assertIsNone(old._preview);self.assertFalse(a.closed)
  np.testing.assert_array_equal(before,old.m);self.assertIsNone(old._native);self.assertEqual(self.open.call_count,1)
  self.assertIn(b.run_id,v.url);self.assertEqual(v.binding_epoch,1)
 def test_close_then_load_twice_preserves_channel_capability(self):
  a=self.make('a');port=self.port();v=self.enable(a,port);instance=v.instance
  a.save('start.state');path=a.output_dir/'start.state';seq=v.sequence;a.close()
  b=NotebookSimulation.load(path,output_dir=self.root/'b');v2=b._session.sim._preview
  self.assertIsNotNone(v2.server);self.assertEqual(v2.instance,instance);self.assertGreater(v2.sequence,seq)
  b.close();c=NotebookSimulation.load(path,output_dir=self.root/'c');v3=c._session.sim._preview
  self.assertEqual(v3.instance,instance);self.assertGreater(v3.binding_epoch,v2.binding_epoch)
  self.assertEqual(self.open.call_count,1)
 def test_foreign_listener_is_not_closed_and_retry_works(self):
  s=self.make('s');foreign=socket.socket();foreign.bind(('127.0.0.1',0));foreign.listen();port=foreign.getsockname()[1]
  try:
   with self.assertWarns(RuntimeWarning):failed=self.enable(s,port)
   self.assertIsNone(failed.server);self.assertGreaterEqual(foreign.fileno(),0);self.assertNotIn(port,_OWNED_PORTS)
  finally:foreign.close()
  s.preview();self.assertIsNotNone(s._session.sim._preview.server)
 def test_busy_owner_is_not_stolen(self):
  a,b=self.make('a'),self.make('b');port=self.port();v=self.enable(a,port);a._session.sim._busy=True
  try:
   with self.assertWarns(RuntimeWarning):self.enable(b,port)
   self.assertIs(a._session.sim._preview,v);self.assertIsNone(b._session.sim._preview.server);self.assertTrue(v.handoff_notice)
  finally:a._session.sim._busy=False
  b.preview();self.assertIs(b._session.sim._preview,v);self.assertIsNone(v.handoff_notice)
 def test_failed_handoff_rolls_back_and_retries(self):
  a,b=self.make('a'),self.make('b');port=self.port();v=self.enable(a,port);before=v.latest
  with patch.object(v,'publish',side_effect=ValueError('fixture source unavailable')):
   with self.assertWarns(RuntimeWarning):self.enable(b,port)
  self.assertIs(v.sim,a._session.sim);self.assertIs(v.latest,before);self.assertTrue(v.handoff_error)
  b.preview();self.assertIs(v.sim,b._session.sim);self.assertIsNone(v.handoff_error)
 def test_interrupt_during_rebind_rolls_back_all_channel_state_then_retries(self):
  a,b=self.make('a'),self.make('b');port=self.port();v=self.enable(a,port)
  attributes=('sim','epoch_offset','binding_epoch','sequence','epoch','url','latest','last_publish')
  before={k:getattr(v,k) for k in attributes};frames=v.frames.copy();cache=v.frame_cache.copy()
  with patch.object(v,'publish',side_effect=KeyboardInterrupt):
   with self.assertRaises(KeyboardInterrupt):self.enable(b,port)
  for k,value in before.items():self.assertEqual(getattr(v,k),value)
  self.assertEqual(v.frames,frames);self.assertEqual(v.frame_cache,cache)
  self.assertIs(a._session.sim._preview,v);self.assertIsNone(b._session.sim._preview)
  b.preview();self.assertIs(b._session.sim._preview,v);self.assertIsNone(a._session.sim._preview)
 def test_periodic_untracked_relative_displacement_is_unavailable(self):
  rows=self.rows()
  for r in rows:r['valid_tracking']=False
  rows[0]['A_area_x']=499e-9;rows[1]['A_area_x']=1e-9
  svg=self.analysis(rows).plot('center').data
  self.assertIn('位移不可用',svg)
  tree=ET.fromstring(svg)
  self.assertFalse([x for x in tree.iter() if x.tag.endswith('circle') or x.tag.endswith('path') and x.get('data-series')])
 def test_different_ports_remain_independent(self):
  a,b=self.make('a'),self.make('b');x=self.enable(a,self.port());y=self.enable(b,self.port())
  self.assertIsNot(x,y);self.assertIs(x.sim,a._session.sim);self.assertIs(y.sim,b._session.sim)
 def rows(self):
  rows=[]
  for i,(x,y) in enumerate([(250.,250.),(248.9,270.)]):
   r=dict(run_id='r',segment_id='s',stage='rk4',time_s=i*1e-9,valid_tracking=True,tracking_part=0,boundary='periodic_xy',source_bindings='{}')
   for label in ('A','B'):
    r.update({label+'_valid_geometry':True,label+'_area_unwrapped_x':x*1e-9,label+'_area_unwrapped_y':y*1e-9,label+'_area_x':x*1e-9,label+'_area_y':y*1e-9})
   rows.append(r)
  return rows
 def analysis(self,rows):return Analysis(_TOKEN,rows,range(len(rows)),(),())
 def test_default_center_delta_xy_equal_scale_and_immutable(self):
  a=self.analysis(self.rows());before=copy.deepcopy(a._rows);svg=a.plot('center',sublattice='both').data
  self.assertIn('Δy / nm',svg);self.assertIn('Δx / nm',svg);self.assertIn('(0,0)',svg)
  tree=ET.fromstring(svg);lines=[x for x in tree.iter() if x.tag.endswith('path') and x.get('data-series')]
  self.assertEqual(len(lines),2)
  x0,y0,x1,y1=map(float,re.findall(r'[-+]?\d+(?:\.\d+)?',lines[0].get('d')))
  self.assertAlmostEqual((y1-y0)/(x1-x0),20/1.1,places=7)
  self.assertEqual(a._rows,before)
 def test_explicit_time_curves_and_legacy_absolute_xy(self):
  a=self.analysis(self.rows());self.assertIn('时间 / ps',a.plot('center',trajectory=False).data)
  self.assertIn('X / nm',a.plot('center',trajectory=True).data)
  self.assertNotIn('Δx / nm',a.plot('center',trajectory=True).data)
 def test_center_gaps_segments_and_unasserted_tracking_no_wrong_lines(self):
  for mode in ('invalid','segment','untracked'):
   rows=self.rows()
   if mode=='invalid':rows[1]['A_valid_geometry']=rows[1]['B_valid_geometry']=False
   if mode=='segment':rows[1]['segment_id']='other'
   if mode=='untracked':
    for r in rows:r['valid_tracking']=False
   svg=ET.fromstring(self.analysis(rows).plot('center').data)
   self.assertFalse([x for x in svg.iter() if x.tag.endswith('path') and x.get('data-series')])
 def test_confirmation_focus_and_modifier_gating(self):
  self.assertTrue(key_allowed(focused=True,armed=True,modifiers=0))
  for state in [(False,True,0),(True,False,0),(True,True,1),(True,True,4),(True,True,8),(True,True,16),(True,True,128)]:
   self.assertFalse(key_allowed(focused=state[0],armed=state[1],modifiers=state[2]))
 def test_ignored_held_enter_requires_release_not_elapsed_time(self):
  gate=PressReleaseGate()
  self.assertFalse(gate.press('Return',focused=True,armed=False,modifiers=0))
  for _ in range(50):self.assertFalse(gate.press('Return',focused=True,armed=True,modifiers=0))
  gate.release('Return')
  self.assertTrue(gate.press('Return',focused=True,armed=True,modifiers=0))
 def test_launch_key_held_before_first_repeat_and_modifier_release(self):
  gate=PressReleaseGate({'Return'})
  self.assertFalse(gate.press('Return',focused=True,armed=True,modifiers=0))
  gate.startup.clear() # physical polling alone must not turn repeats into consent
  self.assertFalse(gate.press('Return',focused=True,armed=True,modifiers=0))
  gate.release('Return')
  self.assertFalse(gate.press('Return',focused=True,armed=True,modifiers=4))
  self.assertFalse(gate.press('Return',focused=True,armed=True,modifiers=0))
  gate.release('Return');self.assertTrue(gate.press('Return',focused=True,armed=True,modifiers=0))
 def test_actual_dialog_handlers_reject_repeat_then_accept_new_press(self):
  import sys,types
  for release_then_new in (False,True):
   tk=MagicMock();ttk=MagicMock();tk.ttk=ttk;root=tk.Tk.return_value
   bindings={};timers=[];protocols={}
   root.bind.side_effect=lambda event,fn:bindings.update({event:fn})
   root.after.side_effect=lambda ms,fn:timers.append((ms,fn))
   root.protocol.side_effect=lambda event,fn:protocols.update({event:fn})
   def mainloop():
    event=types.SimpleNamespace(state=0)
    bindings['<Return>'](event)
    for ms,fn in list(timers):
     if ms==350:fn()
    for _ in range(20):bindings['<Return>'](event)
    root.destroy.assert_not_called()
    self.assertIn('<KeyRelease-Return>',bindings)
    if release_then_new:
     bindings['<KeyRelease-Return>'](event);bindings['<Return>'](event)
    else:protocols['WM_DELETE_WINDOW']()
   root.mainloop.side_effect=mainloop
   with patch.dict(sys.modules,{'tkinter':tk,'tkinter.ttk':ttk}),patch('fimrun.confirmation.sys.platform','linux'):
    answer=_dialog(dict(nonce='held-enter',paths=['sample.csv']))
   self.assertEqual(answer['accepted'],release_then_new)
 def test_fallback_enter_cancel_eof_are_explicit(self):
  for value,expected in [('',True),('OVERWRITE',True),('cancel',False),('yes',False)]:
   with patch('fimrun.confirmation._in_kernel',return_value=False),patch('builtins.input',return_value=value):self.assertEqual(confirm_overwrite([Path('sample.csv')]),expected)
  with patch('fimrun.confirmation._in_kernel',return_value=False),patch('builtins.input',side_effect=EOFError):self.assertFalse(confirm_overwrite([Path('sample.csv')]))
 def test_cancel_close_interrupt_leave_outputs_config_and_state(self):
  s=self.make('a');s.run(name='same',dt=1e-15,duration=0)
  old=s._session.sim.m.copy();settings=copy.deepcopy(s._flat_outputs.settings)
  from fimrun.notebook_flat import inventory
  targets=[s.output_dir/'same.csv',s.output_dir/'same_ovf',s.output_dir/'same.state'];before=inventory(targets)
  for outcome in (False,KeyboardInterrupt):
   with patch('fimrun.confirmation.confirm_overwrite',side_effect=outcome if outcome is KeyboardInterrupt else None,return_value=False):
    with self.assertRaises(KeyboardInterrupt if outcome is KeyboardInterrupt else CellStopped):s.run(name='same',dt=2e-15,duration=0)
   self.assertEqual(inventory(targets),before);self.assertEqual(settings,s._flat_outputs.settings);np.testing.assert_array_equal(old,s._session.sim.m);self.assertFalse(s._in_operation)
 def test_interrupt_terminates_only_own_dialog_child(self):
  child=MagicMock();child.communicate.side_effect=KeyboardInterrupt;child.poll.return_value=None
  with patch('fimrun.confirmation._in_kernel',return_value=True),patch('fimrun.confirmation.subprocess.Popen',return_value=child):
   with self.assertRaises(KeyboardInterrupt):confirm_overwrite([Path('sample.csv')])
  child.terminate.assert_called_once();child.wait.assert_called_once()
