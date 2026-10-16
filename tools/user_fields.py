"""Independent NumPy edge-energy/field assembly for user single-layer cases."""
from pathlib import Path
import json
import numpy as np
MU=4*np.pi*1e-7
LOOKUP=[[0,3,4],[3,1,5],[4,5,2]]

def evaluate(m,case,kernel):
 g=case['geometry'];c=case['material'];nx,ny,nz=g['n'];h=np.array(g['cell_nm'])*1e-9;V=float(np.prod(h));ms=c['Ms_Apm'];out=np.zeros_like(m);parts=np.zeros(7)
 for d,axis in [(0,2),(1,1)]:
  if g['n'][d]==1:continue
  periodic=g['pbc'][d];left=[slice(None)]*4;right=left.copy()
  if not periodic:left[axis]=slice(0,-1);right[axis]=slice(1,None)
  left,right=tuple(left),tuple(right)
  q=[m[i] if periodic else m[i][left] for i in [0,1]];r=[np.roll(m[i],-1,axis=axis) if periodic else m[i][right] for i in [0,1]];diff=[r[i]-q[i] for i in [0,1]]
  def accumulate(i,a,b):
   if periodic:out[i][...]+=a+np.roll(b,1,axis=axis)
   else:out[i][left]+=a;out[i][right]+=b
  if c['active'][0]:
   parts[1]+=.5*V*c['Anh_Jpm']*np.sum(diff[0]*diff[1])/(h[d]*h[d])
   for i in [0,1]:
    parts[0]+=.5*V*c['A_Jpm'][i]*np.sum(diff[i]*diff[i])/(h[d]*h[d]);a=(2*c['A_Jpm'][i]*diff[i]+c['Anh_Jpm']*diff[1-i])/(MU*ms[i]*h[d]*h[d]);accumulate(i,a,-a)
  if c['active'][2]:
   for i in [0,1]:
    parts[3]+=.5*V*c['D_Jpm2'][i]*np.sum(q[i][...,d]*r[i][...,2]-q[i][...,2]*r[i][...,d])/h[d];k=c['D_Jpm2'][i]/(MU*ms[i]*h[d]);a=np.zeros_like(q[i]);b=a.copy();a[...,d]=-k*r[i][...,2];a[...,2]=k*r[i][...,d];b[...,d]=k*q[i][...,2];b[...,2]=-k*q[i][...,d];accumulate(i,a,b)
 if c['active'][1]:
  parts[2]=-2*c['Ah_Jpm3']*V*np.sum(m[0]*m[1])
  for i in [0,1]:out[i]+=4*c['Ah_Jpm3']*m[1-i]/(MU*ms[i])
 if c['active'][3]:
  for i in [0,1]:
   axis=np.array(c['axes'][i]);u=np.sum(m[i]*axis,axis=-1);s=1-u*u;parts[4]+=.5*V*np.sum(c['K1_Jpm3'][i]*s+c['K2_Jpm3'][i]*s*s);out[i]+=(2*u*(c['K1_Jpm3'][i]+2*c['K2_Jpm3'][i]*s)/(MU*ms[i]))[...,None]*axis
 from kernel_cache import layout
 px,py=layout(case);K=np.fromfile(kernel,dtype='<f8').reshape(py,px,6);M=(ms[0]*m[0]+ms[1]*m[1])/2;padded=np.zeros((py,px,3));padded[:ny,:nx]=M[0];F=np.fft.rfft2(padded,axes=(0,1));Ks=np.fft.rfft2(K,axes=(0,1));Hd=np.stack([np.fft.irfft2(-sum(Ks[...,LOOKUP[a][b]]*F[...,b] for b in range(3)),s=(py,px)) for a in range(3)],-1)[:ny,:nx][None];external=np.array(case['field']['H_Apm']);out+=Hd+external;parts[5]=-.5*MU*V*np.sum(M*Hd);parts[6]=-MU*V*np.sum(M*external)
 return out,parts

def residual(m,H):return np.linalg.norm(H-m*np.sum(m*H,axis=-1,keepdims=True),axis=-1).reshape(2,-1).max(axis=1)
def verify(directory,case,kernel):
 out=Path(directory);nx,ny,nz=case['geometry']['n'];shape=(2,nz,ny,nx,3);m=np.fromfile(out/'final.bin',dtype='<f8').reshape(shape);saved=np.stack([np.fromfile(out/('final_H_'+s+'.bin'),dtype='<f8').reshape(shape[1:]) for s in ['A','B']]);native=json.loads((out/'result.json').read_text());H,E=evaluate(m,case,kernel);r=residual(m,H);error=float(np.max(np.linalg.norm(H-saved,axis=-1))/max(1.,float(np.max(np.linalg.norm(H,axis=-1)))));dr=float(np.max(np.abs(r-[native['residual_A_Apm'],native['residual_B_Apm']])));V=np.prod(np.array(case['geometry']['cell_nm'])*1e-9);scale=MU*V*nx*ny*max(case['material']['Ms_Apm'])**2/2;energy=json.loads((out/'final_energy.json').read_text());energy_error=float(np.max(np.abs(E-energy['parts_J']))/scale);unit=float(np.max(np.abs(np.linalg.norm(m,axis=-1)-1)));passed=bool(np.isfinite(m).all() and np.isfinite(H).all() and unit<=1e-12 and error<=1e-10 and dr<=1e-6 and energy_error<=1e-10)
 return {'passed':passed,'real_fields':1,'field_error':error,'residual_difference_Apm':dr,'energy_parts_error_over_scale':energy_error,'unit_error':unit,'A_B_Apm':r.tolist(),'static_criterion_met':bool(np.max(r)<=case['static']['tol_Apm'])}
