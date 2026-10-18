# Existing structure observer generalized only to the actual number of fields; no implicit analysis deadline.
"""Goal-conditional rectangular thin-film observations, never a universal success gate."""
import time
import numpy as np
from .._support.contour_geometry import contours

def observe(m,case,deadline=None):
 if deadline is not None and time.monotonic()>=deadline:raise TimeoutError("structure resource_budget_exhausted")
 g=case['geometry'];nx,ny,_=g['n'];hx,hy=g['cell_nm'][:2];ox,oy=g['origin_nm'][:2];periodic=bool(g['pbc'][0]);rows=[]
 for sub in range(m.shape[0]):
  a=m[sub,0];charge=np.zeros((ny,nx));bad=0
  if periodic:quad=(a,np.roll(a,-1,1),np.roll(np.roll(a,-1,0),-1,1),np.roll(a,-1,0))
  else:quad=(a[:-1,:-1],a[:-1,1:],a[1:,1:],a[1:,:-1])
  a0,b,c,d=quad;Q=0.
  for u,v,w,shifts in [(a0,b,c,[(0,0),(0,1),(1,1)]),(a0,c,d,[(0,0),(1,1),(1,0)])]:
   uv=np.sum(u*v,-1);vw=np.sum(v*w,-1);wu=np.sum(w*u,-1);det=np.sum(u*np.cross(v,w),-1);den=1+uv+vw+wu;invalid=(uv<=-1+1e-12)|(vw<=-1+1e-12)|(wu<=-1+1e-12)|(np.hypot(det,den)<=1e-12);bad+=int(invalid.sum());angle=2*np.arctan2(det,den);angle[invalid]=0;Q+=float(angle.sum()/(4*np.pi))
   if periodic:
    for sh in shifts:charge+=np.roll(angle,sh,(0,1))/(12*np.pi)
   else:charge[:-1,:-1]+=angle/(4*np.pi)
  center=None
  if not bad and abs(Q)>=.1:
   if periodic:
    center=[]
    for marginal,n,h,o in [(charge.sum(0)/Q,nx,hx,ox),(charge.sum(1)/Q,ny,hy,oy)]:
     z=np.sum(marginal*np.exp(2j*np.pi*(np.arange(n)+.5)/n))
     if abs(z)<=1e-12:center=None;break
     center.append(float(np.angle(z)%(2*np.pi)*n*h/(2*np.pi)+o))
   else:center=[float(np.sum(charge*(ox+(np.arange(nx)+.5)*hx)[None,:])/Q),float(np.sum(charge*(oy+(np.arange(ny)+.5)*hy)[:,None])/Q)]
  background=1 if np.median(a[...,2])>=0 else -1;mask=background*a[...,2]<0;seen=np.zeros((ny,nx),bool);sizes=[]
  for y,x in np.argwhere(mask):
   if seen[y,x]:continue
   todo=[(int(y),int(x))];seen[y,x]=True;size=0
   while todo:
    yy,xx=todo.pop();size+=1
    for yy2,xx2 in [(yy-1,xx),(yy+1,xx),(yy,xx-1),(yy,xx+1)]:
     if periodic:yy2%=ny;xx2%=nx
     if 0<=yy2<ny and 0<=xx2<nx and mask[yy2,xx2] and not seen[yy2,xx2]:seen[yy2,xx2]=True;todo.append((yy2,xx2))
   sizes.append(size)
  z=a[...,2]
  if periodic and center is not None:z=np.roll(z,[ny//2-int(np.floor((center[1]-oy)/hy)),nx//2-int(np.floor((center[0]-ox)/hx))],(0,1))
  paths,amb=contours(z,(hx*1e-9,hy*1e-9),(float('inf') if deadline is None else deadline));closed=[p for p in paths if p['closed'] and p['valid']];radius=closed[0]['radius_nm'] if len(closed)==1 else None
  single=bool(not bad and sum(s>=4 for s in sizes)==1 and len(paths)==1 and len(closed)==1 and not amb and center is not None and (not periodic or abs(abs(Q)-1)<=1e-6))
  rows.append({'Q_triangle':None if bad else Q,'Q_interpretation':'periodic topological charge' if periodic else 'open-boundary finite patch charge, not forced integer','triangle_singular_count':bad,'center_nm':center,'core_sizes_cells':sizes,'closed_contours':len(closed),'radius_nm':radius,'valid_single':single,'resolution_note':'radius comparable to a few cells requires refinement check' if radius is not None and radius<3*max(hx,hy) else None})
 goal=case['output']['goal'];return {'requested':goal,'status':'not_requested' if goal=='none' else 'observed' if goal=='observe' else 'met' if all(x['valid_single'] for x in rows) else 'not_met','sublattices':rows,'physical_stability_certified':False}
