"""Train/freeze BEFORE independent analytic holdout; never evaluates a field."""
from pathlib import Path
import json,sys,time
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from fimrun.postprocess.calibration import calibrate,texture
from fimrun.postprocess.geometry import measure,wrap,image
from fimrun.postprocess.io import canonical,content_sha
out=Path(sys.argv[1]).resolve();out.mkdir(parents=True,exist_ok=True);started=time.monotonic()
c=calibrate();(out/'CALIBRATION_FROZEN.json').write_bytes(canonical(c))
# Holdout phases, grids, radii, angles and positions not used for calibration.
records=[];passed=True
for n in (80,112,160,192):
 for k,(ratio,mod) in enumerate(((1.,0.),(1.22,0.),(1.,.12))):
  for flip in (False,True):
   m,h,o,t=texture(cells=n,center=(1.73e-9,254.17e-9),radius=21e-9,ratio=ratio,angle=.81,chi=-2.71,modulation=mod,flip=flip)
   v=measure(m,h,o,'periodic_xy',calibration=c);L=np.array([n,n])*h[:2]
   e=dict(center_rel=max(float(np.linalg.norm(image(np.array([v[p+'x'],v[p+'y']])-t['center'],L))/t['radius']) for p in ('area_','topo_')),radius_rel=abs(v['radius_m']/t['radius']-1),moment_rel=float(np.linalg.norm(v['_cov']-t['cov'],2)/t['radius']**2),phase=float(abs(wrap(v['chi_raw']-t['chi']))))
   checks={key:value<=c['accuracy_envelopes'][key] for key,value in e.items()}
   checks.update(geometry=v['valid_geometry'],topology=v['valid_topology'],helicity=v['valid_helicity'],axis_policy=(v['valid_axis'] if ratio>1 else not v['valid_axis']))
   records.append(dict(n=n,ratio=ratio,modulation=mod,flip=flip,errors=e,checks=checks,reasons=v['reasons'],coherence=v['coherence']))
   passed=passed and all(checks.values())
refinement=[]
for n in (64,128,256):
 m,h,o,t=texture(cells=n,center=(123.3e-9,138.7e-9),radius=24e-9,chi=.87)
 v=measure(m,h,o,'periodic_xy',calibration=c)
 refinement.append(dict(cells=n,radius_error_m=abs(v['radius_m']-t['radius']),phase_error_rad=float(abs(wrap(v['chi_raw']-t['chi']))),arc_refinement_error_rad=v['phase_sampling_error']))
# Rejected-domain controls are assertions, not training observations.
m,h,o,t=texture(cells=96,modulation=1.2);v=measure(m,h,o,'periodic_xy',calibration=c)
assert not v['valid_helicity'],'strong local distortion must not become an aggregate helicity'
answer={'status':'passed' if passed else 'HOLDOUT_FAILED_NO_RETUNING','training_count':len(c['training']),'calibration_sha256':content_sha(c),'holdout_count':len(records),'records':records,'refinement':refinement,'strong_distortion_rejected':True,'fields':0,'wall_s':time.monotonic()-started}
(out/'CALIBRATION_VALIDATION.json').write_text(json.dumps(answer,indent=2)+'\n')
print(json.dumps({k:v for k,v in answer.items() if k!='records'}))
if not passed:
 print(json.dumps([r for r in records if not all(r['checks'].values())]));sys.exit(1)
