"""Generate owned synthetic sample and READ existing real OVF. Native forbidden."""
from pathlib import Path
import sys,json
import numpy as np
from unittest.mock import patch
sys.path[:0]=[str(Path(__file__).resolve().parents[1]),str(Path(__file__).resolve().parent)]
from fimrun.postprocess import analyze_ovf,read_ovf
from fimrun.postprocess.geometry import measure
from fimrun.postprocess.io import sha,ROOT,canonical
from fimrun.micromagnetics.native import Native,EVALUATIONS
from test_skyrmion_postprocess import Offline,CAL
out=Path(sys.argv[1]).resolve();out.mkdir(parents=True,exist_ok=True)
with patch.object(Native,'__init__',side_effect=AssertionError('Native forbidden')):
 # Keep a simple reusable toy example; no original data copied/rewritten.
 fixture=Offline();fixture.root=out
 synthetic=fixture.frames()
 result=analyze_ovf(synthetic,out/'synthetic_analysis.csv',calibration=CAL,assume_temporal_sampling=True,ab_reference='antiparallel',velocity_window_s=[0.,7e-10])
 (out/'synthetic_inputs.json').write_bytes(canonical([{k:str(v) for k,v in entry.items()} for entry in synthetic]))
 reference=Path('/path/to/project/Documents/ChatGPT/Boris Skyrmion 轨道流')
 source=reference/'reference/user_benchmark_20261013'
 files={label:source/name for label,name in [('A','relax_sky_m.ovf'),('B','relax_sky_m2.ovf')]}
 before={str(p):sha(p) for p in files.values()}
 mapping={'stage':'sdesc','boundary':'periodic_xy','mirrors':[10,10],'Ms_A':3e5,'Ms_B':6e5,
          'legacy_A':{'quantity':'magnetization_Apm','origin_m':[0.,0.,0.],'normalization_roundoff':'binary32-gamma12'},
          'legacy_B':{'quantity':'magnetization_Apm','origin_m':[0.,0.,0.],'normalization_roundoff':'binary32-gamma12'},
          'evidence':[{'path':str(reference/'USER_OVF_SOURCE_CONFIRMATION_20261014.md')},{'path':str(source/'skyrmion_relax.user_original.txt')}],
          'normalization_assumption_note':'binary32 component roundtrip is verified; gamma12 is an explicit arithmetic envelope, not verified historical compiler/precision or physical Ms error'}
 real=analyze_ovf([{**files,'mapping':mapping}],out/'real_legacy_analysis.csv',calibration=CAL,ab_reference='antiparallel')[0]
 assert before=={str(p):sha(p) for p in files.values()}
 assert not real['valid_velocity'] and 'missing_time' in real['reason_codes']
 # Legacy extraction comparison is diagnostic, not a truth or a retuning target.
 from fimrun.micromagnetics.analysis import observe
 arrays=[read_ovf(p,Ms=mapping['Ms_'+label],legacy=mapping['legacy_'+label]) for label,p in files.items()]
 m=np.array([a['m'][None] for a in arrays]);g=arrays[0]
 case={'geometry':{'n':list(g['cells']),'cell_nm':(g['h']*1e9).tolist(),'origin_nm':(g['origin']*1e9).tolist(),'pbc':[1,1,0]},'output':{'goal':'observe'}}
 old=observe(m,case)['sublattices'];comparison=[]
 c=json.loads(CAL.read_text())
 for i,(label,a) in enumerate(zip(('A','B'),arrays)):
  raw=measure(a['m'],a['h'],a['origin'],'periodic_xy',calibration=c)
  comparison.append({'label':label,'legacy_center_nm':old[i]['center_nm'],'new_local_topo_center_nm':[raw.get('topo_x',np.nan)*1e9,raw.get('topo_y',np.nan)*1e9],'center_difference_nm':((np.array([raw.get('topo_x',np.nan),raw.get('topo_y',np.nan)])*1e9-np.array(old[i]['center_nm']))).tolist(),'legacy_radius_nm':old[i]['radius_nm'],'new_raw_radius_nm':raw.get('radius_m',np.nan)*1e9,'valid_geometry':raw['valid_geometry'],'valid_topology':raw['valid_topology'],'valid_helicity':raw['valid_helicity'],'reasons':raw['reasons'],'normalization':a['normalization']})
 assert dict(EVALUATIONS)=={'fm':0,'fim':0}
 receipt={'status':'passed_readonly_validation','synthetic_rows':len(result),'synthetic_valid_geometry':all(r['A_valid_geometry'] and r['B_valid_geometry'] for r in result),'real_reason_codes':real['reason_codes'],'real_comparison':comparison,'original_hashes_unchanged':before,'fields':dict(EVALUATIONS),'native_forbidden':True,'gates_retuned_for_real':False,'time_not_invented':True}
 (out/'EXAMPLE_VALIDATION.json').write_text(json.dumps(receipt,indent=2,allow_nan=True)+'\n');print(json.dumps(receipt))
