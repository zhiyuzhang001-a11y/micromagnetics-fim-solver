"""Focused controller faults after frozen endpoint; no dynamic updates."""
from pathlib import Path
import copy,json,subprocess,sys,tempfile
from unittest.mock import patch
import numpy as np
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'))
from current_case import resolve
from run_current_workflow import preflight,successful
from current_motion import motion
from user_case import defaults

def toml(path,raw):
 lines=['schema = '+json.dumps(raw['schema'])]
 for k,v in raw.items():
  if isinstance(v,dict):lines+=['['+k+']']+['%s = %s'%(kk,json.dumps(vv)) for kk,vv in v.items()]
 path.write_text('\n'.join(lines)+'\n')

def check(out,bins):
 raw=json.loads((out/'symmetric_25.input.json').read_text());source=out/'symmetric_25/driven/checkpoint.bin';raw['resume']={'checkpoint':str(source),'metadata':str(source)+'.json'};evidence={}
 for name,target in [('SVG','magnetic_final.svg'),('REPORT','report.json.tmp')]:
  r=copy.deepcopy(raw);folder=out/('fault_'+name);r['output']['directory']=str(folder);path=out/('fault_'+name+'.toml');toml(path,r)
  code="""import sys,pathlib,runpy
sys.path.insert(0,sys.argv[1]+'/tools')
old=pathlib.Path.write_text
def write(p,*a,**kw):
 if p.name==sys.argv[3]:raise OSError(28,'No space left on device')
 return old(p,*a,**kw)
pathlib.Path.write_text=write
target=sys.argv[3]
def write2(p,*a,**kw):
 if p.name==target:raise OSError(28,'No space left on device')
 return old(p,*a,**kw)
pathlib.Path.write_text=write2
sys.argv=[sys.argv[1]+'/tools/run_user_workflow.py',sys.argv[2]]
runpy.run_path(sys.argv[0],run_name='__main__')
"""
  p=subprocess.run([sys.executable,'-c',code,str(ROOT),str(path),target],capture_output=True,text=True,timeout=30);(out/('fault_'+name+'.stdout')).write_text(p.stdout);(out/('fault_'+name+'.stderr')).write_text(p.stderr);start=p.stdout.rfind('\n{\n')+1;report=json.loads(p.stdout[start:]);assert p.returncode==2 and not report['execution_completed'] and not report['mandatory_outputs_written'];assert report['new_fields']==2;assert report['stop_reason']=='output_write_failed';evidence[name]={'exit_code':p.returncode,'report':report}
 # Config and identity faults are checked before any Model.
 rejected=0
 for section,key,value in [('drive','kind','pulse'),('drive','Jc_Apm2',[0,0,1]),('drive','xi',[True,0]),('drive','incident_direction',[0,0,0]),('workflow','mode','relax'),('drive','field_like_ratio',[float('nan'),0])]:
  r=copy.deepcopy(raw);r[section][key]=value
  try:resolve(r)
  except ValueError:rejected+=1
  else:raise AssertionError('unsupported drive accepted')
 r=copy.deepcopy(raw);r['output']['directory']=str(out/'bad_identity');r['drive']['xi']=[.2,.1]
 try:preflight(resolve(r))
 except ValueError:rejected+=1
 else:raise AssertionError('changed drive resumed')
 r=copy.deepcopy(raw);r['output']['directory']=str(out/'cost_floor_preflight');assert preflight(resolve(r))[3]['new_Model_calls']==0
 # Zero-current directions, velocities, Hall are all null; no normalization of J=0.
 zero=json.loads((out/'zero_25/report.json').read_text())['motion'];assert zero['current_direction'] is None and all(x['Hall_deg'] is None and x['velocity_vector_mps'] is None and x['v_parallel_mps'] is None and x['v_perp_mps'] is None for x in zero['sublattices'])
 from run_user_workflow import size
 with tempfile.TemporaryDirectory() as td:
  p=Path(td)/'progress.json.tmp';p.write_text('x');original=Path.stat
  def disappear(self,*a,**kw):
   if self==p:raise FileNotFoundError('atomic rename')
   return original(self,*a,**kw)
  with patch.object(Path,'stat',disappear):assert size(td)==0
 answer={'passed':True,'native_processes':2,'native_started_fields':2,'independent_fields':2,'total_fields':4,'new_dynamic_updates':0,'pre_Model_rejections':rejected,'atomic_progress_rename_size_scan_passed':True,'zero_current_all_directional_values_null':True,'faults':evidence};(out/'FAULT_CHECKS.json').write_text(json.dumps(answer,indent=2,ensure_ascii=False)+'\n');print('PASS fault paths')
if __name__=='__main__':check(Path(sys.argv[1]).resolve(),ROOT/'build-sot')
