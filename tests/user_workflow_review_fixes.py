"""Focused regression for independent-review findings. No dynamics are advanced.
Requires original bounded acceptance evidence and the reviewer TOML reproducer.
"""
from pathlib import Path
import argparse,copy,json,shutil,subprocess,sys,tomllib
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'))
from run_user_workflow import requirements_met,exit_code
from feedback import hints
from user_costs import ResourceCosts

def toml(path,raw):
 lines=['schema = '+json.dumps(raw['schema'])]
 for section,values in raw.items():
  if isinstance(values,dict):
   lines+=['['+section+']']
   for key,value in values.items():lines+=[key+' = '+json.dumps(value)]
 path.write_text('\n'.join(lines)+'\n')

def check(out,review):
 out.mkdir(parents=True,exist_ok=False);receipts={}
 threshold=tomllib.loads((review/'threshold_cli.toml').read_text());cost=tomllib.loads((review/'cost_cli.toml').read_text())
 # Preserve original evidence. Clone the two source CP/report records used for migration.
 for name,raw in [('M',threshold),('M_first',cost)]:
  source=Path(raw['resume']['checkpoint']).parent.parent;target=out/'legacy_inputs'/name;(target/'dynamic').mkdir(parents=True)
  for p in ['report.json','dynamic/checkpoint.bin','dynamic/checkpoint.bin.json']:shutil.copyfile(source/p,target/p)
  raw['resume']={'checkpoint':str(target/'dynamic/checkpoint.bin'),'metadata':str(target/'dynamic/checkpoint.bin.json')}
 def cli(name,raw,fault=False):
  raw=copy.deepcopy(raw);raw['output']['directory']=str(out/name);path=out/(name+'.toml');toml(path,raw)
  if fault:
   code="""import sys,pathlib,runpy
sys.path.insert(0,sys.argv[1]+'/tools')
old=pathlib.Path.write_text
def write(p,*a,**kw):
 if p.name=='magnetic_final.svg':raise OSError(28,'No space left on device')
 return old(p,*a,**kw)
pathlib.Path.write_text=write
sys.argv=[sys.argv[1]+'/tools/run_user_workflow.py',sys.argv[2]]
runpy.run_path(sys.argv[0],run_name='__main__')
"""
   cmd=[sys.executable,'-c',code,str(ROOT),str(path)]
  else:cmd=[sys.executable,str(ROOT/'tools/run_user_workflow.py'),str(path)]
  p=subprocess.run(cmd,capture_output=True,text=True,timeout=30);(out/(name+'.stdout')).write_text(p.stdout);(out/(name+'.stderr')).write_text(p.stderr);report=json.loads((out/name/'report.json').read_text());receipts[name]={'exit_code':p.returncode,'report':report};return p.returncode,report
 code,r=cli('threshold',threshold);assert code==2 and not r['execution_completed'] and r['static_criterion']['status']=='not_met';assert r['static_criterion']['requested_tol_Apm']==486343.30171461013;assert r['static_criterion']['independent']['A_B_Apm'][0]==486343.3017146102
 fault=copy.deepcopy(threshold);fault['static']['tol_Apm']=1e9;code,r=cli('io_fault',fault,True);assert code==2 and not r['execution_completed'] and not r['mandatory_outputs_written'] and 'No space' in r['failure_detail']
 code,a=cli('cost_first',cost);assert code==0 and a['inherited_fields']==181 and a['started_fields']==186 and a['branch_fields']==168
 code,b=cli('cost_old_again',cost);assert code==0 and b['inherited_fields']==186 and b['started_fields']==191 and b['branch_fields']==168
 recent=copy.deepcopy(cost);recent['resume']={'checkpoint':a['final_checkpoint'],'metadata':a['final_checkpoint_metadata']};code,c=cli('cost_new_checkpoint',recent);assert code==0 and c['inherited_fields']==191 and c['started_fields']==193
 code,d=cli('cost_old_after_new',cost);assert code==0 and d['inherited_fields']==193 and d['started_fields']==198
 assert all('尚未达' not in h['observed'] for h in d['feedback'])
 goal=copy.deepcopy(fault);goal['output']['goal']='single_skyrmion';code,r=cli('goal_mismatch',goal);assert code==2 and not r['execution_completed'] and r['static_criterion']['status']=='met' and r['structure_goal']['status']=='not_met'
 # State-level gate coverage needs no extra native field calls.
 state=copy.deepcopy(d);state['requested_step_sensitivity']=True;state['dynamic_step_sensitivity']['status']='not_met';assert not requirements_met(state) and exit_code(state)==2
 state=copy.deepcopy(d);state['static_criterion']['independent']['static_criterion_met']=False;assert not requirements_met(state) and exit_code(state)==2
 assert all('尚未达' not in x['observed'] for x in hints(d));assert any('尚未达' in x['observed'] for x in hints(receipts['threshold']['report']))
 # Conservative reservation survives reader/restart and rejects budget or corruption; no Model.
 ledger=ResourceCosts(out/'reservation_fixture',None);token=ledger.reserve(7,10,'interrupted native');again=ResourceCosts(out/'another_run',{'resource_ledger':str(ledger.path)});assert again.total()==7
 try:again.reserve(4,10,'must reject')
 except RuntimeError:pass
 else:raise AssertionError('reservation lost across restart')
 ledger.settle(token,3);assert again.total()==3
 corrupt=out/'corrupt.resource-costs.jsonl';corrupt.write_bytes(ledger.path.read_bytes()+b'{partial')
 try:ResourceCosts(out/'corrupt_probe',{'resource_ledger':str(corrupt)})
 except ValueError:pass
 else:raise AssertionError('corrupt cost ledger accepted')
 # Final ledger/report I/O failures also clear completion even when all science gates passed.
 from unittest.mock import patch
 import run_user_workflow as workflow
 import tempfile
 for failed_name in ['ledger.json','report.json']:
  state=copy.deepcopy(d);real=workflow.write
  def failed_write(path,value):
   if Path(path).name==failed_name:raise OSError(28,'No space left on device')
   return real(path,value)
  with tempfile.TemporaryDirectory() as td,patch.object(workflow,'write',failed_write):workflow.publish_report(Path(td),state,[])
  assert not state['execution_completed'] and exit_code(state)==2
 ledger.record_run_cost(.1,3,3);assert again.total()==3
 with tempfile.TemporaryDirectory() as td:
  try:ResourceCosts(Path(td)/'out',{'_metadata_path':str(Path(td)/'missing/dynamic/checkpoint.bin.json'),'spent_fields':163})
  except ValueError:pass
  else:raise AssertionError('legacy snapshot without source total accepted')
 empty=out/'empty.resource-costs.jsonl';empty.write_text('')
 try:ResourceCosts(out/'empty_probe',{'resource_ledger':str(empty)})
 except ValueError:pass
 else:raise AssertionError('empty cost ledger accepted')
 records=[p for p in out.glob('*/**/counter.json') if 'legacy_inputs' not in p.parts];native=sum(json.loads(p.read_text())['started_fields'] for p in records);new=sum(q['report']['new_fields'] for q in receipts.values());assert len(records)==13 and native==13 and new==32,(len(records),native,new)
 result={'passed':True,'native_processes':len(records),'native_started_fields':native,'independent_fields':new-native,'total_new_fields':new,'advanced_dynamic_steps':0,'new_builds':0,'new_kernels':0,'500ps_reruns':0,'independent_review_prior_costs':{'native_processes':10,'fields':29},'receipts':receipts,'cost_ledger_repeated_old_and_new_checkpoint_totals':[a['started_fields'],b['started_fields'],c['started_fields'],d['started_fields']]}
 (out/'REPAIR_ACCEPTANCE.json').write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n');print('PASS focused repair;',len(records),'native;',new,'fields')
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);p.add_argument('--review-evidence',type=Path,required=True);a=p.parse_args();check(a.out.resolve(),a.review_evidence.resolve())
