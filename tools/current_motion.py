"""Accepted-state motion; zero current has no longitudinal direction or Hall angle."""
import csv
from pathlib import Path
import numpy as np

def rows(path):return list(csv.DictReader(Path(path).open()))
def motion(path,case):
 records=rows(path);J=np.array(case['drive']['Jc_Apm2'][:2]);current=np.linalg.norm(J);result={'fit_window_ps':[float(records[0]['time_ps']),float(records[-1]['time_ps'])],'current_direction':None if current==0 else (J/current).tolist(),'current_axes_status':'not_applicable' if current==0 else 'defined','sublattices':[],'research_qualification':'not_checked','grid_mirror_convergence':'not_checked'};curves=[]
 for i in [0,1]:
  rr=[r for r in records if int(r['sub'])==i];xy=np.array([[float(r['x_nm']),float(r['y_nm'])] for r in rr]);time=np.array([float(r['time_ps']) for r in rr])*1e-12;valid=bool(np.isfinite(xy).all() and all(int(r['continuous']) and not int(r['singular']) for r in rr));v=None;fit=None;delta=None;budget=None
  if valid:
   delta=xy[-1]-xy[0]
   if current>0 and len(rr)>1 and time[-1]>time[0]:
    coef=np.polyfit(time-time[0],(xy-xy[0])*1e-9,1);v=coef[0];fit=float(np.max(np.linalg.norm(((time-time[0])[:,None]*coef[0]+coef[1])-(xy-xy[0])*1e-9,axis=1)))
   radius=float(rr[0]['radius_nm']);budget=.01*radius if np.isfinite(radius) else None
  resolved=bool(current>0 and valid and budget is not None and delta is not None and np.linalg.norm(delta)>10*budget and v is not None);vp=None;vt=None;hall=None
  if resolved:
   e=J/current;vp=float(v@e);vt=float(v@np.array([-e[1],e[0]]));hall=float(np.degrees(np.arctan2(vt,vp)))
  result['sublattices'].append({'center_valid':valid,'drift_nm':None if delta is None else delta.tolist(),'fit_velocity_vector_mps':None if v is None else v.tolist(),'velocity_vector_mps':v.tolist() if resolved else None,'fit_max_residual_m':fit,'center_error_budget_nm':budget,'directional_status':'not_applicable' if current==0 else 'resolved' if resolved else 'unresolved','v_parallel_mps':vp,'v_perp_mps':vt,'Hall_deg':hall,'last_valid_single':bool(int(rr[-1]['valid_single']))});curves.append(xy if valid else None)
 if all(x is not None for x in curves) and len(curves[0])==len(curves[1]):result['relative_displacement_nm']=((curves[0][-1]-curves[1][-1])-(curves[0][0]-curves[1][0])).tolist();result['common_displacement_nm']=(.5*((curves[0][-1]+curves[1][-1])-(curves[0][0]+curves[1][0]))).tolist()
 else:result['relative_displacement_nm']=None;result['common_displacement_nm']=None
 vectors=[x['fit_velocity_vector_mps'] for x in result['sublattices']];common=None if any(v is None for v in vectors) else .5*(np.array(vectors[0])+vectors[1]);result['common_fit_velocity_vector_mps']=None if common is None else common.tolist();valid_common=bool(current>0 and common is not None and all(x['directional_status']=='resolved' for x in result['sublattices']));result['common_directional_status']='not_applicable' if current==0 else 'resolved' if valid_common else 'unresolved';result['common_velocity_vector_mps']=common.tolist() if valid_common else None;result['common_v_parallel_mps']=None;result['common_v_perp_mps']=None;result['common_Hall_deg']=None
 if valid_common:
  e=J/current;vp=float(common@e);vt=float(common@np.array([-e[1],e[0]]));result.update(common_v_parallel_mps=vp,common_v_perp_mps=vt,common_Hall_deg=float(np.degrees(np.arctan2(vt,vp))))
 return result
