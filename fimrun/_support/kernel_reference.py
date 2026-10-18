"""Independent Decimal Newell mathematical reference; no native code calls."""
from decimal import Decimal as D, localcontext
from functools import lru_cache
from itertools import product
import json,time,resource
from pathlib import Path

def atan(x):
 if not x:return D(0)
 sign=D(-1) if x<0 else D(1); x=abs(x);factor=D(1)
 while x>D('.1'):
  x=x/(1+(1+x*x).sqrt());factor*=2
 term=x;out=x;k=1;tol=D(10)**(-__import__('decimal').getcontext().prec+5)
 while True:
  term*=-x*x;k+=2;q=term/k;out+=q
  if abs(q)<tol:return sign*factor*out
@lru_cache(None)
def pi_at(prec):
 with localcontext() as ctx:
  ctx.prec=prec
  return 16*atan(D(1)/5)-4*atan(D(1)/239)
def asinh(x):return (x+(1+x*x).sqrt()).ln()
def primitive_f(x,y,z):
 x,y,z=abs(x),abs(y),abs(z);R=(x*x+y*y+z*z).sqrt()
 if not R:return D(0)
 v=(2*x*x-y*y-z*z)*R/6
 if x*x+z*z:v+=y*(z*z-x*x)*asinh(y/(x*x+z*z).sqrt())/2
 if x*x+y*y:v+=z*(y*y-x*x)*asinh(z/(x*x+y*y).sqrt())/2
 if x:v-=x*y*z*atan(y*z/(x*R))
 return v
def primitive_g(x,y,z):
 if not x or not y:return D(0)
 sign=(-1 if x<0 else 1)*(-1 if y<0 else 1);x,y,z=abs(x),abs(y),abs(z);R=(x*x+y*y+z*z).sqrt()
 v=-x*y*R/3+x*y*z*asinh(z/(x*x+y*y).sqrt())
 v+=y*(3*z*z-y*y)*asinh(x/(y*y+z*z).sqrt())/6
 v+=x*(3*z*z-x*x)*asinh(y/(x*x+z*z).sqrt())/6
 if z:v-=z**3*atan(x*y/(z*R))/6
 v-=y*y*z*atan(x*z/(y*R))/2+x*x*z*atan(y*z/(x*R))/2
 return sign*v
def tensor(h,r,prec):
 with localcontext() as ctx:
  ctx.prec=prec
  h=[D(str(q)) for q in h];r=[D(str(q)) for q in r];scale=max(h);h=[q/scale for q in h];r=[q/scale for q in r]
  total=[D(0)]*6;w=[-1,2,-1]
  for i,j,k in product(range(-1,2),repeat=3):
   x,y,z=[r[a]+b*h[a] for a,b in enumerate([i,j,k])];ww=w[i+1]*w[j+1]*w[k+1]
   vals=[primitive_f(x,y,z),primitive_f(y,x,z),primitive_f(z,x,y),primitive_g(x,y,z),primitive_g(x,z,y),primitive_g(y,z,x)]
   total=[a+ww*b for a,b in zip(total,vals)]
  den=4*pi_at(prec)*h[0]*h[1]*h[2]
  return [q/den for q in total]
def grid_tensor(hdec,i,j,prec):
 # exact decimal h * integer, not binary input multiplication
 with localcontext() as ctx:
  ctx.prec=prec
  h=[D(q) for q in hdec];r=[h[0]*i,h[1]*j,D(0)]
  return tensor(h,r,prec)
def stable(h,r):
 rows=[tensor(h,r,p) for p in [70,90,110]]
 return rows,max(abs(a-b) for a,b in zip(rows[-2],rows[-1]))
