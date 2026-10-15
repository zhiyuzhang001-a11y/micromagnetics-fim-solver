"""Audited independent fixed-material NumPy field expression, relocatable bindings.
Function body retained verbatim; wrapper is newly packaged, not independently accepted.
"""
import numpy as np
mu=4*np.pi*1e-7
ms=[3e5,6e5]
lookup=[[0,3,4],[3,1,5],[4,5,2]]
def configure(kernel):
 global K,c
 K=np.fromfile(kernel,dtype='=f8').reshape(125,125,6)
 c={'external_H_Apm':[0,0,-.002/mu]}
def fields(m):
 M=(ms[0]*m[0]+ms[1]*m[1])/2;F=np.fft.rfft2(M[0],axes=(0,1));Ks=np.fft.rfft2(K,axes=(0,1));H=np.array([np.fft.irfft2(-sum(Ks[...,lookup[a][b]]*F[...,b] for b in range(3)),s=(125,125)) for a in range(3)]).transpose(1,2,0)[None];out=np.zeros_like(m)
 for i in range(2):
  for d,axis in [(0,2),(1,1)]:
   right=np.roll(m[i],-1,axis=axis);left=np.roll(m[i],1,axis=axis);opp=np.roll(m[1-i],-1,axis=axis)+np.roll(m[1-i],1,axis=axis)-2*m[1-i]
   out[i]+=(1e-11*(right+left-2*m[i])-5e-12*opp)/(mu*ms[i]*16e-18)
   q=.00105/(mu*ms[i]*4e-9);out[i,...,d]-=q*(right[...,2]-left[...,2]);out[i,...,2]+=q*(right[...,d]-left[...,d])
  out[i]+=-32e6*m[1-i]/(mu*ms[i]);out[i,...,2]+=218000*m[i,...,2]/(mu*ms[i])
 return out+H+np.array(c['external_H_Apm'])
