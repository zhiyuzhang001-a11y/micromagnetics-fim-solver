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
def check(out,kernel,config):
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
 return {'A_B_projected_Apm':r,'A_B_cross_Apm':cross,'history_A_B_Apm':reported,'history_max_difference_Apm':max(abs(a-b) for a,b in zip(r,reported)),
  'independent_field_relative_error':field_error,'field_consistent_1e_minus10':field_error<=1e-10,'history_consistent_1e_minus6_Apm':max(abs(a-b) for a,b in zip(r,reported))<=1e-6,
  'both_at_or_below_tentative_1_Apm_once':max(r)<=1.,'scientific_convergence_established':False,'persistence_checked':False,
  'internal_status':json.loads((out/'summary.json').read_text())['status'],
  'external_acceptance_passed':field_error<=1e-10 and max(abs(a-b) for a,b in zip(r,reported))<=1e-6 and max(r)<=1.,
  'external_acceptance_status':'ACCEPTED_ONCE' if field_error<=1e-10 and max(abs(a-b) for a,b in zip(r,reported))<=1e-6 and max(r)<=1. else 'NOT_ACCEPTED',
  'meaning':'Independent field recalculation at saved final state; one observation, not sustained convergence or energy/mesh/mirror acceptance.'}
if __name__=='__main__':
 a=argparse.ArgumentParser();a.add_argument('output',type=Path);a.add_argument('kernel',type=Path);a.add_argument('config',type=Path);x=a.parse_args();result=check(x.output,x.kernel,x.config);print(json.dumps(result,indent=2,allow_nan=False));raise SystemExit(0 if result['external_acceptance_passed'] else 1)
