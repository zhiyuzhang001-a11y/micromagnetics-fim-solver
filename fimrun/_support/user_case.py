"""Versioned user parameter contract. Validation does not construct kernels or fields."""
from pathlib import Path
import copy,hashlib,json,math,tomllib

def digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def number(x,name,low=None,positive=False):
 if isinstance(x,bool) or not isinstance(x,(int,float)) or not math.isfinite(x):raise ValueError(name+': finite number required')
 if positive and x<=0 or low is not None and x<low:raise ValueError(name+': invalid range')
 return float(x)
def integer(x,name,low,high):
 if isinstance(x,bool) or not isinstance(x,int) or not low<=x<=high:raise ValueError(name+': integer range '+str((low,high)))
 return x
def vec(x,n,name,**kw):
 if not isinstance(x,list) or len(x)!=n:raise ValueError(name+': length '+str(n)+' required')
 return [number(v,name,**kw) for v in x]
def defaults():
 return dict(schema='user_case_v1',geometry=dict(n=[125,125,1],cell_nm=[4,4,3],pbc=[1,1,0],mirrors=[10,10],origin_nm=[0,0,0]),material=dict(Ms_Apm=[300000,600000],A_Jpm=[5e-12,5e-12],Ah_Jpm3=-8e6,Anh_Jpm=-5e-12,D_Jpm2=[.00105,.00105],K1_Jpm3=[109000,109000],K2_Jpm3=[0,0],axes=[[0,0,1],[0,0,1]],alpha=[.01,.01],gamma_H_m_per_As=[221276.1569,221276.1569],active=[1,1,1,1]),field=dict(H_Apm=[0,0,-1591.5494309189535]),initial=dict(kind='canonical_legacy',A=[0,0,1],B=[0,0,-1],relation='antiparallel',amplitude=.01,center_nm=[200,300],radius_nm=25,wall_nm=8,helicity_rad=0,polarity=-1,ovf_A='',ovf_B='',interpretation='direction'),dynamic=dict(dt_fs=100,T_ps=500),static=dict(tol_Apm=1,max_updates=30000),resources=dict(wall_s=600,kernel_s=120,max_fields=1000000,rss_bytes=2147483648,output_bytes=536870912),output=dict(directory='../output/user-case',cache='../output/kernel-cache',bins='../build',save_every=100,heartbeat_s=2,goal='none'),validation=dict(step_sensitivity=False,max_chord=1e-4,rms_chord=1e-5),resume=dict(checkpoint='',metadata=''))
def resolve_dict(raw,base=Path('.')):
 d=defaults();raw=copy.deepcopy(raw)
 for key,v in raw.items():
  if key not in d:raise ValueError('unknown section: '+key)
  if isinstance(d[key],dict):
   if not isinstance(v,dict):raise ValueError('table required: '+key)
   if key=='field':d[key]['mu0_H_T']=[0,0,0]
   if set(v)-set(d[key]):raise ValueError('unknown key: '+key+'.'+next(iter(set(v)-set(d[key]))))
   d[key].update(v)
  else:d[key]=v
 if d['schema']!='user_case_v1':raise ValueError('unsupported schema')
 g=d['geometry'];m=d['material'];i=d['initial'];o=d['output'];v=d['validation'];res=d['resources']
 if len(g['n'])!=3:raise ValueError('n dimension')
 g['n']=[integer(q,'n',1,2**31-1) for q in g['n']]
 if g['n'][2]!=1:raise ValueError('v1 supports nz=1 only')
 g['cell_nm']=vec(g['cell_nm'],3,'cell_nm',positive=True);g['origin_nm']=vec(g['origin_nm'],3,'origin_nm')
 if max(g['cell_nm'])/min(g['cell_nm'])>4:raise ValueError('cell aspect outside v1 engineering domain')
 if any(x*1e-9==0 for x in g['cell_nm']) or not 0<math.prod(x*1e-9 for x in g['cell_nm'])<float('inf'):raise ValueError('cell SI arithmetic range')
 if len(g['pbc'])!=3:raise ValueError('pbc dimension')
 g['pbc']=[integer(q,'pbc',0,1) for q in g['pbc']]
 if g['pbc'] not in [[1,1,0],[0,0,0]]:raise ValueError('unsupported mixed/z boundary')
 if len(g['mirrors'])!=2:raise ValueError('mirrors dimension')
 g['mirrors']=[integer(q,'mirrors',0,40) for q in g['mirrors']]
 from ..capacity import geometry_capacity
 geometry_capacity(*g['n'][:2], bool(g['pbc'][0]), g['mirrors'])
 if g['pbc'][0] and min(g['n'][:2])<3:raise ValueError('periodic dimension needs >=3')
 if not g['pbc'][0] and (g['mirrors']!=[0,0] or m['Anh_Jpm']!=0):raise ValueError('open XY requires mirrors=0 and Anh=0; never changed automatically')
 for key in ['Ms_Apm','A_Jpm','D_Jpm2','K1_Jpm3','K2_Jpm3','alpha','gamma_H_m_per_As']:m[key]=vec(m[key],2,key,**({'positive':True} if key in ['Ms_Apm','gamma_H_m_per_As'] else {'low':0} if key in ['A_Jpm','alpha'] else {}))
 if any(not math.isfinite(a*a) for a in m['alpha']):raise ValueError('alpha arithmetic range')
 for key in ['Ah_Jpm3','Anh_Jpm']:m[key]=number(m[key],key)
 if m['Anh_Jpm']!=0 and (min(m['A_Jpm'])<=0 or abs(m['Anh_Jpm'])>=2*math.sqrt(m['A_Jpm'][0])*math.sqrt(m['A_Jpm'][1])):raise ValueError('gradient quadratic form not positive definite')
 if len(m['axes'])!=2:raise ValueError('axes require A/B')
 axes=[]
 for a in m['axes']:
  a=vec(a,3,'axis');n=math.hypot(*a)
  if not n or not math.isfinite(n):raise ValueError('zero/overflow easy axis')
  axes.append([q/n for q in a])
 m['axes_input']=copy.deepcopy(m['axes']);m['axes']=axes
 if len(m['active'])!=4:raise ValueError('active dimension')
 m['active']=[integer(q,'active',0,1) for q in m['active']]
 field=raw.get('field',{})
 if set(field)-{'H_Apm','mu0_H_T'} or len(field)!=1:raise ValueError('field: exactly one H_Apm or mu0_H_T is required')
 if 'H_Apm' in field:H=vec(field['H_Apm'],3,'H_Apm')
 else:H=[q/(4*math.pi*1e-7) for q in vec(field['mu0_H_T'],3,'mu0_H_T')]
 d['field']={'H_Apm':H,'input':copy.deepcopy(field)}
 d['dynamic']['dt_fs']=number(d['dynamic']['dt_fs'],'dt_fs',positive=True);d['dynamic']['T_ps']=number(d['dynamic']['T_ps'],'T_ps',low=0)
 steps=d['dynamic']['T_ps']*1000/d['dynamic']['dt_fs']
 if not math.isfinite(steps) or abs(steps-round(steps))>8*math.ulp(max(1.,steps)) or steps>200000000:raise ValueError('T must be an integer number of dt steps')
 d['dynamic']['steps']=int(round(steps));d['static']['tol_Apm']=number(d['static']['tol_Apm'],'tol_Apm',positive=True);d['static']['max_updates']=integer(d['static']['max_updates'],'max_updates',0,30000)
 for key in ['wall_s','kernel_s']:res[key]=number(res[key],key,positive=True)
 if res['kernel_s']>res['wall_s']:raise ValueError('kernel_s exceeds job wall')
 res['max_fields']=integer(res['max_fields'],'max_fields',1,1000000);res['rss_bytes']=integer(res['rss_bytes'],'rss_bytes',1048576,2147483648);res['output_bytes']=integer(res['output_bytes'],'output_bytes',1048576,1073741824)
 if 5*d['dynamic']['steps']+2>res['max_fields']:raise ValueError('resource_forecast_insufficient: dynamic field budget')
 o['save_every']=integer(o['save_every'],'save_every',1,1000000);o['heartbeat_s']=number(o['heartbeat_s'],'heartbeat_s',positive=True)
 if o['goal'] not in ['none','observe','single_skyrmion']:raise ValueError('unknown structure goal')
 for key in ['directory','cache','bins']:
  if not isinstance(o[key],str) or not o[key]:raise ValueError('output path required')
  o[key]=str((Path(base)/o[key]).resolve())
 for key in ['checkpoint','metadata']:
  x=d['resume'][key]
  if not isinstance(x,str):raise ValueError('resume path string')
  if x:d['resume'][key]=str((Path(base)/x).resolve())
 if bool(d['resume']['checkpoint'])!=bool(d['resume']['metadata']):raise ValueError('resume needs checkpoint and metadata')
 if i['kind'] not in ['uniform','smooth','skyrmion','canonical_legacy','ovf2']:raise ValueError('unsupported initial mode')
 if i['relation'] not in ['antiparallel','independent']:raise ValueError('initial relation')
 for key in ['A','B']:i[key]=vec(i[key],3,key)
 for key in ['amplitude','helicity_rad']:i[key]=number(i[key],key)
 for key in ['radius_nm','wall_nm']:i[key]=number(i[key],key,positive=True)
 i['center_nm']=vec(i['center_nm'],2,'center_nm');i['polarity']=integer(i['polarity'],'polarity',-1,1)
 if i['polarity']==0:raise ValueError('polarity +/-1')
 if i['interpretation'] not in ['direction','magnetization_Apm']:raise ValueError('OVF interpretation')
 for key in ['ovf_A','ovf_B']:
  if not isinstance(i[key],str):raise ValueError('OVF path')
  if i[key]:i[key]=str((Path(base)/i[key]).resolve())
 if i['kind']=='canonical_legacy' and (g['n']!=[125,125,1] or g['cell_nm']!=[4,4,3] or g['origin_nm']!=[0,0,0]):raise ValueError('canonical_legacy requires canonical geometry')
 if i['kind']=='ovf2' and not (i['ovf_A'] and i['ovf_B']):raise ValueError('OVF2 requires explicit A and B files')
 if not isinstance(v['step_sensitivity'],bool):raise ValueError('step_sensitivity bool')
 for key in ['max_chord','rms_chord']:v[key]=number(v[key],key,positive=True)
 physics={'geometry':g,'material':m,'field':H};d['physics_sha256']=digest(physics);d['identity']=digest({'physics':physics,'dt_fs':d['dynamic']['dt_fs'],'schema':d['schema']});return d

def load(path):
 path=Path(path).resolve()
 with path.open('rb') as f:raw=tomllib.load(f)
 return resolve_dict(raw,path.parent)
