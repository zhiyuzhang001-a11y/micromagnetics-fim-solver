"""Report final A/B residuals; never continue the solver or claim scientific convergence."""
from pathlib import Path
import argparse,csv,hashlib,json,numpy as np
import independent_field as ref
KERNEL_SHA='db71f379e2bea728a475d9e0c6e5e1183c7830ee1ba91e6909f84c532ec012b6'
def validate_config(config):
 lines=Path(config).read_text().splitlines()
 expected=[[125,125,1],[4e-9,4e-9,3e-9],[1,1,0],[3e5,6e5],[5e-12,5e-12],[-8e6,-8e6],[-5e-12,-5e-12],[.00105,.00105],[109000,109000],[0,0],[0,0,1],[1,1,1,1]]
 if lines[0].split()[0]!='P-Anh-v1':raise ValueError('fixed configuration schema required')
 for line,values in zip(lines[1:13],expected):
  if [float(x) for x in line.split()]!=values:raise ValueError('reader supports only canonical fixed-material geometry')
 if len(lines[1:13])!=len(expected):raise ValueError('truncated configuration')
def check_legacy(out,kernel,config):
 validate_config(config)
 out=Path(out);kernel=Path(kernel)
 if hashlib.sha256(kernel.read_bytes()).hexdigest()!=KERNEL_SHA:raise ValueError('fixed qualified kernel identity required')
 m=np.fromfile(out/'final.bin',dtype='=f8').reshape(2,1,125,125,3)
 if not np.isfinite(m).all() or np.max(abs(np.linalg.norm(m,axis=-1)-1))>1e-12:raise ValueError('nonfinite/nonunit final state')
 saved=np.array([np.fromfile(out/f'final_H_{s}.bin',dtype='=f8').reshape(1,125,125,3) for s in ['A','B']])
 ref.configure(kernel);H=ref.fields(m)
 if not np.isfinite(H).all() or not np.isfinite(saved).all():raise ValueError('nonfinite field')
 ph=H-m*np.sum(m*H,axis=-1,keepdims=True);r=[float(np.max(np.linalg.norm(ph[i],axis=-1))) for i in range(2)]
 cross=[float(np.max(np.linalg.norm(np.cross(m[i],H[i]),axis=-1))) for i in range(2)]
 with (out/'history.csv').open() as f:rows=list(csv.DictReader(f))
 if not rows:raise ValueError('empty history')
 last=rows[-1];static='post_A_Apm' in last;keys=['post_A_Apm','post_B_Apm'] if static else ['residual_A_Apm','residual_B_Apm'];reported=[float(last[k]) for k in keys]
 if not np.isfinite(reported).all():raise ValueError('nonfinite history residual')
 field_error=float(np.max(np.linalg.norm(H-saved,axis=-1))/max(1.,float(np.max(np.linalg.norm(H,axis=-1)))))
 return {'policy_id':'LEGACY_READER_COMPAT_TENTATIVE','authority':'legacy_observational_reader_only','A_B_projected_Apm':r,'A_B_cross_Apm':cross,'history_A_B_Apm':reported,'history_max_difference_Apm':max(abs(a-b) for a,b in zip(r,reported)),
  'independent_field_relative_error':field_error,'field_consistent_1e_minus10':field_error<=1e-10,'history_consistent_1e_minus6_Apm':max(abs(a-b) for a,b in zip(r,reported))<=1e-6,
  'both_at_or_below_tentative_1_Apm_once':max(r)<=1.,'scientific_convergence_established':False,'persistence_checked':False,
  'internal_status':json.loads((out/'summary.json').read_text())['status'],
  'external_acceptance_passed':field_error<=1e-10 and max(abs(a-b) for a,b in zip(r,reported))<=1e-6 and max(r)<=1.,
  'external_acceptance_status':'ACCEPTED_ONCE' if field_error<=1e-10 and max(abs(a-b) for a,b in zip(r,reported))<=1e-6 and max(r)<=1. else 'NOT_ACCEPTED',
  'meaning':'Independent field recalculation at saved final state; one observation, not sustained convergence or energy/mesh/mirror acceptance.'}

# Compatibility reader only; current normal runs use check_current with explicit policy.
check=check_legacy

def check_current(out, kernel, config, *, requested_tolerance, external_H_Apm, binding):
 from static_policy import POLICY_ID, KERNEL_SHA, sha, tolerance, vector, read_supported_config, write_json
 out=Path(out);eps=tolerance(requested_tolerance);external=vector(external_H_Apm)
 counter=out/'independent_check_counter.json'
 write_json(counter,{'started':0,'completed':0})
 try:
  actual=read_supported_config(config)
  if sha(config)!=binding['configuration_sha256'] or sha(kernel)!=binding['kernel_sha256'] or sha(kernel)!=KERNEL_SHA:
   raise ValueError('actual configuration/kernel identity mismatch')
  if sha(out/'final.bin')!=binding['final_m_sha256'] or sha(out/'checkpoint.bin')!=binding['checkpoint_sha256']:
   raise ValueError('saved magnetization/checkpoint identity mismatch')
  cp=(out/'checkpoint.bin').read_bytes();raw=(out/'final.bin').read_bytes()
  if len(cp)!=2250044 or cp[:16]!=b'SD-v380-v1'+b'\0'*6 or cp[44:750044]!=raw:
   raise ValueError('saved magnetization differs from checkpoint')
  m=np.frombuffer(raw,dtype='<f8').copy().reshape(2,1,125,125,3)
  saved=np.stack([np.fromfile(out/f'final_H_{s}.bin',dtype='<f8').reshape(1,125,125,3)for s in ['A','B']])
  if not np.isfinite(m).all() or not np.isfinite(saved).all() or np.max(abs(np.linalg.norm(m,axis=-1)-1))>1e-12:
   raise ValueError('saved nonfinite/nonunit state or field')
  ref.configure(kernel,config=config,external_H_Apm=external)
  write_json(counter,{'started':1,'completed':0})
  H=ref.fields(m)
  if not np.isfinite(H).all():raise ValueError('independent field nonfinite')
  ph=H-m*np.sum(m*H,axis=-1,keepdims=True)
  r=[float(np.max(np.linalg.norm(ph[i],axis=-1)))for i in range(2)]
  error=float(np.max(np.linalg.norm(H-saved,axis=-1))/max(1.,float(np.max(np.linalg.norm(H,axis=-1)))))
  native=binding['native_A_B_Apm'];difference=max(abs(a-b)for a,b in zip(r,native))
  identities=sha(out/'final.bin')==binding['final_m_sha256'] and sha(out/'checkpoint.bin')==binding['checkpoint_sha256'] and sha(config)==binding['configuration_sha256'] and sha(kernel)==binding['kernel_sha256']
  passed=identities and error<=1e-10 and difference<=1e-6 and max(r)<=eps
  write_json(counter,{'started':1,'completed':1})
  return {'status':'passed'if passed else'failed','policy_id':POLICY_ID,'requested_tolerance':{'value':eps,'unit':'A/m'},
          'achieved_A_Apm':r[0],'achieved_B_Apm':r[1],'field_relative_error':error,'native_residual_difference_Apm':difference,
          'final_m_sha256':binding['final_m_sha256'],'configuration_sha256':binding['configuration_sha256'],
          'kernel_sha256':binding['kernel_sha256'],'checkpoint_sha256':binding['checkpoint_sha256'],
          'Ms_Apm':actual['Ms_Apm'],'external_H_Apm':external,'identities_match':identities,'real_fields':1}
 except Exception as error:
  calls=json.loads(counter.read_text())
  return {'status':'failed','reason':str(error),'achieved_A_Apm':None,'achieved_B_Apm':None,
          'real_fields':calls['started'],'identities_match':False}

if __name__=='__main__':
 a=argparse.ArgumentParser();a.add_argument('output',type=Path);a.add_argument('kernel',type=Path);a.add_argument('config',type=Path);x=a.parse_args();result=check_legacy(x.output,x.kernel,x.config);print(json.dumps(result,indent=2,allow_nan=False));raise SystemExit(0 if result['external_acceptance_passed'] else 1)
