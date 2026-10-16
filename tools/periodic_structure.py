import numpy as np
import time
from contour_geometry import contours
N=125;h=4e-9;L=N*h
def topo(m):
 charge=np.zeros((N,N));bad=0
 right=np.roll(m,-1,1);down=np.roll(m,-1,0);diag=np.roll(down,-1,1)
 for a,b,c,shifts in [(m,right,diag,[(0,0),(0,1),(1,1)]),(m,diag,down,[(0,0),(1,1),(1,0)])]:
  ab=np.sum(a*b,-1);bc=np.sum(b*c,-1);ca=np.sum(c*a,-1);det=np.sum(a*np.cross(b,c),-1);den=1+ab+bc+ca
  invalid=(ab<=-1+1e-12)|(bc<=-1+1e-12)|(ca<=-1+1e-12)|(np.hypot(det,den)<=1e-12);bad+=int(invalid.sum());w=2*np.arctan2(det,den);w[invalid]=0
  for sh in shifts:charge+=np.roll(w,sh,(0,1))/(12*np.pi)
 Q=float(charge.sum());dx=(right-np.roll(m,1,1))/(2*h);dy=(down-np.roll(m,1,0))/(2*h);Qfd=float(np.sum(m*np.cross(dx,dy))*h*h/(4*np.pi))
 center=None;strength=[]
 if not bad and abs(Q)>=.1:
  axis=(np.arange(N)+.5)/N*2*np.pi
  for dim in [0,1]:
   marginal=charge.sum(axis=dim)/Q;z=np.sum(marginal*np.exp(1j*axis));strength.append(float(abs(z)))
  if min(strength)>1e-12:
   center=[float((np.angle(np.sum(charge.sum(axis=dim)/Q*np.exp(1j*axis)))%(2*np.pi))*L/(2*np.pi)/1e-9) for dim in [0,1]]
 return dict(Q_triangle=None if bad else Q,Q_fd=Qfd,triangle_singular_count=bad,circular_center_nm=center,circular_strength=strength)

def cores(mask):
 seen=np.zeros(mask.shape,bool);sizes=[]
 for y,x in np.argwhere(mask):
  if seen[y,x]:continue
  todo=[(y,x)];seen[y,x]=1;size=0
  while todo:
   a,b=todo.pop();size+=1
   for c,e in [((a-1)%N,b),((a+1)%N,b),(a,(b-1)%N),(a,(b+1)%N)]:
    if mask[c,e] and not seen[c,e]:seen[c,e]=1;todo.append((c,e))
  sizes.append(size)
 return sizes

def observe(v,i):
 t=topo(v);sizes=cores((1 if i==0 else -1)*v[...,2]<0);reasons=[];center=t['circular_center_nm'];resolved=sum(s>=4 for s in sizes)
 if center is None:reasons.append('topology_or_circular_center_invalid')
 if resolved!=1:reasons.append('not_single_resolved_periodic_core')
 radius=None;shape=None;count=None
 if center is not None:
  shift=[N//2-int(np.floor(center[1]/4)),N//2-int(np.floor(center[0]/4))];z=np.roll(v[...,2],shift,(0,1));paths,amb=contours(z,h,time.monotonic()+15);closed=[p for p in paths if p['closed']];count=len(closed)
  if amb or len(paths)!=1 or len(closed)!=1:reasons.append('multiple_open_or_ambiguous_contours')
  elif not closed[0]['valid'] or closed[0]['area_nm2']<4*16 or closed[0]['edge_margin_nm']<12:reasons.append('invalid_unresolved_or_seam_contour')
  elif not reasons:radius=closed[0]['radius_nm'];shape=closed[0]['shape']
 return t|dict(periodic_core_sizes=sizes,resolved_core_count=resolved,closed_contour_count=count,valid_single=not reasons,center_nm=center if not reasons else None,radius_nm=radius,shape=shape,invalid_reasons=reasons)
