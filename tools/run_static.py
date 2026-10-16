"""Explicit local FiM post-field policy; native candidate needs saved-state verification."""
from pathlib import Path
import argparse
import json
import math
import os
import subprocess
import sys
import time
from static_policy import (POLICY_ID,KERNEL_SHA,sha,load_json,write_json,read_supported_config,
                           read_sidecar,resolve_policy,success_status)
from static_policy import has_nonfinite


def run(args):
 start=time.monotonic();out=Path(args.output).resolve()
 if out.exists():raise ValueError('output exists; no overwrite or retry')
 out.mkdir(parents=True)
 native={};independent={'status':'not_checked'};binding={};policy={};timed_out=False
 report={'policy_id':POLICY_ID,'status':'failed_input','stop_reason':'invalid_input','independent_check':independent,
         'achieved_A_Apm':None,'achieved_B_Apm':None,'real_native_fields':0,'real_independent_fields':0,'native_invoked':False,'native_field_cap':args.max_fields}
 try:
  if not math.isfinite(args.timeout)or not math.isfinite(args.native_budget)or args.timeout<=0 or args.native_budget<=0 or args.native_budget>args.timeout:
   raise ValueError('invalid explicit time budgets')
  if args.max_updates<0 or args.max_updates>30000 or args.max_fields<1:raise ValueError('invalid update/field cap')
  config=Path(args.config).resolve();kernel=Path(args.kernel).resolve();actual=read_supported_config(config)
  config_sha=sha(config);kernel_sha=sha(kernel)
  if kernel_sha!=KERNEL_SHA:raise ValueError('only the fixed qualified finite-image kernel is supported')
  restore=Path(args.restore).resolve()if args.restore else None
  sidecar=read_sidecar(restore,config_sha,kernel_sha,args.adopt_legacy_checkpoint)if restore else None
  policy=resolve_policy(args.policy_config,args.tolerance,sidecar,args.external_H)
  if bool(args.seed)==bool(restore):raise ValueError('provide exactly one seed or restore checkpoint')
  report.update(policy);report['checkpoint_migration']='legacy_no_sidecar_explicit_adoption'if restore and sidecar is None else'inherited_sidecar'if restore else'new_seed'
  raw_input=restore if restore else Path(args.seed).resolve();input_sha=sha(raw_input)
  native_out=out/'native';eps=policy['requested_tolerance']['value']
  command=[str(Path(args.binary).resolve()),str(config),str(kernel),str(raw_input)if not restore else'-',str(native_out),'run_policy',str(restore)if restore else'-',repr(args.native_budget),repr(eps),str(args.max_updates),str(args.max_fields),*map(repr,policy['external_H_Apm'])]
  write_json(out/'request.json',{'policy':policy,'configuration':actual,'configuration_sha256':config_sha,'kernel_sha256':kernel_sha,
                              'input_sha256':input_sha,'command':command,'overall_timeout_s':args.timeout})
  remaining=args.timeout-(time.monotonic()-start)
  if remaining<=0:raise subprocess.TimeoutExpired(command,args.timeout)
  try:
   report['native_invoked']=True
   proc=subprocess.run(command,capture_output=True,text=True,timeout=remaining,env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1'})
   (out/'native.stdout').write_text(proc.stdout);(out/'native.stderr').write_text(proc.stderr)
  except subprocess.TimeoutExpired:
   timed_out=True
   if (native_out/'native_policy_result.json').exists():native=load_json(native_out/'native_policy_result.json')
   raise
  result_path=native_out/'native_policy_result.json'
  if result_path.exists():native=load_json(result_path)
  report.update({'native_returncode':proc.returncode,'native':native,'native_stop_reason':native.get('stop_reason'),
                 'stop_reason':native.get('stop_reason','native_result_missing'),'real_native_fields':native.get('field_calls',0),
                 'achieved_A_Apm':native.get('achieved_A_Apm'),'achieved_B_Apm':native.get('achieved_B_Apm'),
                 'local_updates':native.get('local_updates'),'global_updates':native.get('global_updates')})
  if proc.returncode!=0 or native.get('stop_reason')!='residual_tolerance' or not native.get('native_candidate'):
   report['status']='not_success';return finish(out,report,args.timeout,start)
  if native.get('policy_id')!=POLICY_ID or native.get('requested_tolerance')!=policy['requested_tolerance'] or native.get('Ms_Apm')!=actual['Ms_Apm'] or native.get('external_H_Apm')!=policy['external_H_Apm']:
   raise ValueError('native actual policy/configuration differs from request')
  if sha(config)!=config_sha or sha(kernel)!=kernel_sha or sha(raw_input)!=input_sha:raise ValueError('input changed during native run')
  binding={'configuration_sha256':config_sha,'kernel_sha256':kernel_sha,'final_m_sha256':sha(native_out/'final.bin'),
           'checkpoint_sha256':sha(native_out/'checkpoint.bin'),'native_A_B_Apm':[native['achieved_A_Apm'],native['achieved_B_Apm']]}
  if time.monotonic()-start>=args.timeout:raise subprocess.TimeoutExpired(command,args.timeout)
  from check_residual import check_current
  independent=check_current(native_out,kernel,config,requested_tolerance=eps,external_H_Apm=policy['external_H_Apm'],binding=binding)
  write_json(out/'independent_check.json',independent)
  identities=(independent.get('identities_match',False)and sha(native_out/'final.bin')==binding['final_m_sha256']and sha(native_out/'checkpoint.bin')==binding['checkpoint_sha256']and sha(config)==config_sha and sha(kernel)==kernel_sha)
  report.update({'independent_check':independent,'real_independent_fields':independent.get('real_fields',0),'identities_match':identities,
                 'final_m_sha256':binding['final_m_sha256'],'checkpoint_sha256':binding['checkpoint_sha256'],
                 'configuration_sha256':config_sha,'kernel_sha256':kernel_sha,
                 'final_m_path':str(native_out/'final.bin'),'checkpoint_path':str(native_out/'checkpoint.bin')})
  report['status']=success_status(native,independent,identities)
  if report['status']=='success':
   new_sidecar={**policy,'configuration_sha256':config_sha,'kernel_sha256':kernel_sha,
                'final_m_sha256':binding['final_m_sha256'],'checkpoint_sha256':binding['checkpoint_sha256'],
                'Ms_Apm':actual['Ms_Apm'],'migration':report['checkpoint_migration'],'local_updates':native['local_updates'],
                'global_updates':native['global_updates'],'independent_verified':True}
   write_json(Path(str(native_out/'checkpoint.bin')+'.policy.json'),new_sidecar)
   # Verify output metadata and both saved files again after the sidecar write.
   read_sidecar(native_out/'checkpoint.bin',config_sha,kernel_sha,False)
   if sha(native_out/'final.bin')!=binding['final_m_sha256']:raise ValueError('saved magnetization changed after verification')
  return finish(out,report,args.timeout,start)
 except subprocess.TimeoutExpired:
  report.update({'status':'failed_timeout','execution_failure_reason':'external_timeout','native_stop_reason':native.get('stop_reason'),
                 'stop_reason':native.get('stop_reason','external_timeout'),'native':native,'real_native_fields':native.get('field_calls',0),
                 'independent_check':independent})
  if 'field_calls' not in native:
   report['real_native_fields']=None;report['native_field_count_unconfirmed_upper_bound']=args.max_fields
 except Exception as error:
  report.update({'status':'failed_io_or_verification'if native else'failed_input','failure_reason':str(error),'independent_check':independent})
 return finish(out,report,args.timeout,start)


def finish(out,report,timeout,start):
 report['achieved_source']='native_actual_post_current_field'if report.get('native')else'unavailable'
 for stem,key in [('final.bin','final_m'),('checkpoint.bin','checkpoint')]:
  p=out/'native'/stem;actual=sha(p)if p.exists()else None;previous=report.get(key+'_sha256')
  if previous is not None and previous!=actual:
   report['status']='failed_saved_identity';report['identities_match']=False
   report['previously_verified_'+key+'_sha256']=previous
  report[key+'_path']=str(p)if p.exists()else None;report[key+'_sha256']=actual
 if report.get('native_invoked')and 'field_calls'not in report.get('native',{}):
  report['real_native_fields']=None;report['native_field_count_unconfirmed_upper_bound']=report.get('native_field_cap')
 if has_nonfinite(report):
  report['status']='failed_nonfinite_report';report['failure_reason']='nonfinite machine result converted to null'
 report['wall_s']=time.monotonic()-start
 if report['wall_s']>=timeout:
  report['status']='failed_timeout';report['execution_failure_reason']='external_timeout'
 write_json(out/'run_result.json',report)
 # The final write is part of the total timeout too, not a success loophole.
 if time.monotonic()-start>=timeout and report['status']!='failed_timeout':
  report['status']='failed_timeout';report['execution_failure_reason']='external_timeout_after_result_write'
  report['wall_s']=time.monotonic()-start;write_json(out/'run_result.json',report)
 return report


def parser():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--config',required=True);p.add_argument('--kernel',required=True)
 p.add_argument('--binary',required=True);p.add_argument('--output',required=True);p.add_argument('--seed');p.add_argument('--restore')
 p.add_argument('--policy-config');p.add_argument('--tolerance',type=float);p.add_argument('--external-H',type=float,nargs=3)
 p.add_argument('--adopt-legacy-checkpoint',action='store_true');p.add_argument('--max-updates',type=int,default=10000)
 p.add_argument('--max-fields',type=int,default=1000000);p.add_argument('--native-budget',type=float,default=1.5);p.add_argument('--timeout',type=float,default=2)
 return p


if __name__=='__main__':
 try:
  result=run(parser().parse_args());print(json.dumps(result,allow_nan=False,indent=2));raise SystemExit(0 if result['status']=='success'else 2)
 except Exception as error:
  print(str(error),file=sys.stderr);raise SystemExit(2)
