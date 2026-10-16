"""Public generated directions and explicit two-file OVF2 import."""
import numpy as np
from pathlib import Path
from ovf import read

def generate(case):
 g=case['geometry'];i=case['initial'];nx,ny,nz=g['n'];h=np.array(g['cell_nm']);origin=np.array(g['origin_nm']);metadata={}
 if i['kind']=='canonical_legacy':
  from make_representative_fixture import directions
  return directions(),{'kind':'canonical_legacy','source':'public analytical direction recipe'}
 if i['kind']=='ovf2':
  values=[]
  for sub in ['A','B']:
   a,report=read(i['ovf_'+sub],g,case['material']['Ms_Apm'][len(values)],i['interpretation']);values.append(a);metadata[sub]=report
  return np.array(values),metadata
 yy,xx=np.meshgrid(origin[1]+(np.arange(ny)+.5)*h[1],origin[0]+(np.arange(nx)+.5)*h[0],indexing='ij')
 if i['kind']=='uniform':a=np.broadcast_to(np.array(i['A'],float),(nz,ny,nx,3)).copy()
 elif i['kind']=='smooth':
  t=i['amplitude']*np.cos(2*np.pi*((xx-origin[0])/(nx*h[0])+(yy-origin[1])/(ny*h[1])))
  if abs(i['amplitude'])>=1:raise ValueError('smooth amplitude must be <1')
  a=np.stack([t,np.zeros_like(t),np.sqrt(1-t*t)],-1)[None]
 else:
  dx=xx-i['center_nm'][0];dy=yy-i['center_nm'][1];rr=np.hypot(dx,dy);theta=.5*np.pi*(1-np.tanh((rr-i['radius_nm'])/i['wall_nm']));phi=np.arctan2(dy,dx)+i['helicity_rad'];a=np.stack([np.sin(theta)*np.cos(phi),np.sin(theta)*np.sin(phi),-i['polarity']*np.cos(theta)],-1)[None]
 b=-a if i['relation']=='antiparallel' else np.broadcast_to(np.array(i['B'],float),a.shape).copy();m=np.array([a,b]);n=np.linalg.norm(m,axis=-1)
 if not np.isfinite(m).all() or np.any(n==0):raise ValueError('initial finite nonzero vectors required')
 metadata={'kind':i['kind'],'normalization':'explicit generated unit directions','input_norm_min':float(n.min()),'input_norm_max':float(n.max())};return m/n[...,None],metadata
