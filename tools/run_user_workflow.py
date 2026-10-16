"""One TOML -> traceable single-layer dynamic/SD workflow. No implicit retuning."""
from pathlib import Path
import argparse,copy,json,math,os,resource,struct,subprocess,sys,time
if sys.version_info < (3,11):raise SystemExit('需要 Python 3.11+；请使用具备 numpy 的同一解释器构建、预检及运行。')
try:import numpy as np
except ModuleNotFoundError:raise SystemExit('缺少 numpy；请使用已安装 numpy 的 Python 3.11+ 解释器。没有启动 Model 或自动安装依赖。')
from user_case import load,sha,digest
from initial_state import generate
from kernel_cache import get,layout,key_data
from user_fields import verify
from user_structure import observe
from feedback import hints
from user_costs import ResourceCosts,inspect_ledger,legacy_source_cost
ROOT=Path(__file__).resolve().parents[1]

def write(path,obj):
 p=Path(path);tmp=p.with_name(p.name+'.tmp');tmp.write_text(json.dumps(obj,indent=2,allow_nan=False,ensure_ascii=False)+'\n');tmp.replace(p)
def size(path):
 total=0
 for p in Path(path).rglob('*'):
  try:
   if p.is_file():total+=p.stat().st_size
  except FileNotFoundError:pass  # A native atomic rename may remove its temporary file.
 return total
def rss():return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*(1 if sys.platform=='darwin' else 1024)
def native_config(path,case,wall,fields):
 g=case['geometry'];m=case['material'];px,py=layout(case);reserve=rss()+32*1024**2;cap=case['resources']['rss_bytes']-reserve
 if cap<16*1024**2:raise ValueError('resource_forecast_insufficient: RSS for Python and native')
 rows=['USER-FIM-v1',g['n'],[x*1e-9 for x in g['cell_nm']],g['pbc'],m['Ms_Apm'],m['A_Jpm'],[m['Ah_Jpm3'],m['Anh_Jpm']],m['D_Jpm2'],m['K1_Jpm3'],m['K2_Jpm3'],*m['axes'],m['alpha'],m['gamma_H_m_per_As'],case['field']['H_Apm'],m['active'],[case['dynamic']['dt_fs']*1e-15,wall,fields,px,py,cap]]
 Path(path).write_text('\n'.join(x if isinstance(x,str) else ' '.join(str(q) for q in x) for x in rows)+'\n')
def checkpoint_sidecar(cp,case,binary,kernel,phase,spent,costs=None,branch_fields=None):
 raw=Path(cp).read_bytes();magic,n,length=struct.unpack_from('<QQQ',raw);offset=24+length+12;steps=struct.unpack_from('<Q',raw,offset)[0];updates=struct.unpack_from('<i',raw,offset+8+48)[0]
 if magic!=0x3150435245535546 or n!=int(np.prod(case['geometry']['n'])):raise ValueError('checkpoint schema/shape')
 meta={'schema':'user-checkpoint-v1','checkpoint_sha256':sha(cp),'identity':case['identity'],'physics_sha256':case['physics_sha256'],'kernel_sha256':sha(kernel),'binary_sha256':sha(binary),'phase':phase,'dynamic_steps':steps,'static_updates':updates,'spent_fields':spent,'requested_tol_Apm':case['static']['tol_Apm'],'requested_T_ps':case['dynamic']['T_ps'],'shape':case['geometry']['n']};
 if costs:meta.update(resource_ledger=str(costs.path),branch_fields=branch_fields)
 write(str(cp)+'.json',meta);return meta

def preflight(case):
 if sys.byteorder!='little' or struct.calcsize('@L')!=8:raise ValueError('native checkpoint ABI currently requires little-endian 64-bit unsigned long')
 if Path(case['output']['directory']).exists():raise ValueError('output exists; choose a new directory, never overwrite')
 m=None;initial=None;required=['fim_user'];g=case['geometry'];canonical=g['n']==[125,125,1] and g['cell_nm']==[4,4,3] and g['pbc']==[1,1,0] and g['mirrors']==[10,10]
 cache=Path(case['output']['cache'])/digest(key_data(case));cached=(cache/'manifest.json').exists()
 if not canonical and not cached:required.append('kernel_builder')
 missing=[str(Path(case['output']['bins'])/x) for x in required if not (Path(case['output']['bins'])/x).is_file()]
 if missing:raise ValueError('missing build/dependencies: '+','.join(missing)+'; build.py --user-workflow needs FFTW/MPFR/GMP')
 resume=case['resume'];meta=None
 if resume['checkpoint']:
  meta=json.loads(Path(resume['metadata']).read_text());cp=Path(resume['checkpoint'])
  if meta.get('schema')!='user-checkpoint-v1' or meta.get('identity')!=case['identity'] or meta.get('checkpoint_sha256')!=sha(cp) or meta.get('binary_sha256')!=sha(Path(case['output']['bins'])/'fim_user') or meta.get('shape')!=case['geometry']['n']:raise ValueError('checkpoint identity/checksum mismatch; unbound legacy checkpoints are not exact resumes')
 if meta:
  meta['_metadata_path']=str(Path(resume['metadata']).resolve())
  if meta.get('resource_ledger'):inspect_ledger(meta['resource_ledger'])
  else:legacy_source_cost(meta)
  if meta.get('phase') not in ['dynamic','static'] or case['validation']['step_sensitivity']:raise ValueError('unsupported resume phase/step sensitivity combination')
  if meta['dynamic_steps']>case['dynamic']['steps'] or meta['phase']=='static' and meta['dynamic_steps']!=case['dynamic']['steps']:raise ValueError('resume interval mismatch')
  raw=Path(resume['checkpoint']).read_bytes();n=int(np.prod(case['geometry']['n']));length=struct.unpack_from('<Q',raw,16)[0];offset=24+length+12+8+48+12
  if length!=64 or len(raw)!=offset+3*2*n*3*8 or raw[24:24+length].decode()!=case['identity']:raise ValueError('checkpoint native layout/identity')
  m=np.frombuffer(raw[offset:offset+2*n*3*8],dtype='<f8').copy().reshape(2,case['geometry']['n'][2],case['geometry']['n'][1],case['geometry']['n'][0],3)
  if not np.isfinite(m).all() or np.max(np.abs(np.linalg.norm(m,axis=-1)-1))>1e-12:raise ValueError('checkpoint direction finite/unit')
  initial={'kind':'checkpoint accepted directions','predecessor_checkpoint_sha256':sha(resume['checkpoint'])}
 else:m,initial=generate(case)
 sensitivity=case['validation']['step_sensitivity'];phases=2+int(sensitivity);save_every=case['output']['save_every'];frames=case['dynamic']['steps']//save_every+case['static']['max_updates']//save_every+2*phases
 if sensitivity:frames+=2*case['dynamic']['steps']//save_every
 rows=case['dynamic']['steps']*(3 if sensitivity else 1)+case['static']['max_updates']+2*phases
 forecast=(frames+10*phases+5)*m.nbytes+512*rows+16384*phases
 if forecast>case['resources']['output_bytes']:raise ValueError('resource_forecast_insufficient: snapshot output, increase save_every or output_bytes')
 return m,initial,meta,{'valid':True,'new_Model_calls':0,'new_kernel_generation':False,'missing_dependencies':missing,'snapshot_bytes_upper_estimate':forecast,'first_kernel_note':'首次新几何核需MPFR/GMP，可能较慢；缓存不代表网格/镜像收敛'}

def svg_snapshot(path,m,case):
 nx,ny,_=case['geometry']['n'];width=2*nx+12;rows=[f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {ny+20}">',f'<text x="0" y="6" font-size="4">m_z A/B; cells={case["geometry"]["cell_nm"]} nm; red +1 / blue -1</text>']
 for sub in [0,1]:
  for y in range(ny):
   for x in range(nx):
    z=float(m[sub,0,y,x,2]);red=int(round((z+1)*127.5));rows.append(f'<rect x="{x+sub*(nx+12)}" y="{y+10}" width="1" height="1" fill="rgb({red},0,{255-red})"/>')
 rows.append('</svg>');Path(path).write_text('\n'.join(rows))

def dynamic_diagnostics(case,result):
 scale=4*math.pi*1e-7*math.prod(x*1e-9 for x in case['geometry']['cell_nm'])*math.prod(case['geometry']['n'])*max(case['material']['Ms_Apm'])**2/2
 defect=result['energy_J']-result['origin_J']+result['total_loss_J']
 return {'energy_dissipation_defect_J':defect,'defect_over_energy_scale':defect/scale,'loss_A_J':result['loss_A_J'],'loss_B_J':result['loss_B_J'],'note':'有限步长诊断；未给定全局动态误差资格时不据此宣称物理精度。改变参数后用同窗dt/2复核。'}

def requirements_met(report):
 static=report.get('static_criterion',{});check=static.get('independent',{})
 step=report.get('dynamic_step_sensitivity',{}).get('status')
 structure=report.get('structure_goal',{});goal=structure.get('status');goal_ok=goal in {'none':['not_requested'],'observe':['observed'],'single_skyrmion':['met']}.get(structure.get('requested'),[])
 return bool(report.get('mandatory_outputs_written') and static.get('status')=='met' and check.get('passed') and check.get('static_criterion_met') and (step=='passed' if report.get('requested_step_sensitivity') else step in ['not_checked','passed']) and goal_ok and not report.get('failure_detail'))

def exit_code(report):
 return 0 if report.get('valid') or report.get('execution_completed') and requirements_met(report) else 2

def publish_report(out,report,ledger):
 try:
  write(out/'ledger.json',ledger)
  report['execution_completed']=bool(report.get('execution_completed') and requirements_met(report))
  write(out/'report.json',report)
 except Exception as error:
  report.update(execution_completed=False,mandatory_outputs_written=False,execution_status='failed',stop_reason='output_write_failed',failure_detail=str(error))
  report['feedback']=hints(report)
  try:write(out/'report.json',report)
  except Exception:pass  # Return/CLI still fail if even the failure report cannot be persisted.
 return report

def run(case,validate_only=False):
 m,initial,resume_meta,validation=preflight(case)
 if validate_only:return validation
 start=time.monotonic();deadline=start+case['resources']['wall_s'];out=Path(case['output']['directory']);out.mkdir(parents=True);binary=Path(case['output']['bins'])/'fim_user';costs=ResourceCosts(out,resume_meta);spent=costs.total();inherited_spent=spent;branch_spent=(resume_meta.get('branch_fields',resume_meta['spent_fields']) if resume_meta else 0);initial_branch_spent=branch_spent;ledger=[];last_notify=0.;report={'execution_completed':False,'mandatory_outputs_written':False,'requested_step_sensitivity':case['validation']['step_sensitivity'],'resource_ledger':str(costs.path),'legacy_cost_import_note':costs.legacy_note,'checkpoint_branch_fields':initial_branch_spent,'static_criterion':{'status':'not_checked'},'dynamic_step_sensitivity':{'status':'not_checked'},'structure_goal':{'status':'not_checked'},'grid_mirror_convergence':{'status':'not_checked','note':'核工程参考检查/缓存命中不等于物理收敛验证'},'stop_reason':'preparing','started_fields':spent,'inherited_fields':inherited_spent,'ledger':ledger}
 write(out/'resolved_case.json',case);m.astype('<f8').tofile(out/'seed.f64');write(out/'initial.json',initial);write(out/'manifest.json',{'schema':'user-run-v1','identity':case['identity'],'physics_sha256':case['physics_sha256'],'initial_sha256':sha(out/'seed.f64'),'binary_sha256':sha(binary),'source_sha256':digest({p.name:sha(p) for p in (ROOT/'src').rglob('*') if p.is_file()}),'shape':[2,*reversed(case['geometry']['n']),3],'storage':'little-endian f64; A then B; x fastest','predecessor':resume_meta,'user_config':case,'dependency_note':'FFTW; MPFR/GMP for new kernels; Python/numpy','python':sys.version,'numpy':np.__version__,'build_receipt':json.loads((binary.parent/'build.json').read_text()) if (binary.parent/'build.json').exists() else None})
 def notify(event):
  nonlocal last_notify
  if time.monotonic()-last_notify>=case['output']['heartbeat_s']:
   event={**event,'job_elapsed_s':time.monotonic()-start,'observed_at_unix_s':time.time(),'observation_note':'最近一次读取的已接受态；checkpoint 步号单列'};print(json.dumps(event,ensure_ascii=False),flush=True);write(out/'progress.json',event);last_notify=time.monotonic()
 def guard():
  if time.monotonic()>=deadline:raise TimeoutError('resource_budget_exhausted: job wall')
  if size(out)>case['resources']['output_bytes'] or rss()>case['resources']['rss_bytes']:raise RuntimeError('resource_budget_exhausted: output/RSS')
 def stage(label,phase,target,state,kind,localcase=case):
  nonlocal spent,branch_spent
  spent=costs.total();guard();folder=out/label;config=out/(label+'.native.dat');remaining=case['resources']['max_fields']-spent
  if remaining<1:raise RuntimeError('field_budget_exhausted')
  native_config(config,localcase,deadline-time.monotonic(),remaining);args=[str(binary),str(config),str(kernel),str(state),str(folder),phase,str(target),str(localcase['static']['tol_Apm']),str(case['output']['save_every']),localcase['identity'],kind];write(out/(label+'.request.json'),{'command':args,'actual_requested_case_identity':localcase['identity']});begin=time.monotonic();proc=None;reservation=costs.reserve(remaining,case['resources']['max_fields'],label)
  try:
   with (out/(label+'.stdout')).open('wb') as stdout,(out/(label+'.stderr')).open('wb') as stderr:
    proc=subprocess.Popen(args,stdout=stdout,stderr=stderr)
    try:
     while proc.poll() is None:
      guard();progress=folder/'progress.json'
      if progress.exists():
       try:notify(json.loads(progress.read_text()))
       except json.JSONDecodeError:pass
      else:notify({'phase':label,'native_state':'starting'})
      time.sleep(.05)
     if proc.returncode:raise RuntimeError((folder/'failure.txt').read_text() if (folder/'failure.txt').exists() else 'native_interrupted returncode='+str(proc.returncode)+'; '+(out/(label+'.stderr')).read_text())
    finally:
     if proc.poll() is None:proc.kill();proc.wait()
  finally:
   result=folder/'result.json';failure=folder/'failure.json';counter=folder/'counter.json';data={}
   for record in [result,failure,counter]:
    try:data=json.loads(record.read_text());break
    except (FileNotFoundError,json.JSONDecodeError):pass
   fields=data.get('fields',data.get('fields_started',data.get('started_fields')))
   if fields is None and proc is not None:
    report['unconfirmed_field_upper_bound']=remaining;branch_spent+=remaining;spent=costs.total()
   else:
    charged=fields or 0;spent=costs.settle(reservation,charged);branch_spent+=charged
   ledger.append({'label':label,'wall_s':time.monotonic()-begin,'fields':fields,'returncode':None if proc is None else proc.returncode});write(out/'ledger.json',ledger)
   if (folder/'checkpoint.bin').exists():checkpoint_sidecar(folder/'checkpoint.bin',localcase,binary,kernel,'dynamic' if phase=='dynamic' else 'static',spent,costs,branch_spent)
  return folder,json.loads((folder/'result.json').read_text())
 def independently(folder,localcase=case,checkpoint=True):
  nonlocal spent,branch_spent
  spent=costs.total();guard()
  if spent>=case['resources']['max_fields']:raise RuntimeError('field_budget_exhausted: independent check')
  reservation=costs.reserve(1,case['resources']['max_fields'],folder.name+'-independent');spent=costs.settle(reservation,1);branch_spent+=1;before=time.monotonic();check=verify(folder,localcase,kernel);ledger.append({'label':folder.name+'-independent','wall_s':time.monotonic()-before,'fields':1});write(folder/'independent.json',check)
  if not check['passed']:raise RuntimeError('independent field/energy/identity verification failed')
  if checkpoint:checkpoint_sidecar(folder/'checkpoint.bin',localcase,binary,kernel,'static' if folder.name=='static' else 'dynamic',spent,costs,branch_spent)
  guard();return check
 try:
  kernel,kmeta=get(case,deadline,notify);write(out/'kernel.json',kmeta);guard()
  if resume_meta and resume_meta['kernel_sha256']!=sha(kernel):raise ValueError('resume kernel identity mismatch')
  seed=Path(case['resume']['checkpoint']) if resume_meta else out/'seed.f64';kind='checkpoint' if resume_meta else 'seed'
  if resume_meta and resume_meta['phase']=='static':
   if resume_meta['dynamic_steps']!=case['dynamic']['steps']:raise ValueError('static resume cannot change completed dynamic interval')
   dynamic=None
  else:
   dynamic,dresult=stage('dynamic','dynamic',case['dynamic']['steps'],seed,kind);icheck=independently(dynamic/'initial',checkpoint=False);dcheck=independently(dynamic);seed=dynamic/'checkpoint.bin';kind='checkpoint';write(out/'dynamic_summary.json',dresult)
   report['dynamic_diagnostics']=dynamic_diagnostics(case,dresult)
   if case['validation']['step_sensitivity']:
    if resume_meta:raise ValueError('step sensitivity requires fresh common initial state')
    fine=copy.deepcopy(case);fine['dynamic']['dt_fs']/=2;fine['dynamic']['steps']*=2;fine['identity']=digest({'physics':{'geometry':fine['geometry'],'material':fine['material'],'field':fine['field']['H_Apm']},'dt_fs':fine['dynamic']['dt_fs'],'schema':fine['schema']})
    tight,tresult=stage('dt_half','dynamic',fine['dynamic']['steps'],out/'seed.f64','seed',fine);tcheck=independently(tight,fine)
    if not tcheck['passed']:raise RuntimeError('dt_half independent verification failed')
    a=np.fromfile(dynamic/'final.bin',dtype='<f8').reshape(m.shape);b=np.fromfile(tight/'final.bin',dtype='<f8').reshape(m.shape);q=np.linalg.norm(a-b,axis=-1);mx=float(q.max());rms=float(np.sqrt(np.mean(q*q)));report['dynamic_step_sensitivity']={'status':'passed' if mx<=case['validation']['max_chord'] and rms<=case['validation']['rms_chord'] else 'not_met','max_chord':mx,'rms_chord':rms,'engineering_target':case['validation']}
  static,sresult=stage('static','static' if resume_meta and resume_meta['phase']=='static' else 'static_fresh',case['static']['max_updates'],seed,kind);check=independently(static);report['static_criterion']={'status':'met' if sresult['stop_reason']=='residual_tolerance' and check['static_criterion_met'] else 'not_met','requested_tol_Apm':case['static']['tol_Apm'],'independent':check,'native_stop_reason':sresult['stop_reason']};final=np.fromfile(static/'final.bin',dtype='<f8').reshape(m.shape);np.savez(out/'magnetic_final.npz',m=final,cell_nm=case['geometry']['cell_nm'],origin_nm=case['geometry']['origin_nm']);report['structure_goal']=observe(final,case,deadline);report['stop_reason']=sresult['stop_reason'];report['final_checkpoint']=str(static/'checkpoint.bin');report['final_checkpoint_metadata']=str(static/'checkpoint.bin.json');report['static_result']=sresult;guard()
  svg_snapshot(out/'magnetic_final.svg',final,case);guard();report['mandatory_outputs_written']=True
  report['execution_completed']=requirements_met(report);report['execution_status']='completed' if report['execution_completed'] else 'criteria_not_met'
  if sresult['stop_reason']=='step_budget':report['execution_status']='budget_stopped'
  elif report['static_criterion']['status']!='met':report['stop_reason']='independent_static_criterion_not_met'
  elif not report['execution_completed']:report['stop_reason']='requested_validation_not_met'
 except Exception as error:
  report['execution_completed']=False;report['mandatory_outputs_written']=False;report['execution_status']='failed'
  report['stop_reason']='resource_budget_exhausted' if isinstance(error,TimeoutError) or 'budget' in str(error) else 'output_write_failed' if isinstance(error,OSError) else 'external_interrupted' if 'native_interrupted' in str(error) else 'failed_input_or_verification';report['failure_detail']=str(error)
 finally:
  checkpoints=[p for p in out.glob('*/checkpoint.bin') if Path(str(p)+'.json').exists()]
  if checkpoints:report['last_complete_checkpoint']=str(max(checkpoints,key=lambda p:p.stat().st_mtime_ns))
  spent=costs.total();report['started_fields']=spent;report['branch_fields']=branch_spent;report['new_fields']=branch_spent-initial_branch_spent;report['wall_s']=time.monotonic()-start;report['feedback']=hints(report)
  try:costs.record_run_cost(report['wall_s'],report['new_fields'],branch_spent)
  except Exception as error:report.update(execution_completed=False,mandatory_outputs_written=False,execution_status='failed',stop_reason='resource_ledger_write_failed',failure_detail=str(error));report['feedback']=hints(report)
  publish_report(out,report,ledger)
 return report
if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('case',type=Path);p.add_argument('--validate-only',action='store_true');a=p.parse_args()
 try:
  import tomllib
  if tomllib.loads(a.case.read_text()).get('schema')=='user_case_v2':
   from current_case import load as load_current
   from run_current_workflow import run as run_current,successful
   result=run_current(load_current(a.case),a.validate_only);code=0 if result.get('valid') or successful(result) else 2
  else:result=run(load(a.case),a.validate_only);code=exit_code(result)
  print(json.dumps(result,indent=2,ensure_ascii=False));sys.exit(code)
 except Exception as e:print(json.dumps({'execution_completed':False,'stop_reason':'input_rejected_before_Model','failure_detail':str(e),'feedback':hints(str(e))},ensure_ascii=False));sys.exit(2)
