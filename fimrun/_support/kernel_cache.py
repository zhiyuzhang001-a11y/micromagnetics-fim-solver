"""Geometry-bound atomic kernel cache, checked before any user Model construction."""
from pathlib import Path
import json,os,time,subprocess,hashlib
import numpy as np
from .user_case import digest,sha
from .kernel_reference import grid_tensor
from ..runtime import RESOURCE_ROOT as ROOT
VERSION='single-layer-mpfr128-asym40-v1'

def layout(case):
 g=case['geometry'];nx,ny,_=g['n'];return (nx,ny) if g['pbc'][0] else (2*nx,2*ny)
def key_data(case):
 return {'schema':VERSION,'geometry':case['geometry'],'layout':list(layout(case)),'components':'xx yy zz xy xz yz','sign':'positive N, H=-N*M','storage':'little-endian f64, x fastest','projection':'XY even diag/odd xy for finite periodic images','generator_source':digest({str(p.relative_to(ROOT)):sha(p) for p in [ROOT/'src/kernel_builder.cpp',*sorted((ROOT/'src/user_kernel').glob('*'))]})}
def validate_kernel(case,path,samples=None,deadline=float('inf')):
 g=case['geometry'];nx,ny,_=g['n'];px,py=layout(case);a=np.fromfile(path,dtype='<f8').reshape(py,px,6)
 if not np.isfinite(a).all():raise ValueError('kernel nonfinite')
 iy=(-np.arange(py))%py;ix=(-np.arange(px))%px;inversion=a[iy][:,ix];sym=float(np.max(np.abs(a-inversion)))
 if sym>1e-12:raise ValueError('kernel reciprocity')
 checked=[];refcalls=0;maxerr=0.
 if samples:
  h=[str(x*1e-9) for x in g['cell_nm']]
  for row in samples:
   if time.monotonic()>deadline:raise TimeoutError('kernel validation resource_budget_exhausted')
   lo=np.array([float(x) for x in grid_tensor(h,row['i'],row['j'],70)]);hi=np.array([float(x) for x in grid_tensor(h,row['i'],row['j'],90)]);refcalls+=2;err=float(np.max(np.abs(np.array(row['tensor'])-hi)));drift=float(np.max(np.abs(lo-hi)));maxerr=max(maxerr,err)
   if drift>1e-12 or err>1e-10:raise ValueError('kernel engineering tensor reference failed')
   checked.append({'i':row['i'],'j':row['j'],'error':err,'reference_precision_drift':drift})
  # Independently reconstruct effective q=0 from physical finite-image tensors.
  # q=0 is unchanged by parity projection. This checks sum/sign/layout, not just cached samples.
  if g['pbc'][0]:
   ref=np.zeros(6);mx,my=g['mirrors']
   for i in range(-mx,mx+1):
    for j in range(-my,my+1):
     if time.monotonic()>deadline:raise TimeoutError('kernel reference resource_budget_exhausted')
     ref+=np.array([float(x) for x in grid_tensor(h,i*nx,j*ny,90)]);refcalls+=1
  else:ref=np.array([float(x) for x in grid_tensor(h,0,0,90)]);refcalls+=1
  error=float(np.max(np.abs(a[0,0]-ref)));maxerr=max(maxerr,error)
  if error>1e-10:raise ValueError('effective zero-displacement kernel reference')
 return {'engineering_reference_error':maxerr if samples else None,'reciprocity_max':sym,'reference_samples':checked,'reference_tensor_evaluations':refcalls,'coverage':'tensor samples and effective zero block; full-kernel finite/reciprocity','physical_grid_convergence':'not_checked','physical_mirror_convergence':'not_checked'}
def get(case,deadline,notify=lambda x:None):
 cache=Path(case['output']['cache']);cache.mkdir(parents=True,exist_ok=True);key=key_data(case);token=digest(key);folder=cache/token;manifest=folder/'manifest.json';payload=folder/'kernel.f64';start=time.monotonic()
 if folder.exists():
  if not manifest.exists():raise ValueError('incomplete kernel cache; use a new cache directory or inspect lock')
  meta=json.loads(manifest.read_text())
  if meta['key']!=key or sha(payload)!=meta['payload_sha256']:raise ValueError('kernel cache identity/checksum mismatch')
  return payload,{**meta,'cache_hit':True,'lookup_wall_s':time.monotonic()-start}
 lock=cache/(token+'.lock');fd=os.open(lock,os.O_CREAT|os.O_EXCL|os.O_WRONLY);os.close(fd);folder.mkdir()
 try:
  g=case['geometry'];canonical=g['n']==[125,125,1] and g['cell_nm']==[4,4,3] and g['pbc']==[1,1,0] and g['mirrors']==[10,10]
  if canonical:
   original=ROOT/'examples/kernel125-mirror10.f64'
   if sha(original)!='db71f379e2bea728a475d9e0c6e5e1183c7830ee1ba91e6909f84c532ec012b6':raise ValueError('bundled canonical kernel identity')
   payload.write_bytes(original.read_bytes());verification=validate_kernel(case,payload);verification['historical_reference']='qualified canonical finite mirror10 kernel; original bytes retained';source='bundled-qualified-canonical'
  else:
   generator=Path(case['output']['bins'])/'kernel_builder'
   if not generator.exists():raise ValueError('new geometry needs MPFR/GMP kernel_builder; build with --user-workflow')
   cap=min(case['resources']['kernel_s'],deadline-time.monotonic());assert cap>0,'resource_forecast_insufficient'
   args=[str(generator),*map(str,g['n'][:2]),*map(str,[x*1e-9 for x in g['cell_nm']]),str(g['pbc'][0]),*map(str,g['mirrors']),str(payload),str(cap),str(case['resources']['rss_bytes'])]
   with (folder/'generation.stdout').open('wb') as stdout,(folder/'generation.stderr').open('wb') as stderr:
    proc=subprocess.Popen(args,stdout=stdout,stderr=stderr)
    try:
     while proc.poll() is None:
      if time.monotonic()>=deadline or time.monotonic()-start>cap:raise TimeoutError('kernel resource_budget_exhausted')
      notify({'phase':'kernel','elapsed_s':time.monotonic()-start,'note':'首次高精度生成可能较慢；不是物理收敛检查'});time.sleep(.1)
     if proc.returncode:raise ValueError((folder/'generation.stderr').read_text())
    except BaseException:
     proc.kill();proc.wait();raise
   verification=validate_kernel(case,payload,json.loads(Path(str(payload)+'.samples.json').read_text()),min(deadline,start+case['resources']['kernel_s']));source='MPFR128-Newell/BORIS-asymptotic'
  meta={'key':key,'payload_sha256':sha(payload),'verification':verification,'source':source,'generation_and_validation_s':time.monotonic()-start,'cache_hit':False};tmp=folder/'manifest.json.tmp';tmp.write_text(json.dumps(meta,indent=2)+'\n');tmp.replace(manifest);return payload,meta
 finally:lock.unlink(missing_ok=True)
