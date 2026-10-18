import numpy as np
import time
from collections import defaultdict
def polygon(vertices,deadline=None):
 v=np.array(vertices,dtype=float);x,y=v[:,0],v[:,1];u=np.roll(x,-1);w=np.roll(y,-1);cross=x*w-u*y;A=float(cross.sum()/2)
 if abs(A)<1e-14:return dict(valid=False,reason='zero_area')
 cx=float(np.sum((x+u)*cross)/(6*A));cy=float(np.sum((y+w)*cross)/(6*A));cov=np.array([[np.sum((x*x+x*u+u*u)*cross)/(12*A)-cx*cx,np.sum((2*x*y+x*w+u*y+2*u*w)*cross)/(24*A)-cx*cy],[0.,np.sum((y*y+y*w+w*w)*cross)/(12*A)-cy*cy]]);cov[1,0]=cov[0,1];lam=np.linalg.eigvalsh(cov)
 # Blocked all non-adjacent segment intersections: proper crossing, touch, collinear overlap.
 n=len(v);selfcross=False;c=v[None,:,:];d=np.roll(v,-1,axis=0)[None,:,:];j=np.arange(n)[None,:];eps=1e-10
 def orient(a,b,c):return (b[...,0]-a[...,0])*(c[...,1]-a[...,1])-(b[...,1]-a[...,1])*(c[...,0]-a[...,0])
 def on(a,b,p):return (np.abs(orient(a,b,p))<=eps)&(p[...,0]>=np.minimum(a[...,0],b[...,0])-eps)&(p[...,0]<=np.maximum(a[...,0],b[...,0])+eps)&(p[...,1]>=np.minimum(a[...,1],b[...,1])-eps)&(p[...,1]<=np.maximum(a[...,1],b[...,1])+eps)
 for first in range(0,n,32):
  if deadline is not None and time.monotonic()>deadline:raise RuntimeError('observation resource deadline')
  i=np.arange(first,min(first+32,n))[:,None];a=v[first:first+32,None,:];b=np.roll(v,-1,axis=0)[first:first+32,None,:]
  o1=orient(a,b,c);o2=orient(a,b,d);o3=orient(c,d,a);o4=orient(c,d,b)
  proper=((o1>eps)&(o2<-eps)|(o1<-eps)&(o2>eps))&((o3>eps)&(o4<-eps)|(o3<-eps)&(o4>eps))
  hits=proper|on(a,b,c)|on(a,b,d)|on(c,d,a)|on(c,d,b);hits&=(i<j)&(j!=i+1)&~((i==0)&(j==n-1))
  if hits.any():selfcross=True;break
 valid=bool(lam[0]>0 and not selfcross)
 return dict(valid=valid,self_crossing=selfcross,area_nm2=abs(A),area_centroid_nm=[cx,cy],radius_nm=float(np.sqrt(abs(A)/np.pi)),shape=float(np.sqrt(lam[-1]/lam[0])-1) if lam[0]>0 else None,principal_ratio=float(np.sqrt(lam[-1]/lam[0])) if lam[0]>0 else None,eigenvalues_nm2=lam.tolist(),span_nm=[float(np.ptp(x)),float(np.ptp(y))])

def contours(z,h,deadline=None):
 ny,nx=z.shape;hx,hy=(h,h) if np.isscalar(h) else h;hn=hx/1e-9;yn=hy/1e-9;axis=(np.arange(nx)-(nx-1)/2)*hn;yaxis=(np.arange(ny)-(ny-1)/2)*yn;adj=defaultdict(list);coords={};ambiguous=0
 lo=np.minimum.reduce([z[:-1,:-1],z[:-1,1:],z[1:,1:],z[1:,:-1]]);hi=np.maximum.reduce([z[:-1,:-1],z[:-1,1:],z[1:,1:],z[1:,:-1]])
 for y,x in np.argwhere((lo<=0)&(hi>=0)):
  y=int(y);x=int(x);f=[z[y,x],z[y,x+1],z[y+1,x+1],z[y+1,x]]
  if any(q==0 for q in f):ambiguous+=1;continue
  sides=[(0,1,('h',x,y)),(1,2,('v',x+1,y)),(2,3,('h',x,y+1)),(3,0,('v',x,y))];p=[(axis[x],yaxis[y]),(axis[x+1],yaxis[y]),(axis[x+1],yaxis[y+1]),(axis[x],yaxis[y+1])];cross=[]
  for k,(a,b,key) in enumerate(sides):
   if (f[a]>0)==(f[b]>0):continue
   r=f[a]/(f[a]-f[b]);coords[key]=(p[a][0]+r*(p[b][0]-p[a][0]),p[a][1]+r*(p[b][1]-p[a][1]));cross.append(k)
  if len(cross)==2:pairs=[cross]
  elif len(cross)==4:
   determinant=f[0]*f[2]-f[1]*f[3]
   if abs(determinant)<=1e-14:ambiguous+=1;continue
   pairs=[(0,1),(2,3)] if determinant>0 else [(0,3),(1,2)]
  else:ambiguous+=1;continue
  for a,b in pairs:
   ka,kb=sides[a][2],sides[b][2];adj[ka].append(kb);adj[kb].append(ka)
 paths=[];visited=set()
 for root in list(adj):
  if root in visited:continue
  component=[];todo=[root];seen={root}
  while todo:
   q=todo.pop();component.append(q)
   for other in adj[q]:
    if other not in seen:seen.add(other);todo.append(other)
  ends=[q for q in component if len(adj[q])==1];start=ends[0] if ends else root;path=[];pathset=set();prev=None;cur=start;closed=False
  for _ in range(len(component)+1):
   if cur in pathset:closed=cur==start;break
   path.append(cur);pathset.add(cur);nexts=[q for q in adj[cur] if q!=prev]
   if not nexts:break
   prev,cur=cur,nexts[0]
  visited.update(component);v=[coords[q] for q in path];valid_degrees=all(len(adj[q]) in (1,2) for q in component)
  item=dict(closed=closed,graph_valid=valid_degrees,vertices_nm=v)
  if closed and len(v)>=3:item.update(polygon(v,deadline))
  else:item.update(valid=False,span_nm=[float(np.ptp(np.array(v)[:,0])),float(np.ptp(np.array(v)[:,1]))] if v else [0,0])
  margin=min((min(nx*hn/2-abs(pt[0]),ny*yn/2-abs(pt[1])) for pt in v),default=0);item['edge_margin_nm']=float(margin);paths.append(item)
 return paths,ambiguous
