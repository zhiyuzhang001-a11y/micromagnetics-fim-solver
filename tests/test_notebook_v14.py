"""No-native acceptance of the simplified facade, sampling and cache contract."""
import contextlib,copy,csv,hashlib,io,json,tempfile,unittest,zipfile
from pathlib import Path
from unittest.mock import patch
import numpy as np
from fimrun.notebook import NotebookSimulation,NotebookSession,CellStopped,_ACTIVE_NOTEBOOKS
from fimrun.notebook_flat import metadata
from fimrun.micromagnetics import Antiparallel,Uniform
from fimrun.micromagnetics.native import Native,EVALUATIONS
from fimrun.micromagnetics.simulation import energy_columns,Simulation
from test_notebook_simple import model,INITIAL,SOT

class V14(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name).resolve();self.fields=dict(EVALUATIONS)
  self.no=patch.object(Native,'__init__',side_effect=AssertionError('native forbidden'));self.no.start()
  self.no_preview=patch.object(Simulation,'_start_preview');self.no_preview.start()
  self.viewer=patch.object(NotebookSession,'preview',autospec=True);self.opened=self.viewer.start()
 def tearDown(self):
  for sim in list(_ACTIVE_NOTEBOOKS.values()):
   if sim.directory.is_relative_to(self.root):sim.close()
  self.viewer.stop();self.no_preview.stop();self.no.stop();self.assertEqual(EVALUATIONS,self.fields);self.temp.cleanup()
 def create(self,**kw):return NotebookSimulation(model=model(),initial=INITIAL,output_dir=self.root,**kw)
 def cached(self,sim):
  c=sim._session.sim;c._field=np.zeros_like(c._m);c._energy=np.arange(7,dtype=float);return c
 def state(self,sim):
  c=sim._session.sim
  return (sim.m.tobytes(),sim.time,sim.dt,copy.deepcopy(c.events),copy.deepcopy(c.segments),copy.deepcopy(c.current),copy.deepcopy(sim._flat_outputs.settings),copy.deepcopy(sim._flat_outputs.cadences))
 def test_simple_initial_no_dt_and_preview(self):
  sim=self.create();self.assertIsNone(sim.dt);self.assertEqual(sim.time,0);self.opened.assert_called_once()
  self.assertEqual(len(sim._flat_outputs.settings['scalars']),7);self.assertTrue(sim._flat_outputs.settings['magnetization']);self.assertNotIn('structure',sim._flat_outputs.settings['scalars'])
  self.assertIn('dt=None',repr(sim));sim._session.sim._preview=None
  from fimrun.micromagnetics.preview import LivePreview
  p=LivePreview(sim._session.sim,0);p.publish(force=True);self.assertIsNone(p.latest['state']['dt_fs'])
  with self.assertRaisesRegex(ValueError,'requires dt'):sim.run(0.,name='no_dt')
  self.assertFalse(list(self.root.glob('no_dt*')))
 def test_static_without_dt_roundtrip_and_energy(self):
  sim=self.create();c=self.cached(sim);sim.relax(name='static',mxh=1e-5,save_step=2)
  self.assertIsNone(sim.dt);self.assertEqual(sim.time,0);rows=list(csv.DictReader(io.StringIO((self.root/'static.csv').read_text())));self.assertEqual(len(rows),1)
  row=rows[0];parts=[float(v) for k,v in row.items() if k.startswith('energy_') and k not in ('energy_J','energy_total_J')]
  self.assertEqual(sum(parts),float(row['energy_total_J']));self.assertEqual(row['energy_J'],row['energy_total_J'])
  self.assertEqual(len(list((self.root/'static_ovf').glob('*.ovf'))),2)
  restored=NotebookSimulation.load(self.root/'static.state',output_dir=self.root/'restore',name='continue')
  self.assertIsNone(restored.dt);self.assertEqual(restored._flat_outputs.cadences['sdesc'],2)
  self.cached(restored);restored.run(duration=0.,dt=1e-15,name='dynamic');self.assertEqual(restored.dt,1e-15)
 def test_preflight_is_atomic(self):
  sim=self.create();self.cached(sim);before=self.state(sim)
  bad=[lambda:sim.run(0.,name='a',output_name='a',dt=1e-15),lambda:sim.relax(name='a',output_name='a',mxh=1e-5),lambda:sim.relax(mxh=1e-5,save_step=None,save_every_steps=None),lambda:sim.relax(mxh=1e-5,save_step=True),lambda:sim.run(1.5e-15,dt=1e-15,name='bad'),lambda:sim.run(0.,dt=1e-15,save_interval=1.5e-15),lambda:sim.run(0.,dt=1e-15,name='../bad')]
  for call in bad:
   with self.assertRaises((ValueError,TypeError)):call()
   self.assertEqual(before,self.state(sim))
  self.assertEqual(list(self.root.iterdir()),[])
  sim.run(0.,dt=1e-15,name='exists');before=self.state(sim)
  with patch('builtins.input',return_value='NO'),contextlib.redirect_stdout(io.StringIO()):
   with self.assertRaises(CellStopped):sim.run(0.,dt=2e-15,name='exists',save_interval=None)
  self.assertEqual(before,self.state(sim))
 def test_frequency_inherit_none_and_legacy_defaults(self):
  sim=self.create(dt=1e-15,save_interval=2e-15)
  self.assertEqual(sim._flat_outputs.settings['scalars'],('time','mean_m'));self.opened.assert_not_called();self.cached(sim)
  sim.run(0.,name='one');sim.relax(name='two',mxh=1e-5,save_step=3)
  self.assertEqual(sim._flat_outputs.cadences,{'rk4':2e-15,'sdesc':3})
  sim.run(0.,name='three',save_interval=None);sim.relax(name='four',mxh=1e-5)
  self.assertEqual(sim._flat_outputs.cadences,{'rk4':None,'sdesc':3})
 def test_reset_closed_and_missing_energy(self):
  sim=self.create();fresh=self.create();self.assertTrue(sim.closed);self.assertNotEqual(sim.run_id,fresh.run_id)
  with self.assertRaises(RuntimeError):sim.preview()
  values=energy_columns(None,fresh._session.sim.model);self.assertTrue(all(v=='' for v in values.values()))
  fresh.close()
  with self.assertRaises(RuntimeError):fresh.preview()

if __name__=='__main__':unittest.main(verbosity=2)
