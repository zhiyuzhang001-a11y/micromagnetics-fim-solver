"""Constant-current A/B effective SOT. Dynamic completion is separate from equilibrium."""
from pathlib import Path
import argparse,copy,csv,json,struct,subprocess,time,sys
import numpy as np
from current_case import load,initial,shape,drive_rhs,rhs_scale
from current_motion import motion,rows
from user_case import sha,digest
from kernel_cache import get,key_data
from user_fields import evaluate,residual,MU
from user_structure import observe
from user_costs import ResourceCosts,inspect_ledger,legacy_source_cost
from run_user_workflow import write,size,rss,native_config,svg_snapshot
ROOT=Path(__file__).resolve().parents[1]

def scale(case):return MU*np.prod(np.array(case['geometry']['cell_nm'])*1e-9)*np.prod(case['geometry']['n'])*max(case['material']['Ms_Apm'])**2/2

def preflight(case):
 if sys.byteorder!='little' or struct.calcsize('@L')!=8:raise ValueError('current native ABI requires little-endian 64-bit unsigned long')
 if Path(case['output']['directory']).exists():raise ValueError('output exists; never overwrite')
 binary=Path(case['output']['bins'])/'fim_drive'
 if not binary.is_file():raise ValueError('missing fim_drive; build.py --current-sot')
 g=case['geometry'];canonical=g['n']==[125,125,1] and g['cell_nm']==[4,4,3] and g['pbc']==[1,1,0] and g['mirrors']==[10,10];cached=Path(case['output']['cache'])/digest(key_data(case))/'manifest.json'
 if not canonical and not cached.exists() and not (binary.parent/'kernel_builder').is_file():raise ValueError('new geometry needs verified MPFR/GMP kernel_builder before Model')
 m,info,meta=initial(case)
 if case['resume']['checkpoint']:
  if case['validation']['step_sensitivity']:raise ValueError('exact resume cannot restart a fresh dt/2 sensitivity branch')
  raw=Path(case['resume']['checkpoint']).read_bytes();n=int(np.prod(case['geometry']['n']))
  if meta.get('schema')!='current-checkpoint-v1' or meta['identity']!=case['identity'] or meta['binary_sha256']!=sha(binary) or len(raw)!=244+48*n or raw[24:88].decode()!=case['identity']:raise ValueError('driven resume identity/binary/layout')
  if meta['dynamic_steps']>case['dynamic']['steps']:raise ValueError('driven resume beyond target')
 if meta:
  if meta.get('resource_ledger'):inspect_ledger(meta['resource_ledger'])
  else:legacy_source_cost(meta)
 frames=case['dynamic']['steps']//case['output']['save_every']+len(case['output']['event_steps'])+3
 if case['validation']['step_sensitivity']:frames*=3
 forecast=(frames*3+8)*m.nbytes+case['dynamic']['steps']*1024
 if forecast>case['resources']['output_bytes']:raise ValueError('resource_forecast_insufficient: accepted observations/saved fields')
 return m,info,meta,{'valid':True,'new_Model_calls':0,'new_fields':0,'kernel_generated':False,'output_bytes_forecast':forecast}

def spec(path,case):
 d=case['drive'];rows=['CURRENT-SOT-v1',d['Jc_Apm2'],d['incident_direction'],d['xi'],d['field_like_ratio'],[*case['geometry']['origin_nm'],1e-8,len(case['output']['event_steps'])],case['output']['event_steps']];Path(path).write_text('\n'.join(v if isinstance(v,str) else ' '.join(str(x) for x in v) for v in rows)+'\n')

def metadata(cp,case,binary,kernel,costs,branch):
 raw=Path(cp).read_bytes();step=struct.unpack_from('<Q',raw,100)[0];d={'schema':'current-checkpoint-v1','identity':case['identity'],'physics_sha256':case['physics_sha256'],'drive_sha256':case['drive_sha256'],'checkpoint_sha256':sha(cp),'binary_sha256':sha(binary),'kernel_sha256':sha(kernel),'shape':case['geometry']['n'],'dynamic_steps':step,'phase':'driven_dynamic','time_ps':step*case['dynamic']['dt_fs']/1000,'spent_fields':costs.total(),'branch_fields':branch,'resource_ledger':str(costs.path),'observer_state':'wrapped/unwrapped positions and continuity embedded in CP; no reset on restore'};write(str(cp)+'.json',d);return d

def verify_event(folder,step,case,kernel):
 tag='step_'+str(step);m=np.fromfile(folder/(tag+'.bin'),'<f8').reshape(shape(case));H,E=evaluate(m,case,kernel);saved=np.stack([np.fromfile(folder/(tag+'_H_'+s+'.bin'),'<f8').reshape(m.shape[1:]) for s in ['A','B']]);f=np.fromfile(folder/(tag+'_drive_rhs.bin'),'<f8').reshape(m.shape);reference=drive_rhs(m,case);energy=np.array(json.loads((folder/(tag+'_energy.json')).read_text())['parts_J']);hist=next(r for r in rows(folder/'history.csv') if int(r['step'])==step);r=residual(m,H);unit=float(np.max(np.abs(np.linalg.norm(m,axis=-1)-1)));he=float(np.max(np.linalg.norm(H-saved,axis=-1))/max(1.,np.max(np.linalg.norm(H,axis=-1))));fe=float(np.max(np.linalg.norm(f-reference,axis=-1))/rhs_scale(case));ee=float(np.max(np.abs(E-energy))/scale(case));re=float(np.max(np.abs(r-[float(hist['residual_A_Apm']),float(hist['residual_B_Apm'])])))
 return {'passed':bool(np.isfinite(m).all() and np.isfinite(H).all() and np.isfinite(reference).all() and unit<=1e-12 and he<=1e-10 and fe<=1e-12 and ee<=1e-10 and re<=1e-6),'step':step,'unit_error':unit,'field_error':he,'RHS_error':fe,'energy_parts_error_over_Estar':ee,'residual_difference_Apm':re}

def successful(r):
 goal=r.get('structure_goal',{});goal_ok=goal.get('status') in {'none':['not_requested'],'observe':['observed'],'single_skyrmion':['met']}.get(goal.get('requested'),[])
 return bool(r.get('execution_completed') and r.get('mandatory_outputs_written') and r.get('trajectory_reached') and r.get('independent',{}).get('passed') and (r.get('step_sensitivity',{}).get('status')=='passed' if r.get('requested_step_sensitivity') else True) and goal_ok and not r.get('failure_detail'))

def run(case,validate_only=False):
 m,info,ancestor,valid=preflight(case)
 if validate_only:return valid
 out=Path(case['output']['directory']);out.mkdir(parents=True);start=time.monotonic();deadline=start+case['resources']['wall_s'];binary=Path(case['output']['bins'])/'fim_drive';costs=ResourceCosts(out,ancestor);inherited=costs.total();branch=ancestor.get('branch_fields',ancestor['spent_fields']) if ancestor and case['resume']['checkpoint'] else 0;branch_initial=branch;ledger=[];last_notify=0;report={'execution_completed':False,'mandatory_outputs_written':False,'trajectory_reached':False,'requested_step_sensitivity':case['validation']['step_sensitivity'],'step_sensitivity':{'status':'not_checked'},'static_criterion':{'status':'not_applicable','note':'driven trajectory does not use equilibrium stop'},'structure_goal':{'status':'not_checked'},'research_motion_qualification':'not_checked','grid_mirror_convergence':'not_checked','resource_ledger':str(costs.path),'inherited_fields':inherited,'legacy_cost_import_note':costs.legacy_note,'stop_reason':'preparing'}
 def guard():
  if time.monotonic()>=deadline:raise TimeoutError('resource_budget_exhausted: current wall')
  if size(out)>case['resources']['output_bytes'] or rss()>case['resources']['rss_bytes']:raise RuntimeError('resource_budget_exhausted: current output/RSS')
 def notify(event):
  nonlocal last_notify
  if time.monotonic()-last_notify>=case['output']['heartbeat_s']:
   event={**event,'job_elapsed_s':time.monotonic()-start,'observed_at_unix_s':time.time()};print(json.dumps(event,ensure_ascii=False),flush=True);write(out/'progress.json',event);last_notify=time.monotonic()
 def stage(name,c,state,kind):
  nonlocal branch
  guard();folder=out/name;cfg=out/(name+'.native.dat');remaining=case['resources']['max_fields']-costs.total()
  if remaining<1:raise RuntimeError('field_budget_exhausted')
  native_config(cfg,c,deadline-time.monotonic(),remaining);program=out/(name+'.drive.dat');spec(program,c);cmd=[str(binary),str(cfg),str(kernel),str(state),str(folder),str(c['dynamic']['steps']),str(c['output']['save_every']),c['identity'],kind,str(program)];write(out/(name+'.request.json'),{'command':cmd});token=costs.reserve(remaining,case['resources']['max_fields'],name);proc=None;before=time.monotonic()
  try:
   with (out/(name+'.stdout')).open('wb') as stdout,(out/(name+'.stderr')).open('wb') as stderr:
    proc=subprocess.Popen(cmd,stdout=stdout,stderr=stderr)
    try:
     while proc.poll() is None:
      guard();p=folder/'progress.json'
      if p.exists():
       try:notify(json.loads(p.read_text()))
       except json.JSONDecodeError:pass
      time.sleep(.05)
     if proc.returncode:raise RuntimeError((folder/'failure.txt').read_text() if (folder/'failure.txt').exists() else 'native_interrupted '+str(proc.returncode))
    finally:
     if proc.poll() is None:proc.kill();proc.wait()
  finally:
   data={}
   for tag in ['result.json','failure.json','counter.json']:
    try:data=json.loads((folder/tag).read_text());break
    except (FileNotFoundError,json.JSONDecodeError):pass
   count=data.get('fields',data.get('fields_started',data.get('started_fields')))
   if count is None and proc is not None:branch+=remaining;report['unconfirmed_field_upper_bound']=remaining
   else:count=count or 0;costs.settle(token,count);branch+=count
   ledger.append({'label':name,'fields':count,'returncode':None if proc is None else proc.returncode,'wall_s':time.monotonic()-before})
   if (folder/'checkpoint.bin').exists():metadata(folder/'checkpoint.bin',c,binary,kernel,costs,branch)
  return folder,json.loads((folder/'result.json').read_text())
 def independently(folder,c):
  nonlocal branch
  results=[]
  for p in sorted(folder.glob('step_*.bin')):
   if p.stem[5:].isdigit():
    guard();token=costs.reserve(1,case['resources']['max_fields'],'independent '+p.stem);costs.settle(token,1);branch+=1;step=int(p.stem[5:]);check=verify_event(folder,step,c,kernel);results.append(check)
    if not check['passed']:raise RuntimeError('independent driven field/RHS/energy gate failed')
  answer={'passed':all(x['passed'] for x in results) and bool(results),'checks':results,'fields':len(results)};write(folder/'independent.json',answer);metadata(folder/'checkpoint.bin',c,binary,kernel,costs,branch);return answer
 try:
  write(out/'resolved_case.json',case);write(out/'initial.json',info);m.astype('<f8').tofile(out/'seed.f64');write(out/'manifest.json',{'schema':'current-run-v1','identity':case['identity'],'drive':case['drive'],'conservative_physics_sha256':case['physics_sha256'],'binary_sha256':sha(binary),'source_sha256':digest({str(p.relative_to(ROOT)):sha(p) for p in (ROOT/'src').rglob('*') if p.is_file()}),'initial_sha256':sha(out/'seed.f64'),'predecessor':ancestor,'python':sys.version,'numpy':np.__version__})
  kernel,kmeta=get(case,deadline,notify);write(out/'kernel.json',kmeta)
  if case['resume']['checkpoint'] and ancestor['kernel_sha256']!=sha(kernel):raise ValueError('current resume kernel identity')
  state=Path(case['resume']['checkpoint']) if case['resume']['checkpoint'] else out/'seed.f64';folder,result=stage('driven',case,state,'checkpoint' if case['resume']['checkpoint'] else 'seed');check=independently(folder,case);report['independent']=check;report['native_result']=result;report['trajectory_reached']=result['step']==case['dynamic']['steps'];report['motion']=motion(folder/'observations.csv',case);final=np.fromfile(folder/'final.bin','<f8').reshape(m.shape);report['structure_goal']=observe(final,case,deadline)
  if case['validation']['step_sensitivity']:
   fine=copy.deepcopy(case);fine['dynamic']['dt_fs']/=2;fine['dynamic']['steps']*=2;fine['output']['event_steps']=[k*2 for k in fine['output']['event_steps']];fine['conservative_identity']=digest({'physics':{'geometry':fine['geometry'],'material':fine['material'],'field':fine['field']['H_Apm']},'dt_fs':fine['dynamic']['dt_fs'],'schema':'user_case_v1'});fine['identity']=digest({'base':fine['conservative_identity'],'drive':fine['drive'],'mode':'driven_dynamic-v1'});ff,fr=stage('dt_half',fine,out/'seed.f64','seed');independently(ff,fine);fm=np.fromfile(ff/'final.bin','<f8').reshape(m.shape);q=np.linalg.norm(fm-final,axis=-1);report['step_sensitivity']={'status':'passed' if np.max(q)<=case['validation']['max_chord'] and np.sqrt(np.mean(q*q))<=case['validation']['rms_chord'] else 'not_met','max_chord':float(np.max(q)),'rms_chord':float(np.sqrt(np.mean(q*q)))}
  np.savez(out/'magnetic_final.npz',m=final,cell_nm=case['geometry']['cell_nm'],origin_nm=case['geometry']['origin_nm']);svg_snapshot(out/'magnetic_final.svg',final,case);guard();report.update(final_checkpoint=str(folder/'checkpoint.bin'),final_checkpoint_metadata=str(folder/'checkpoint.bin.json'),mandatory_outputs_written=True,execution_completed=True,stop_reason='physical_time');report['execution_completed']=successful(report)
  if not report['execution_completed']:report['stop_reason']='requested_validation_not_met'
 except Exception as e:report.update(execution_completed=False,mandatory_outputs_written=False,stop_reason='resource_budget_exhausted' if isinstance(e,TimeoutError) or 'budget' in str(e) else 'output_write_failed' if isinstance(e,OSError) else 'failed_input_or_verification',failure_detail=str(e))
 finally:
  report.update(started_fields=costs.total(),branch_fields=branch,new_fields=branch-branch_initial,ledger=ledger,wall_s=time.monotonic()-start)
  cps=[p for p in out.glob('*/checkpoint.bin') if Path(str(p)+'.json').exists()]
  if cps:report['last_complete_checkpoint']=str(max(cps,key=lambda p:p.stat().st_mtime_ns))
  report['feedback']=[{'observed':report['stop_reason'],'guidance':'驱动到时长、数值检查和观测有效性分别查看；J=0仅报漂移。未分辨不能转写为速度/Hall物理结论，不自动改电流或科学阈值。','automatic_parameter_change':False}]
  try:costs.record_run_cost(report['wall_s'],report['new_fields'],branch);write(out/'ledger.json',ledger);write(out/'report.json',report)
  except Exception as e:
   report.update(execution_completed=False,mandatory_outputs_written=False,stop_reason='output_write_failed',failure_detail=str(e))
   try:write(out/'report.json',report)
   except Exception:pass
 return report

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('case',type=Path);p.add_argument('--validate-only',action='store_true');a=p.parse_args()
 try:r=run(load(a.case),a.validate_only);print(json.dumps(r,indent=2,ensure_ascii=False));sys.exit(0 if r.get('valid') or successful(r) else 2)
 except Exception as e:print(json.dumps({'execution_completed':False,'stop_reason':'input_rejected_before_Model','failure_detail':str(e)},ensure_ascii=False));sys.exit(2)
