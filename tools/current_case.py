"""Constant effective SOT contract; v1 relax inputs are not silently reinterpreted."""
from pathlib import Path
import copy,json,struct,tomllib,math
import numpy as np
from user_case import resolve_dict,vec,number,digest,sha
from initial_state import generate
MUB_E=5.788381608e-5

def resolve(raw,base=Path('.')):
 raw=copy.deepcopy(raw)
 if raw.pop('schema',None)!='user_case_v2':raise ValueError('current workflow requires user_case_v2')
 workflow=raw.pop('workflow',{})
 if workflow!={'mode':'driven_dynamic'}:raise ValueError('SOT requires driven_dynamic; nonzero drive is not a relax/static state')
 drive=raw.pop('drive',{})
 if set(drive)!={'kind','Jc_Apm2','incident_direction','xi','field_like_ratio'} or drive['kind']!='constant':raise ValueError('only explicit uniform constant SOT supported; STT/pulse/AC unsupported')
 J=vec(drive['Jc_Apm2'],3,'Jc_Apm2');d=vec(drive['incident_direction'],3,'incident_direction');n=math.hypot(*d)
 if J[2]!=0 or n==0 or not math.isfinite(n):raise ValueError('in-plane J and nonzero finite incident direction required')
 xi=vec(drive['xi'],2,'xi');r=vec(drive['field_like_ratio'],2,'field_like_ratio');d=[v/n for v in d]
 events=raw.setdefault('output',{}).pop('times_ps',[])
 if not isinstance(events,list):raise ValueError('times_ps list')
 initial=raw.setdefault('initial',{});handoff=None
 if initial.get('kind')=='checkpoint_directions':
  handoff={key:initial.pop(key,'') for key in ['checkpoint','metadata']};initial['kind']='uniform'
  if not all(isinstance(v,str) and v for v in handoff.values()):raise ValueError('direction handoff requires checkpoint/metadata')
  handoff={k:str((Path(base)/v).resolve()) for k,v in handoff.items()}
 raw['schema']='user_case_v1';case=resolve_dict(raw,base);case['schema']='user_case_v2';case['workflow']=workflow;case['drive']={'kind':'constant','Jc_Apm2':J,'incident_direction':d,'incident_direction_input':drive['incident_direction'],'xi':xi,'field_like_ratio':r,'muB_over_e_m2_per_s':MUB_E,'thickness_m':case['geometry']['cell_nm'][2]*1e-9};case['handoff']=handoff
 if any(not math.isfinite(x*MUB_E/(m*case['drive']['thickness_m'])) for x,m in zip(xi,case['material']['Ms_Apm'])):raise ValueError('SOT coefficient numerical range')
 case['output']['times_ps']=[number(v,'times_ps',low=0) for v in events];steps=[]
 for t in case['output']['times_ps']:
  k=t*1000/case['dynamic']['dt_fs']
  if t>case['dynamic']['T_ps'] or abs(k-round(k))>8*math.ulp(max(1.,k)):raise ValueError('output times must lie on accepted fixed steps, no event clipping')
  steps.append(int(round(k)))
 case['output']['event_steps']=sorted(set(steps));case['drive_sha256']=digest(case['drive']);case['conservative_identity']=case['identity'];case['identity']=digest({'base':case['identity'],'drive':case['drive'],'mode':'driven_dynamic-v1'});return case

def load(path):
 path=Path(path).resolve();return resolve(tomllib.loads(path.read_text()),path.parent)

def shape(case):return (2,*reversed(case['geometry']['n']),3)
def cp_directions(cp,case,metadata):
 p=Path(cp);raw=p.read_bytes();n=int(np.prod(case['geometry']['n']));meta=json.loads(Path(metadata).read_text())
 if meta.get('checkpoint_sha256')!=sha(p) or meta.get('physics_sha256')!=case['physics_sha256'] or meta.get('shape')!=case['geometry']['n']:raise ValueError('handoff/resume checkpoint identity/shape/checksum')
 magic,count,length=struct.unpack_from('<QQQ',raw)
 if count!=n or length!=64 or list(struct.unpack_from('<iii',raw,88))!=case['geometry']['n'] or raw[24:88].decode()!=meta['identity']:raise ValueError('checkpoint native shape/identity length')
 offset=168 if magic==0x3150435245535546 else 164 if magic==0x315043544f534946 else 0
 if not offset or len(raw)!=(168+144*n if offset==168 else 244+48*n):raise ValueError('unsupported/truncated checkpoint directions')
 m=np.frombuffer(raw[offset:offset+48*n],'<f8').copy().reshape(shape(case))
 if not np.isfinite(m).all() or np.max(np.abs(np.linalg.norm(m,axis=-1)-1))>1e-12:raise ValueError('checkpoint direction unit/finite')
 meta['_metadata_path']=str(Path(metadata).resolve());return m,meta

def initial(case):
 if case['resume']['checkpoint']:
  m,meta=cp_directions(case['resume']['checkpoint'],case,case['resume']['metadata']);return m,{'kind':'exact driven checkpoint','source_sha256':meta['checkpoint_sha256']},meta
 if case['handoff']:
  m,meta=cp_directions(case['handoff']['checkpoint'],case,case['handoff']['metadata']);return m,{'kind':'explicit fresh driven phase from saved directions','source_sha256':meta['checkpoint_sha256'],'preparation_fields_recorded':meta['spent_fields'],'work_and_time_start_at_zero':True},meta
 m,info=generate(case);return m,info,None

def drive_rhs(m,case):
 c=case['drive'];u=case['material'];q=np.cross(c['incident_direction'],c['Jc_Apm2']);out=np.empty_like(m)
 for i in [0,1]:
  if c['xi'][i]==0 or np.all(q==0):out[i]=0;continue
  alpha=u['alpha'][i];r=c['field_like_ratio'][i];C=c['xi'][i]*MUB_E/(u['Ms_Apm'][i]*c['thickness_m']);out[i]=C/(1+alpha*alpha)*((1+alpha*r)*np.cross(m[i],np.cross(m[i],q))+(r-alpha*np.sum(m[i]*m[i],axis=-1))[...,None]*np.cross(m[i],q))
 return out

def rhs_scale(case):
 c=case['drive'];u=case['material'];return max(1.,max(max(.1,abs(c['xi'][i]))*MUB_E*max(1e11,np.linalg.norm(c['Jc_Apm2']))/(u['Ms_Apm'][i]*c['thickness_m'])*(1+abs(c['field_like_ratio'][i])+u['alpha'][i]) for i in [0,1]))
