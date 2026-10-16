"""No-field synthetic policy, control-flow, persistence and corruption regressions."""
from pathlib import Path
import argparse
import json
import math
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
import static_policy as p
import run_static
from check_residual import check_current
from make_fixture import make

ARGS,REST=argparse.ArgumentParser(add_help=False).parse_known_args()
BINARY=None
HIGH_CP=None
if '--static-binary' in REST:
 i=REST.index('--static-binary');BINARY=REST[i+1];REST=REST[:i]+REST[i+2:]
if '--high-checkpoint' in REST:
 i=REST.index('--high-checkpoint');HIGH_CP=REST[i+1];REST=REST[:i]+REST[i+2:]


class SyntheticPolicy(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.work=Path(self.tmp.name)
 def tearDown(self):self.tmp.cleanup()
 def cfg(self,value=1):
  x=self.work/'policy.json';p.write_json(x,{'policy_id':p.POLICY_ID,'requested_tolerance':{'value':value,'unit':'A/m'},'external_H_Apm':[0,0,-1]});return x
 def test_explicit_tolerance_and_provenance(self):
  for x in [.5,1.,2.]:self.assertEqual(p.resolve_policy(self.cfg(x))['requested_tolerance']['value'],x)
  for x in [0,-1,float('nan'),float('inf')]:
   with self.assertRaises(ValueError):p.tolerance(x)
  with self.assertRaises(ValueError):p.resolve_policy()
  side={'policy_id':p.POLICY_ID,'requested_tolerance':{'value':.5,'unit':'A/m'},'external_H_Apm':[0,0,-1]}
  r=p.resolve_policy(self.cfg(1),2,side);self.assertEqual(r['requested_tolerance']['value'],2);self.assertEqual(r['tolerance_provenance']['sidecar_value'],.5)
  self.assertEqual(p.resolve_policy(sidecar=side)['tolerance_provenance']['source'],'checkpoint_sidecar')
 def test_unverified_independent_and_timeout_never_success(self):
  native={'stop_reason':'residual_tolerance','native_candidate':True};yes={'status':'passed','achieved_A_Apm':.5,'achieved_B_Apm':1.}
  self.assertEqual(p.success_status(native,{'status':'not_checked'},True),'unverified')
  self.assertEqual(p.success_status(native,{'status':'failed'},True),'failed_independent_check')
  self.assertEqual(p.success_status(native,yes,False),'failed_independent_check')
  self.assertEqual(p.success_status(native,yes,True,True),'failed_timeout')
  self.assertEqual(p.success_status({'stop_reason':'step_budget','native_candidate':False},yes,True),'not_success')
  self.assertEqual(p.success_status(native,yes,True),'success')
  self.assertEqual(p.success_status(native,{**yes,'achieved_A_Apm':float('nan')},True),'failed_independent_check')
 def test_nonfinite_machine_result_null_and_failure(self):
  report={'status':'success','achieved_A_Apm':float('nan'),'achieved_B_Apm':float('inf')}
  with patch.object(run_static.time,'monotonic',return_value=1):result=run_static.finish(self.work,report,2,0)
  saved=json.loads((self.work/'run_result.json').read_text());self.assertEqual(result['status'],'failed_nonfinite_report');self.assertIsNone(saved['achieved_A_Apm']);self.assertIsNone(saved['achieved_B_Apm'])
 def test_budget_after_output_write_has_priority(self):
  report={'status':'success','stop_reason':'residual_tolerance'}
  with patch.object(run_static.time,'monotonic',side_effect=[1,2,2.01]):run_static.finish(self.work,report,2,0)
  saved=p.load_json(self.work/'run_result.json');self.assertEqual(saved['status'],'failed_timeout');self.assertEqual(saved['stop_reason'],'residual_tolerance')
 def test_io_failure_cannot_return_success(self):
  with patch.object(run_static,'write_json',side_effect=OSError('synthetic output failure')):
   with self.assertRaises(OSError):run_static.finish(self.work,{'status':'success'},2,0)
 def fixture_cp(self):
  make(self.work/'input');seed=(self.work/'input/seed.f64').read_bytes()
  raw=b'SD-v380-v1'+b'\0'*6+struct.pack('<3i2d',14380,0,0,1e-10,1e-15)+seed+seed+b'\0'*750000
  cp=self.work/'checkpoint.bin';cp.write_bytes(raw)
  return cp,seed
 def test_sidecar_inheritance_hash_and_unit_damage(self):
  cp,seed=self.fixture_cp();cfg=self.work/'input/config.dat';kernel=ROOT/'examples/kernel125-mirror10.f64'
  with self.assertRaises(ValueError):p.read_sidecar(cp,p.sha(cfg),p.sha(kernel),False)
  self.assertIsNone(p.read_sidecar(cp,p.sha(cfg),p.sha(kernel),True))
  side={**p.resolve_policy(self.cfg()),'checkpoint_sha256':p.sha(cp),'configuration_sha256':p.sha(cfg),'kernel_sha256':p.sha(kernel),'final_m_sha256':__import__('hashlib').sha256(seed).hexdigest()}
  path=Path(str(cp)+'.policy.json');p.write_json(path,side);self.assertEqual(p.read_sidecar(cp,p.sha(cfg),p.sha(kernel),False)['policy_id'],p.POLICY_ID)
  cp.write_bytes(cp.read_bytes()[:-1]+b'1')
  with self.assertRaises(ValueError):p.read_sidecar(cp,p.sha(cfg),p.sha(kernel),False)
  side['requested_tolerance']['unit']='dimensionless';p.write_json(path,side)
  with self.assertRaises(ValueError):p.read_sidecar(cp,p.sha(cfg),p.sha(kernel),False)
 def test_saved_magnetic_file_damage_rejected_before_field(self):
  cp,seed=self.fixture_cp();out=self.work/'saved';out.mkdir();(out/'final.bin').write_bytes(seed);(out/'checkpoint.bin').write_bytes(cp.read_bytes())
  cfg=self.work/'input/config.dat';kernel=ROOT/'examples/kernel125-mirror10.f64'
  binding={'configuration_sha256':p.sha(cfg),'kernel_sha256':p.sha(kernel),'final_m_sha256':p.sha(out/'final.bin'),'checkpoint_sha256':p.sha(out/'checkpoint.bin'),'native_A_B_Apm':[0,0]}
  raw=bytearray(seed);raw[0]^=1;(out/'final.bin').write_bytes(raw)
  with patch('check_residual.ref.fields',side_effect=AssertionError('no real field allowed'))as field:
   result=check_current(out,kernel,cfg,requested_tolerance=1,external_H_Apm=[0,0,-1],binding=binding)
  self.assertEqual(result['status'],'failed');self.assertEqual(result['real_fields'],0);field.assert_not_called()
 def test_FM_not_missing_B_zero(self):
  make(self.work/'input');cfg=self.work/'input/config.dat';s=cfg.read_text().replace('300000 600000','300000');cfg.write_text(s)
  with self.assertRaises(ValueError):p.read_supported_config(cfg)
 def test_cpp_threshold_AB_finite_post_and_clock_synthetic(self):
  if BINARY is None:self.skipTest('compiled policy_unit not requested')
  result=subprocess.run([BINARY,'policy_unit'],capture_output=True,text=True,timeout=2)
  self.assertEqual(result.returncode,0,result.stderr);self.assertEqual(json.loads(result.stdout)['real_fields'],0)
 def test_high_global_checkpoint_opt_in_no_field(self):
  if BINARY is None or HIGH_CP is None:self.skipTest('compiled checkpoint IO fixture not requested')
  r=subprocess.run([BINARY,'policy_checkpoint_unit',HIGH_CP],capture_output=True,text=True,timeout=2)
  self.assertEqual(r.returncode,0,r.stderr);self.assertEqual(json.loads(r.stdout)['real_fields'],0)


if __name__=='__main__':unittest.main(argv=[sys.argv[0],*REST])
