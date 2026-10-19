"""Bounded acceptance matrix; writes fresh evidence, never overwrites runs.
Run with Python >=3.11 plus numpy, after build.py --user-workflow.
"""
from pathlib import Path
import argparse,copy,json,struct,subprocess,sys,time
import numpy as np
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'))
from user_case import defaults,resolve_dict,sha
from initial_state import generate
from run_user_workflow import run,preflight,native_config,checkpoint_sidecar
from user_fields import evaluate,residual,verify,MU,LOOKUP
from kernel_cache import get,layout,key_data
from ovf import read

def save(p,x):p.write_text(json.dumps(x,indent=2,ensure_ascii=False)+'\n')
def fixture(base,name,bins):
 r=defaults();r['geometry'].update(n=[7,5,1],cell_nm=[4,5,3],mirrors=[1,1]);r['material'].update(Ms_Apm=[250000,430000],A_Jpm=[4e-12,6e-12],Ah_Jpm3=-6e6,Anh_Jpm=2e-12,D_Jpm2=[0,-.0007],K1_Jpm3=[80000,-40000],K2_Jpm3=[7000,12000],axes=[[1,2,3],[-2,1,4]],alpha=[.02,.035],gamma_H_m_per_As=[210000,235000]);r['field']={'H_Apm':[1500,-2000,3200]};r['initial'].update(kind='smooth',amplitude=.03);r['dynamic'].update(dt_fs=1,T_ps=.064);r['static']['max_updates']=32;r['output'].update(directory=str(base/name),cache=str(base/'cache'),bins=str(bins),save_every=16);r['resources'].update(wall_s=180,kernel_s=120);return r

def ovf(path,m,g,fmt='Text',endian='<',unit='1'):
 n=g['n'];lines=['# OOMMF OVF 2.0','# Segment count: 1','# Begin: Segment','# Begin: Header','# meshtype: rectangular','# meshunit: nm','# valuedim: 3','# valueunits: '+unit]
 for a,k in enumerate('xyz'):lines += [f'# {k}nodes: {n[a]}',f'# {k}stepsize: {g["cell_nm"][a]}',f'# {k}base: {g["origin_nm"][a]+g["cell_nm"][a]/2}']
 lines += ['# End: Header','# Begin: Data '+fmt];b=('\n'.join(lines)+'\n').encode()
 if fmt=='Text':b+=('\n'.join(' '.join(format(x,'.17g') for x in row) for row in m.reshape(-1,3))+'\n').encode()
 else:
  w=int(fmt[-1]);kind='f' if w==4 else 'd';b+=struct.pack(endian+kind,1234567. if w==4 else 123456789012345.)+m.astype(endian+kind).tobytes()+b'\n'
 path.write_bytes(b+('# End: Data '+fmt+'\n# End: Segment\n').encode())

def rejected(f):
 try:f()
 except (ValueError,TypeError,KeyError,OverflowError,FileNotFoundError):return
 raise AssertionError('invalid input was accepted')

def contract(base,bins):
 r=fixture(base,'contract-unused',bins);checks=0
 for section,key,val in [('geometry','n',[7,5,2]),('geometry','n',[True,5,1]),('geometry','pbc',[1,0,0]),('geometry','mirrors',[-1,1]),('geometry','cell_nm',[1,1,5]),('material','Ms_Apm',[0,1]),('material','A_Jpm',[-1,0]),('material','alpha',[-.1,0]),('material','gamma_H_m_per_As',[0,1]),('material','axes',[[0,0,0],[0,0,1]]),('material','Anh_Jpm',1),('dynamic','dt_fs',0),('dynamic','T_ps',.0645),('static','tol_Apm',0),('initial','kind','OVF1'),('material','bad',1),('resources','max_fields',1),('geometry','n',[2,5,1]),('material','Ah_Jpm3',float('nan')),('output','goal','unknown')]:
  q=copy.deepcopy(r);q[section][key]=val;rejected(lambda:resolve_dict(q));checks+=1
 for val in [{},dict(H_Apm=[0,0,0],mu0_H_T=[0,0,0])]:
  q=copy.deepcopy(r);q['field']=val;rejected(lambda:resolve_dict(q));checks+=1
 for key in ['Ah_Jpm3','Anh_Jpm']:
  q=copy.deepcopy(r);q['material'][key]=0;resolve_dict(q);checks+=1
 q=copy.deepcopy(r);q['field']={'mu0_H_T':[0,0,.001]};assert abs(resolve_dict(q)['field']['H_Apm'][2]-795.7747154594767)<1e-12;checks+=1
 c=resolve_dict(r);before=list((base/'cache').glob('*')) if (base/'cache').exists() else [];assert run(c,True)['new_Model_calls']==0;assert before==(list((base/'cache').glob('*')) if (base/'cache').exists() else []);checks+=1
 # Synthetic OVF exercises all formats/endian, x-fastest ordering and format-specific Ms norms.
 m,_=generate(c);g=c['geometry'];ovfdir=base/'ovf';ovfdir.mkdir(exist_ok=True)
 for fmt,endian in [('Text','<'),('Binary 4','<'),('Binary 4','>'),('Binary 8','<'),('Binary 8','>')]:
  path=ovfdir/(fmt.replace(' ','')+('le' if endian=='<' else 'be')+'.ovf');ovf(path,m[0]*c['material']['Ms_Apm'][0],g,fmt,endian,'A/m');v,meta=read(path,g,c['material']['Ms_Apm'][0],'magnetization_Apm');assert np.max(np.linalg.norm(v-m[0],axis=-1))<(1e-7 if fmt=='Binary 4' else 1e-14);checks+=1
  rejected(lambda:read(path,g,c['material']['Ms_Apm'][0]*1.01,'magnetization_Apm'));checks+=1
 bad=ovfdir/'bad.ovf';ovf(bad,m[0]*0,g);rejected(lambda:read(bad,g,1,'direction'));checks+=1
 ovf(bad,m[0],g,'Binary 8');b=bytearray(bad.read_bytes());i=b.index(b'# Begin: Data Binary 8\n')+len(b'# Begin: Data Binary 8\n');b[i:i+8]=b'badcheck';bad.write_bytes(b);rejected(lambda:read(bad,g,1,'direction'));checks+=1
 q=copy.deepcopy(r);q['geometry']['pbc']=[0,0,0];q['geometry']['mirrors']=[0,0];rejected(lambda:resolve_dict(q));checks+=1
 q=copy.deepcopy(r);q['dynamic']['dt_fs']/=2;fine=resolve_dict(q)
 from user_case import digest
 assert fine['identity']==digest({'physics':{'geometry':fine['geometry'],'material':fine['material'],'field':fine['field']['H_Apm']},'dt_fs':fine['dynamic']['dt_fs'],'schema':fine['schema']});checks+=1
 from run_user_workflow import dynamic_diagnostics
 assert dynamic_diagnostics(c,dict(energy_J=-1e-20,origin_J=-2e-20,total_loss_J=1e-21,loss_A_J=4e-22,loss_B_J=6e-22))['energy_dissipation_defect_J']==1.1e-20;checks+=1
 return {'passed':True,'zero_Model_checks':checks}

def direct_and_gradient(case,kernel,base):
 m,_=generate(case);H,E=evaluate(m,case,kernel);nx,ny,_=case['geometry']['n'];px,py=layout(case);K=np.fromfile(kernel,'<f8').reshape(py,px,6);M=(case['material']['Ms_Apm'][0]*m[0,0]+case['material']['Ms_Apm'][1]*m[1,0])/2;Hd=np.zeros_like(M)
 for y in range(ny):
  for x in range(nx):
   for yy in range(ny):
    for xx in range(nx):
     k=K[(y-yy)%py,(x-xx)%px];Hd[y,x]-=np.array([[k[LOOKUP[a][b]] for b in range(3)] for a in range(3)])@M[yy,xx]
 # Full discrete transform independently checks FFT embedding, including rectangular/open layout.
 pad=np.zeros((py,px,3));pad[:ny,:nx]=M;F=np.fft.rfft2(pad,axes=(0,1));Ks=np.fft.rfft2(K,axes=(0,1));fft=np.stack([np.fft.irfft2(-sum(Ks[...,LOOKUP[a][b]]*F[...,b] for b in range(3)),s=(py,px)) for a in range(3)],-1)[:ny,:nx];error=np.max(np.abs(fft-Hd))/max(1.,np.max(np.abs(Hd)));assert error<=1e-12
 rng=np.random.default_rng(17);direction=rng.normal(size=m.shape);direction-=m*np.sum(m*direction,-1,keepdims=True);direction/=np.linalg.norm(direction);eps=1e-5;V=np.prod(np.array(case['geometry']['cell_nm'])*1e-9);energy_scale=MU*V*nx*ny*max(case['material']['Ms_Apm'])**2/2;errs=[];operations=0
 # Module-wise finite difference prevents strong Ah from concealing D/K/gradient errors.
 for active in [[0,0,0,0],[1,0,0,0],[0,1,0,0],[0,0,1,0],[0,0,0,1],[1,1,1,1]]:
  c=copy.deepcopy(case);c['material']['active']=active;field,_=evaluate(m,c,kernel);a=m+eps*direction;b=m-eps*direction;a/=np.linalg.norm(a,axis=-1,keepdims=True);b/=np.linalg.norm(b,axis=-1,keepdims=True);_,ea=evaluate(a,c,kernel);_,eb=evaluate(b,c,kernel);numerical=(ea.sum()-eb.sum())/(2*eps);analytic=-MU*V/2*sum(c['material']['Ms_Apm'][i]*np.sum(field[i]*direction[i]) for i in [0,1]);err=abs(numerical-analytic)/max(energy_scale,abs(analytic));assert err<=1e-6,(active,err);errs.append(err);operations+=3
 return {'direct_fft_error':float(error),'module_gradient_errors':errs,'independent_field_operations':operations+1}

def small(base,bins,serial_bins=None):
 evidence={};raw=fixture(base,'M',bins);raw['validation']['step_sensitivity']=True;save(base/'M_input.json',raw);c=resolve_dict(raw);result=run(c);assert result['stop_reason']=='step_budget',result;assert result['static_criterion']['independent']['passed'];assert result['dynamic_step_sensitivity']['status']=='passed';evidence['M']=result
 kernel,meta=get(c,time.monotonic()+120);assert meta['cache_hit'];evidence['M_direct_gradient']=direct_and_gradient(c,kernel,base)
 # Dynamic split and static continuation. Same numerical identity; policy/limits are lineage metadata.
 first=copy.deepcopy(raw);first['validation']['step_sensitivity']=False;first['dynamic']['T_ps']=.032;first['static']['max_updates']=16;first['output']['directory']=str(base/'M_first');evidence['M_first']=run(resolve_dict(first))
 second=copy.deepcopy(raw);second['validation']['step_sensitivity']=False;second['output']['directory']=str(base/'M_resumed');second['resume']={'checkpoint':str(base/'M_first/dynamic/checkpoint.bin'),'metadata':str(base/'M_first/dynamic/checkpoint.bin.json')};evidence['M_resumed']=run(resolve_dict(second))
 for name in ['dynamic/final.bin','static/final.bin','static/checkpoint.bin']:assert (base/'M'/name).read_bytes()==(base/'M_resumed'/name).read_bytes(),name
 sr=copy.deepcopy(second);sr['resume']={'checkpoint':str(base/'M_first/static/checkpoint.bin'),'metadata':str(base/'M_first/static/checkpoint.bin.json')};sr['dynamic']['T_ps']=.032;sr['output']['directory']=str(base/'M_static_resumed');evidence['M_static_resumed']=run(resolve_dict(sr))
 # Independent continuous static run from the same 32-step dynamic endpoint.
 cfg=base/'static_control.dat';native_config(cfg,c,10,33);control=base/'static_control';begin=time.monotonic();proc=subprocess.run([str(bins/'fim_user'),str(cfg),str(kernel),str(base/'M_first/dynamic/checkpoint.bin'),str(control),'static_fresh','32','1','16',c['identity'],'checkpoint'],capture_output=True,timeout=10);assert proc.returncode==0,proc.stderr
 check=verify(control,c,kernel);assert check['passed'];assert (control/'checkpoint.bin').read_bytes()==(base/'M_static_resumed/static/checkpoint.bin').read_bytes();evidence['static_control']={'native_fields':33,'independent_fields':1,'wall_s':time.monotonic()-begin,'check':check}
 # Corrupted cache and CP, changed dt and unsupported legacy resume are rejected before Model.
 cp=base/'corrupt.cp';cp.write_bytes((base/'M/dynamic/checkpoint.bin').read_bytes()[:-1]);q=copy.deepcopy(second);q['resume']['checkpoint']=str(cp);rejected(lambda:preflight(resolve_dict(q)))
 q=copy.deepcopy(second);q['dynamic']['dt_fs']=.5;rejected(lambda:preflight(resolve_dict(q)))
 damaged=base/'damaged-cache';damaged.mkdir();token=Path(kernel).parent.name;import shutil;shutil.copytree(Path(kernel).parent,damaged/token);p=damaged/token/'kernel.f64';p.write_bytes(p.read_bytes()[:-8]);q=copy.deepcopy(c);q['output']['cache']=str(damaged);rejected(lambda:get(q,time.monotonic()+10));evidence['identity_rejections']=3
 # G open rectangular mesh, OVF A/B non-collinear, all physical field terms allowed by v1.
 g=fixture(base,'G',bins);g['geometry'].update(n=[5,4,1],cell_nm=[3,4,2],pbc=[0,0,0],mirrors=[0,0]);g['material']['Anh_Jpm']=0;g['dynamic']['T_ps']=.032;g['initial'].update(kind='uniform',relation='independent',A=[.2,.1,1],B=[-.1,.2,-1]);gc=resolve_dict(g);m,_=generate(gc)
 for i,s in enumerate(['A','B']):ovf(base/(s+'.ovf'),m[i],gc['geometry'],'Binary 8' if i else 'Text');g['initial']['ovf_'+s]=str(base/(s+'.ovf'))
 g['initial']['kind']='ovf2';gc=resolve_dict(g);evidence['G']=run(gc);assert evidence['G']['static_criterion']['independent']['passed'];gk,_=get(gc,time.monotonic()+120);evidence['G_direct_gradient']=direct_and_gradient(gc,gk,base)
 z=fixture(base,'Z',bins);z['geometry'].update(n=[4,3,1],mirrors=[2,1]);z['material'].update(Ms_Apm=[300000,300000],A_Jpm=[0,0],Ah_Jpm3=0,Anh_Jpm=0,D_Jpm2=[0,0],K1_Jpm3=[0,0],K2_Jpm3=[0,0],alpha=[0,0]);z['field']={'H_Apm':[0,0,0]};z['initial'].update(kind='uniform',A=[0,0,1]);z['dynamic']['T_ps']=.002;z['static']['max_updates']=0;evidence['Z']=run(resolve_dict(z));assert evidence['Z']['execution_completed'];assert evidence['Z']['static_result']['total_loss_J']==0;assert evidence['Z']['static_criterion']['independent']['A_B_Apm']==[0,0]
 # Native isolated-module probes, one eval each, to compare independent terms without domination.
 probes=[]
 for j,active in enumerate([[0,0,0,0],[1,0,0,0],[0,1,0,0],[0,0,1,0],[0,0,0,1]]):
  q=copy.deepcopy(c);q['material']['active']=active;seed=base/f'probe{j}.f64';m,_=generate(q);m.astype('<f8').tofile(seed);cfg=base/f'probe{j}.dat';native_config(cfg,q,10,1);out=base/f'probe{j}';cmd=[str(bins/'fim_user'),str(cfg),str(kernel),str(seed),str(out),'static_fresh','0','1','16',q['identity'],'seed'];t=time.monotonic();p=subprocess.run(cmd,capture_output=True,timeout=10);assert p.returncode==0,p.stderr;check=verify(out,q,kernel);assert check['passed'];probes.append({'native_fields':1,'independent_fields':1,'wall_s':time.monotonic()-t,'check':check})
 evidence['probes']=probes
 if serial_bins:
  q=copy.deepcopy(c);cfg=base/'serial.dat';native_config(cfg,q,10,1);out=base/'serial-probe';seed=base/'M/seed.f64';p=subprocess.run([str(serial_bins/'fim_user'),str(cfg),str(kernel),str(seed),str(out),'static_fresh','0','1','16',q['identity'],'seed'],capture_output=True,timeout=10);assert p.returncode==0,p.stderr;check=verify(out,q,kernel);assert check['passed'];assert (out/'final.bin').read_bytes()==(base/'M/dynamic/initial/final.bin').read_bytes();assert (out/'final_H_A.bin').read_bytes()==(base/'M/dynamic/initial/final_H_A.bin').read_bytes();evidence['serial_probe']={'native_fields':1,'independent_fields':1,'passed':True}
 # Real exhausted field budget, with a valid last checkpoint and no success assertion.
 q=fixture(base,'field_budget',bins);q['resources']['max_fields']=323;q['static']['max_updates']=32;evidence['field_budget']=run(resolve_dict(q));assert not evidence['field_budget']['execution_completed'];assert evidence['field_budget']['stop_reason']=='resource_budget_exhausted';assert evidence['field_budget']['started_fields']==323
 # Goal mismatch is separate from an independently met static criterion.
 q=resolve_dict(z);q['output']['goal']='single_skyrmion';from user_structure import observe
 structure=observe(np.fromfile(base/'Z/static/final.bin','<f8').reshape(2,1,3,4,3),q);assert structure['status']=='not_met';evidence['goal_mismatch']=structure
 save(base/'small_evidence.json',evidence);return evidence

def interrupted(base,bins):
 import run_user_workflow as workflow
 r=fixture(base,'external_interrupt',bins);r['resources']['max_fields']=400;real=workflow.subprocess.Popen;forced=[]
 def stop_after_checkpoint(*a,**kw):
  p=real(*a,**kw);deadline=time.monotonic()+3;cp=base/'external_interrupt/dynamic/checkpoint.bin'
  while not cp.exists() and p.poll() is None and time.monotonic()<deadline:time.sleep(.0001)
  if p.poll() is None and cp.exists():p.kill();p.wait();forced.append(True)
  return p
 workflow.subprocess.Popen=stop_after_checkpoint
 try:result=run(resolve_dict(r))
 finally:workflow.subprocess.Popen=real
 assert forced and result['stop_reason']=='external_interrupted' and not result['execution_completed'];cp=base/'external_interrupt/dynamic/checkpoint.bin';assert Path(result['last_complete_checkpoint']).resolve()==cp.resolve()
 resume=fixture(base,'interrupt_validate_only',bins);resume['resume']={'checkpoint':str(cp),'metadata':str(cp)+'.json'};assert preflight(resolve_dict(resume))[3]['new_Model_calls']==0
 save(base/'interrupted_evidence.json',result);return result

def canonical(base,bins):
 r=defaults();r['field']={'mu0_H_T':[0,0,-.002]};r['output'].update(directory=str(base/'canonical'),cache=str(base/'cache'),bins=str(bins),save_every=1000,goal='single_skyrmion');r['resources']['wall_s']=180;save(base/'canonical_input.json',r);result=run(resolve_dict(r));assert result['execution_completed'],result;assert result['static_criterion']['status']=='met';assert result['structure_goal']['status']=='met';save(base/'canonical_evidence.json',result);return result
if __name__=='__main__':
 a=argparse.ArgumentParser();a.add_argument('--out',type=Path,required=True);a.add_argument('--bins',type=Path,required=True);a.add_argument('--serial-bins',type=Path);a.add_argument('--mode',choices=['contract','small','canonical','interrupted'],required=True);x=a.parse_args();x.out.mkdir(parents=True,exist_ok=True);t=time.monotonic();r=contract(x.out,x.bins) if x.mode=='contract' else small(x.out,x.bins,x.serial_bins) if x.mode=='small' else interrupted(x.out,x.bins) if x.mode=='interrupted' else canonical(x.out,x.bins);save(x.out/(x.mode+'_receipt.json'),{'passed':True,'wall_s':time.monotonic()-t,'mode':x.mode,**(r if x.mode=='contract' else {})});print('PASS',x.mode)
