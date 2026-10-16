"""Zero-Model contract regression for final report gates and motion qualifiers."""
from pathlib import Path
import copy, csv, sys, tempfile
from unittest.mock import patch
import numpy as np
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'))
from run_current_workflow import successful,preflight
from current_case import load,drive_rhs
from current_motion import motion

def check():
 good={'execution_completed':True,'mandatory_outputs_written':True,'trajectory_reached':True,'independent':{'passed':True},'requested_step_sensitivity':False,'structure_goal':{'requested':'observe','status':'observed'}}
 assert successful(good)
 for requested,status in [('none','not_requested'),('observe','observed'),('single_skyrmion','met')]:
  r=copy.deepcopy(good);r['structure_goal']={'requested':requested,'status':status};assert successful(r)
  r['structure_goal']['status']='not_checked';assert not successful(r)
 for key in ['execution_completed','mandatory_outputs_written','trajectory_reached']:
  r=copy.deepcopy(good);r[key]=False;assert not successful(r)
 r=copy.deepcopy(good);r.update(requested_step_sensitivity=True);assert not successful(r)
 r['step_sensitivity']={'status':'passed'};assert successful(r)
 r['failure_detail']='ENOSPC';assert not successful(r)
 case=load(ROOT/'configs/user_case_sot.toml')
 with patch('run_current_workflow.sys.byteorder','big'):
  try:preflight(case)
  except ValueError as e:assert 'ABI' in str(e)
  else:raise AssertionError('ABI')
 m=np.ones((2,1,1,1,3));zero=copy.deepcopy(case);zero['drive']['xi']=[0,0];assert np.array_equal(drive_rhs(m,zero),np.zeros_like(m))
 with tempfile.TemporaryDirectory() as directory:
  path=Path(directory)/'observations.csv';keys=['time_ps','sub','x_nm','y_nm','continuous','singular','radius_nm','valid_single']
  def fixture(displacement,continuous=1):
   with path.open('w') as f:
    w=csv.DictWriter(f,keys);w.writeheader()
    for time in [0,1,2]:
     for sub in [0,1]:w.writerow(dict(zip(keys,[time,sub,time*displacement/2,0,continuous,0,10,1])))
  fixture(.1);r=motion(path,case);assert r['common_directional_status']=='unresolved' and r['common_velocity_vector_mps'] is None and r['common_fit_velocity_vector_mps'] is not None
  zero['drive']['Jc_Apm2']=[0,0,0];r=motion(path,zero);assert r['current_direction'] is None and r['common_directional_status']=='not_applicable' and r['common_fit_velocity_vector_mps'] is None and r['common_Hall_deg'] is None
  fixture(2);r=motion(path,case);assert r['common_directional_status']=='resolved' and abs(r['common_velocity_vector_mps'][0]-1000)<1e-10 and abs(r['common_Hall_deg'])<1e-10
  fixture(2,0);r=motion(path,case);assert r['common_displacement_nm'] is None and r['common_velocity_vector_mps'] is None
 print('passed: final success gates, ABI, zero xi, zero/unresolved/resolved/invalid motion; zero Model and fields')
if __name__=='__main__':check()
