"""New names are thin aliases, with zero-native preflight/serialization tests."""
import contextlib,copy,io,json,tempfile,unittest,warnings
from pathlib import Path
from unittest.mock import patch
import numpy as np
from fimrun.notebook import NotebookSimulation,CellStopped
from fimrun.micromagnetics.native import Native,EVALUATIONS
from fimrun.postprocess.io import read_ovf,read_state
from fimrun.postprocess import frames_from_state
from fimrun.postprocess.pipeline import resolve
from test_notebook_usability import model
from fimrun.micromagnetics import Uniform,Antiparallel

class SaveNames(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name).resolve();self.sims=[];self.before=dict(EVALUATIONS);self.no=patch.object(Native,'__init__',side_effect=AssertionError('Native forbidden'));self.no.start()
 def tearDown(self):
  for s in self.sims:s.close()
  self.no.stop();self.assertEqual(self.before,EVALUATIONS);self.temp.cleanup()
 def create(self,**kw):
  sim=NotebookSimulation(model=model(),initial=Antiparallel(Uniform((0.,0.,1.))),dt=1e-15,output_dir=self.root,**kw);self.sims.append(sim);core=sim._session.sim;core._field=np.zeros_like(core._m);core._energy=np.zeros(2);return sim
 def test_defaults_cross_stage_restore_and_metadata(self):
  sim=self.create(save_interval=2e-15)
  sim.run(0.,output_name='dyn');sim.relax(mxh=1e-5,output_name='stat',save_every_steps=2)
  self.assertEqual(sim._flat_outputs.cadences,{'rk4':2e-15,'sdesc':2})
  sim.run(0.,output_name='next',save_interval=None)
  self.assertEqual(sim._flat_outputs.cadences,{'rk4':None,'sdesc':2})
  state,b=read_state(self.root/'next.state');self.assertIsNone(state['notebook_flat']['every'])
  with warnings.catch_warnings(record=True) as w:
   restored=NotebookSimulation.load(self.root/'stat.state',output_dir=self.root/'restored');self.sims.append(restored)
  self.assertFalse(w);self.assertEqual(restored._flat_outputs.cadences,{'rk4':2e-15,'sdesc':2})
  d=read_ovf(self.root/'dyn_ovf/rk4-000000000000_A.ovf')
  for k in ('run_id','segment_id','boundary','mirrors','time_s','accepted_index'):self.assertIn(k,d['fields'])
  self.assertEqual(d['legacy_missing_header'],[]);self.assertEqual(d['label'],'A')
  frames=frames_from_state(self.root/'dyn.state');self.assertEqual(len(frames),1)
  arrays,meta,binding=resolve(frames[0]);self.assertEqual(set(arrays),{'A','B'});self.assertEqual(meta['stage'],'rk4');self.assertEqual(meta['time_s'],0.)
  self.assertIn('row_key',binding['sources']['csv'])
  source=self.root/'dyn_ovf/rk4-000000000000_A.ovf';source.write_bytes(source.read_bytes()+b'\n')
  with self.assertRaisesRegex(ValueError,'inventory'):frames_from_state(self.root/'dyn.state')
 def test_conflicts_stage_misuse_and_decline_have_no_side_effects(self):
  sim=self.create();sim.run(0.);core=sim._session.sim
  before=(sim.m.tobytes(),sim.dt,copy.deepcopy(core.events),copy.deepcopy(core.segments),copy.deepcopy(sim._flat_outputs.cadences),sim.output_name)
  calls=[lambda:sim.run(0.,every=None,save_interval=None),lambda:sim.relax(mxh=1e-5,every=None,save_every_steps=None),lambda:sim.run(0.,save_every_steps=1),lambda:sim.relax(mxh=1e-5,save_interval=1e-15),lambda:sim.relax(mxh=1e-5,save_every_steps=True),lambda:sim.run(0.,save_interval=1.5e-15)]
  with patch('builtins.input') as ask:
   for call in calls:
    with self.assertRaises((ValueError,TypeError)):call()
   ask.assert_not_called()
  with patch('builtins.input',return_value='NO'),contextlib.redirect_stdout(io.StringIO()):
   with self.assertRaises(CellStopped):sim.run(0.,dt=2e-15,save_interval=None)
  self.assertEqual(before,(sim.m.tobytes(),sim.dt,core.events,core.segments,sim._flat_outputs.cadences,sim.output_name))
 def test_alias_warning_and_new_names_rejected_in_legacy_path(self):
  with self.assertWarns(FutureWarning):sim=self.create(every=None)
  with self.assertWarns(FutureWarning):sim.run(0.,every=None,output_name='new')
  with self.assertWarns(FutureWarning):sim.relax(mxh=1e-5,every=1,output_name='static')
  with self.assertRaises(TypeError):NotebookSimulation(model=model(),initial=Antiparallel(Uniform((0.,0.,1.))),dt=1e-15,results=self.root/'legacy',save_interval=None)
  with self.assertRaises(TypeError):self.create(save_interval=None,every=None)
  with self.assertRaises(TypeError):self.create(save_every_steps=1)
