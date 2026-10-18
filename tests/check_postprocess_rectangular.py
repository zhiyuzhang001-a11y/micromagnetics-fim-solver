from pathlib import Path
import sys,json
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from fimrun.postprocess.calibration import texture
from fimrun.postprocess.geometry import measure,wrap,image
from fimrun.postprocess.io import ROOT
c=json.loads((ROOT/'fimrun/postprocess/calibration_v1.json').read_text());records=[]
for cells in ((80,112),(112,160),(160,112)):
 m,h,o,t=texture(cells=cells,center=(2.31e-9,254.27e-9),ratio=1.22,angle=.79,chi=2.9)
 shift=np.array([1.2e-6,-.7e-6]);origin=o.copy();origin[:2]+=shift
 a=measure(m,h,origin,'periodic_xy',calibration=c);b=measure(-m,h,origin,'periodic_xy',calibration=c)
 center=t['center']+shift;L=np.array(cells)*h[:2]
 errors=dict(center_rel=float(np.linalg.norm(image(np.array([a['area_x'],a['area_y']])-center,L))/t['radius']),moment_rel=float(np.linalg.norm(a['_cov']-t['cov'],2)/t['radius']**2),radius_rel=abs(a['radius_m']/t['radius']-1),phase=abs(float(wrap(a['chi_raw']-t['chi']))))
 assert all(value<=c['accuracy_envelopes'][key] for key,value in errors.items()),errors
 assert np.linalg.norm(np.array([a['seed_x']-b['seed_x'],a['seed_y']-b['seed_y']]))<np.finfo(float).eps*np.linalg.norm(L)*128
 gap=(t['major']**2-t['minor']**2)/4;delta=c['moment_error_rel']*t['radius']**2
 angle_bound=float(np.arcsin(min(1.,delta/max(gap-delta,np.finfo(float).tiny))))
 angle_error=abs(float(wrap(2*(a['axis_raw_rad']-t['axis']))/2));assert angle_error<=angle_bound
 records.append(dict(cells=cells,errors=errors,axis_error_rad=angle_error,axis_calibration_envelope_rad=angle_bound,signed_seed_same=True,origin_shift_m=shift.tolist()))
answer={'status':'passed','thresholds_retuned':False,'records':records,'fields':0}
p=Path(sys.argv[1]);p.write_text(json.dumps(answer,indent=2)+'\n');print(json.dumps(answer))
