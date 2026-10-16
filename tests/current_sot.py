"""Finite effective-SOT acceptance. Reuses a supplied qualified static CP, never reruns relax."""
from pathlib import Path
import argparse,copy,csv,json,subprocess,sys,time
import numpy as np
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'))
from user_case import defaults,sha
from current_case import resolve,drive_rhs,MUB_E
from run_current_workflow import run,scale
from run_user_workflow import native_config
from initial_state import generate
from user_structure import observe
from current_motion import rows

def save(p,v):p.write_text(json.dumps(v,indent=2,ensure_ascii=False)+'\n')
def raw_case(out,bins,checkpoint=None):
 r=defaults();r['schema']='user_case_v2';r['workflow']={'mode':'driven_dynamic'};r['drive']={'kind':'constant','Jc_Apm2':[1e11,0,0],'incident_direction':[0,0,1],'xi':[.1,.1],'field_like_ratio':[0,0]};r['field']={'mu0_H_T':[0,0,-.002]};r['dynamic'].update(dt_fs=25,T_ps=2);r['output'].update(directory=str(out),cache=str(out.parent/'cache'),bins=str(bins),save_every=1000000,goal='observe',times_ps=[0,.2,.4,.5,.6,.8,1,1.2,1.4,1.5,1.6,1.8,2]);r['resources'].update(wall_s=180,kernel_s=120,max_fields=1000000)
 if checkpoint:r['initial']={'kind':'checkpoint_directions','checkpoint':str(checkpoint),'metadata':str(checkpoint)+'.json'}
 return r

def scalar(out):
 r=list(csv.DictReader((out/'scalar_checks/rhs_cases.csv').open()));err=0;oracle=0
 for row in r:
  a=lambda *keys:np.array([float(row[k]) for k in keys]);m=a('mx','my','mz');H=a('Hx','Hy','Hz');q=np.cross(a('dx','dy','dz'),np.array([float(row['Jx']),float(row['Jy']),0.]));ms=float(row['Ms']);gamma=float(row['gamma']);alpha=float(row['alpha']);xi=float(row['xi']);ratio=float(row['r']);C=xi*MUB_E/(ms*3e-9);f=C/(1+alpha**2)*((1+alpha*ratio)*np.cross(m,np.cross(m,q))+(ratio-alpha*(m@m))*np.cross(m,q));actual=a('drive_x','drive_y','drive_z');err=max(err,float(np.linalg.norm(f-actual)/1e9))
  # Literal pinned BORIS field on full M, then its AFM LLG, divided by own Ms.
  M=ms*m;hd=-(xi*MUB_E/gamma)/(ms*ms*3e-9)*(np.cross(M,q)+ratio*ms*q);hf=H+hd;expected=-gamma/(1+alpha**2)*(np.cross(M,hf)+alpha*np.cross(M/ms,np.cross(M,hf)))/ms;oracle=max(oracle,float(np.linalg.norm(expected-a('fx','fy','fz'))/1e9))
 assert err<=1e-12 and oracle<=1e-12
 rr=list(csv.DictReader((out/'scalar_checks/macro.csv').open()));ratios=[]
 for kind in ['0','1']:
  for sub in ['0','1']:
   a=sorted([x for x in rr if x['kind']==kind and x['sub']==sub],key=lambda x:int(x['steps']))
   for lo,hi in zip(a,a[1:]):
    el,eh=float(lo['error']),float(hi['error']);limited=bool(min(el,eh)<=100*np.finfo(float).eps);ratio=el/eh
    assert limited or 12<=ratio<=20,(kind,sub,ratio)
    ratios.append({'kind':kind,'sub':sub,'ratio':ratio,'roundoff_limited':limited})
 answer={'passed':True,'independent_RHS_error':err,'BORIS_literal_oracle_error':oracle,'macro_max_direction_error':max(float(x['error']) for x in rr),'order_ratios':ratios,'Models':0,'fields':0,'scalar_RHS':json.loads((out/'scalar_checks/result.json').read_text())['scalar_vector_RHS']};save(out/'SCALAR_INDEPENDENT.json',answer);return answer

def compat(out,bins,reference):
 r=raw_case(out/'zero_compat_new',bins);r['drive']['Jc_Apm2']=[0,0,0];r['dynamic'].update(dt_fs=12.5,T_ps=.2);r['output']['times_ps']=[0,.2];c=resolve(r);new=run(c);assert new['execution_completed'],new;seed=out/'zero_compat_new/seed.f64';cfg=out/'zero_compat_old.dat';native_config(cfg,c,30,81);from kernel_cache import get
 kernel,_=get(c,time.monotonic()+120);p=subprocess.run([str(reference/'fim_user'),str(cfg),str(kernel),str(seed),str(out/'zero_compat_old'),'dynamic','16','1','1000000',c['conservative_identity'],'seed'],capture_output=True,timeout=30);assert p.returncode==0,p.stderr;old=json.loads((out/'zero_compat_old/result.json').read_text());native=new['native_result']
 for name in ['final.bin','final_H_A.bin','final_H_B.bin','final_Hd.bin','final_energy.json']:assert (out/'zero_compat_old'/name).read_bytes()==(out/'zero_compat_new/driven'/name).read_bytes(),name
 for x,y in [('energy_J','energy_J'),('origin_J','origin_J'),('loss_A_J','D_A_J'),('loss_B_J','D_B_J'),('total_loss_J','D_J')]:assert old[x]==native[y],(x,old[x],native[y])
 assert new['motion']['current_direction'] is None
 for sub in new['motion']['sublattices']:assert sub['directional_status']=='not_applicable' and sub['Hall_deg'] is None and sub['v_parallel_mps'] is None and sub['v_perp_mps'] is None and sub['velocity_vector_mps'] is None
 answer={'passed':True,'native_fields':81+native['fields'],'independent_fields':new['independent']['fields'],'new_workflow_fields':new['new_fields'],'byte_equal':['m','H_A','H_B','Hd','energy_parts'],'loss_and_origin_equal':True,'zero_current_directional_values_null':True};save(out/'ZERO_COMPAT.json',answer);return answer

def spatial(out,bins,cp):
 index={}
 for name,xi,j in [('zero',[.1,.1],0),('symmetric',[.1,.1],1e11),('A_only',[.1,0],1e11),('B_only',[0,.1],1e11),('reverse',[.1,.1],-1e11)]:
  for dt in [25,12.5,6.25]:
   folder=out/(name+'_'+str(dt));answer=None
   if (folder/'report.json').exists():
    prior=json.loads((folder/'report.json').read_text())
    if prior['execution_completed']:answer=prior
    else:folder=folder.with_name(folder.name+'_retry1')
   r=raw_case(folder,bins,cp);r['drive'].update(xi=xi,Jc_Apm2=[j,0,0]);r['dynamic']['dt_fs']=dt;c=resolve(r)
   if answer is None:save(out/(folder.name+'.input.json'),r);answer=run(c);save(out/(folder.name+'.receipt.json'),answer)
   index[name+'_'+str(dt)]=str(folder)
   if not answer['execution_completed']:raise AssertionError((name,dt,answer))
   # Native every-accepted observer vs existing independent Python triangle/contour code.
   m=np.fromfile(folder/'driven/final.bin','<f8').reshape(2,1,125,125,3);ind=observe(m,c);native=[x for x in rows(folder/'driven/observations.csv') if int(x['step'])==c['dynamic']['steps']]
   for i in [0,1]:
    v=ind['sublattices'][i];assert abs(float(native[i]['Q'])-v['Q_triangle'])<=1e-10;assert abs(float(native[i]['radius_nm'])-v['radius_nm'])<=1e-8;assert np.linalg.norm(np.array(v['center_nm'])-[float(native[i]['wrapped_x_nm']),float(native[i]['wrapped_y_nm'])])<=1e-7
 save(out/'SPATIAL_CASE_INDEX.json',index);compare={};bounds=np.array([1e-4,4e-5]);rmsbounds=np.array([7e-6,2.5e-6]);Escale=scale(resolve(raw_case(out/'unused',bins,cp)))
 for name in ['zero','symmetric','A_only','B_only','reverse']:
  maxima={};fine=Path(index[name+'_6.25'])/'driven';fr={round(float(x['time_ps']),9):x for x in rows(fine/'history.csv')}
  for dt in [25,12.5]:
   folder=Path(index[name+'_'+str(dt)])/'driven';rr={round(float(x['time_ps']),9):x for x in rows(folder/'history.csv')};mx=np.zeros(2);rm=np.zeros(2);en=np.zeros(3);defect=0
   for t in [0,.2,.4,.5,.6,.8,1,1.2,1.4,1.5,1.6,1.8,2]:
    a=np.fromfile(folder/f'step_{round(t*1000/dt)}.bin','<f8').reshape(2,-1,3);b=np.fromfile(fine/f'step_{round(t*1000/6.25)}.bin','<f8').reshape(2,-1,3);q=np.linalg.norm(a-b,axis=-1);mx=np.maximum(mx,q.max(1));rm=np.maximum(rm,np.sqrt(np.mean(q*q,axis=1)));en=np.maximum(en,[abs(float(rr[t][k])-float(fr[t][k]))/Escale for k in ['E_J','D_J','P_J']]);defect=max(defect,abs(float(rr[t]['defect_J']))/Escale,abs(float(fr[t]['defect_J']))/Escale)
   factor=.25 if dt==12.5 else 1.;passed=bool(np.all(mx<=factor*bounds) and np.all(rm<=factor*rmsbounds) and np.max(en)<=factor*1e-7 and defect<=2e-7);maxima[str(dt)]={'passed':passed,'max_A_B':mx.tolist(),'rms_A_B':rm.tolist(),'E_integralD_integralP_over_Estar':en.tolist(),'balance_defect_over_Estar':defect}
  compare[name]=maxima
 save(out/'THREE_LEVEL_COMPARISON.json',compare);assert all(v['passed'] for case in compare.values() for v in case.values()),compare;return compare

def restore(out,bins,cp):
 full=out/'symmetric_25';r=raw_case(out/'split_first',bins,cp);r['dynamic']['T_ps']=1;r['output']['times_ps']=[t for t in r['output']['times_ps'] if t<=1];first=run(resolve(r));assert first['execution_completed'],first
 r=raw_case(out/'split_resumed',bins,cp);r['resume']={'checkpoint':first['final_checkpoint'],'metadata':first['final_checkpoint_metadata']};second=run(resolve(r));assert second['execution_completed'],second
 for name in ['checkpoint.bin','final.bin','final_H_A.bin','final_H_B.bin','final_Hd.bin','final_energy.json']:assert (out/'split_resumed/driven'/name).read_bytes()==(full/'driven'/name).read_bytes(),name
 for key in ['step','energy_J','origin_J','D_A_J','D_B_J','D_J','P_A_J','P_B_J','P_J']:assert second['native_result'][key]==json.loads((full/'report.json').read_text())['native_result'][key],key
 expected=[q for q in rows(full/'driven/observations.csv') if int(q['step'])>=40];actual=rows(out/'split_resumed/driven/observations.csv');assert expected==actual
 from user_costs import ResourceCosts
 before=ResourceCosts(out/'unused',json.loads(Path(first['final_checkpoint_metadata']).read_text())).total();assert before==second['started_fields'] and before>first['started_fields']
 save(out/'RESTORE_CHECK.json',{'passed':True,'first_new_fields':first['new_fields'],'second_new_fields':second['new_fields'],'restored_native_CP_and_final_fields_bytes_equal':True,'D_P_and_time_equal':True,'accepted_observations_and_unwrap_equal':True,'old_checkpoint_resource_floor_now':before,'first_checkpoint_recorded_cost':first['started_fields'],'Models':2});return second

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);p.add_argument('--bins',type=Path,default=ROOT/'build-sot');p.add_argument('--reference-bins',type=Path,default=ROOT/'build');p.add_argument('--static-checkpoint',type=Path);p.add_argument('--mode',choices=['scalar','compat','spatial','restore'],required=True);a=p.parse_args();a.out.mkdir(parents=True,exist_ok=True);result=scalar(a.out) if a.mode=='scalar' else compat(a.out,a.bins.resolve(),a.reference_bins.resolve()) if a.mode=='compat' else restore(a.out,a.bins.resolve(),a.static_checkpoint.resolve()) if a.mode=='restore' else spatial(a.out,a.bins.resolve(),a.static_checkpoint.resolve());print('PASS',a.mode)
