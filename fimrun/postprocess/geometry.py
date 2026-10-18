"""Single-layer signed topology, local charts and area/phase observables (SI)."""
import time
import numpy as np
from .io import tool

def wrap(a):return np.angle(np.exp(1j*a))
def image(delta,L):return delta-L*np.floor(delta/L+.5)
def moments(v):
    offset=v.mean(0);v=v-offset;x,y=v.T;u,w=np.roll(v,-1,axis=0).T;c=x*w-u*y;A=c.sum()/2
    if A<0:return moments((v+offset)[::-1])
    if not np.isfinite(A) or A<=0:raise ValueError('zero_area')
    center=np.array([((x+u)*c).sum(),((y+w)*c).sum()])/(6*A)
    xx=((x*x+x*u+u*u)*c).sum()/(12*A)-center[0]**2
    yy=((y*y+y*w+w*w)*c).sum()/(12*A)-center[1]**2
    xy=((2*x*y+x*w+u*y+2*u*w)*c).sum()/(24*A)-center[0]*center[1]
    S=np.array([[xx,xy],[xy,yy]]);lam,U=np.linalg.eigh(S)
    return A,center+offset,S,lam,U

def inside(point,v):
    a=v-point;b=np.roll(a,-1,axis=0)
    return abs(np.sum(np.arctan2(a[:,0]*b[:,1]-a[:,1]*b[:,0],(a*b).sum(1))))>np.pi

def interpolate(m,points,h,origin,periodic):
    ny,nx=m.shape[:2];u=(points-origin[:2])/h[:2]-.5;i=np.floor(u).astype(int);f=u-i
    if not periodic and ((u<0).any() or (u>np.array([nx-1,ny-1])).any()):raise ValueError('contour_outside_sampled_domain')
    x=i[:,0]%nx;y=i[:,1]%ny;xx=(x+1)%nx;yy=(y+1)%ny
    fx,fy=f[:,0,None],f[:,1,None]
    return (1-fy)*((1-fx)*m[y,x]+fx*m[y,xx])+fy*((1-fx)*m[yy,x]+fx*m[yy,xx])

def phase(m,v,center,h,origin,periodic,ds):
    edge=np.roll(v,-1,axis=0)-v;length=np.linalg.norm(edge,axis=1);P=length.sum()
    count=max(16,int(np.ceil(P/ds)))
    if count>100000:raise ValueError('phase_sample_limit')
    arc=np.arange(count)*P/count;cum=np.r_[0,np.cumsum(length)];ids=np.searchsorted(cum,arc,side='right')-1
    points=v[ids]+edge[ids]*((arc-cum[ids])/length[ids])[:,None]
    field=interpolate(m,points,h,origin,periodic);amplitude=np.linalg.norm(field[:,:2],axis=1)
    if (amplitude<=np.finfo(float).eps*32).any():raise ValueError('undefined_inplane_phase')
    psi=np.arctan2(field[:,1],field[:,0]);phi=np.arctan2(points[:,1]-center[1],points[:,0]-center[0])
    increments=wrap(np.roll(psi,-1)-psi);winding=increments.sum()/(2*np.pi);n=int(round(winding))
    local=wrap(psi-n*phi);Z=np.exp(1j*local).mean();chi=np.angle(Z);C=abs(Z)
    residual=wrap(local-chi)
    return dict(n=n,winding_error=abs(winding-n),chi_raw=float(chi),coherence=float(C),phase_rms=float(np.sqrt(np.mean(residual**2))),phase_p95=float(np.quantile(abs(residual),.95)),phase_coverage=1.,phase_samples=count,max_phase_increment=float(abs(increments).max()))

def measure(m,h,origin,boundary,*,calibration=None):
    """Raw values remain diagnostic when any calibrated validity gate fails."""
    periodic=boundary=='periodic_xy';ny,nx=m.shape[:2];L=np.array([nx,ny])*h[:2]
    if boundary not in ('open','periodic_xy'):raise ValueError('unknown_boundary')
    out=dict(valid_geometry=False,valid_topology=False,valid_helicity=False,valid_axis=False,reasons=[])
    if min(nx,ny)<3:out['reasons'].append('undersampled_grid');return out
    a=m if periodic else m[:-1,:-1];b=np.roll(m,-1,1) if periodic else m[:-1,1:]
    c=np.roll(np.roll(m,-1,0),-1,1) if periodic else m[1:,1:];d=np.roll(m,-1,0) if periodic else m[1:,:-1]
    charges=[];bad=0
    for x,y,z in ((a,b,c),(a,c,d)):
        xy=(x*y).sum(-1);yz=(y*z).sum(-1);zx=(z*x).sum(-1);det=(x*np.cross(y,z)).sum(-1);den=1+xy+yz+zx
        invalid=(xy<=-1+32*np.finfo(float).eps)|(yz<=-1+32*np.finfo(float).eps)|(zx<=-1+32*np.finfo(float).eps)|(np.hypot(det,den)<=32*np.finfo(float).eps)
        bad+=int(invalid.sum());charges.append(2*np.arctan2(det,den)/(4*np.pi))
    q1,q2=charges;Q=float(q1.sum()+q2.sum());out.update(Q=Q,singular_triangles=bad)
    if bad or abs(Q)<=np.finfo(float).eps*(nx*ny)*32:out['reasons'].append('singular_or_zero_topology');return out
    kappa=float((abs(q1).sum()+abs(q2).sum())/abs(Q));out['charge_cancellation']=kappa
    yy,xx=np.meshgrid(origin[1]+(np.arange(ny)+.5)*h[1],origin[0]+(np.arange(nx)+.5)*h[0],indexing='ij')
    cellq=np.zeros((ny,nx))
    if periodic:
        cellq=(q1+q2+np.roll(q1,1,1)+np.roll(q1+q2,(1,1),(0,1))+np.roll(q2,1,0))/3
        Z=np.array([(cellq*np.exp(2j*np.pi*(xx-origin[0])/L[0])).sum()/Q,(cellq*np.exp(2j*np.pi*(yy-origin[1])/L[1])).sum()/Q])
        out['seed_strength_x'],out['seed_strength_y']=map(float,abs(Z))
        if (abs(Z)<=np.finfo(float).eps*nx*ny*32).any():out['reasons'].append('degenerate_signed_seed');return out
        seed=origin[:2]+(np.angle(Z)%(2*np.pi))*L/(2*np.pi)
    else:
        for q,offsets in [(q1,((0,0),(0,1),(1,1))),(q2,((0,0),(1,1),(1,0)))]:
            for dy,dx in offsets:cellq[dy:dy+ny-1,dx:dx+nx-1]+=q/3
        seed=np.array([(cellq*xx).sum(),(cellq*yy).sum()])/Q
    out['seed_x'],out['seed_y']=map(float,seed)
    # Grid-neighbour triangles lift to positive hx/hy edges FIRST. Only whole
    # triangle centroids subsequently change their periodic image.
    x=xx if periodic else xx[:-1,:-1];y=yy if periodic else yy[:-1,:-1]
    cs=[np.stack((x+2*h[0]/3,y+h[1]/3),-1),np.stack((x+h[0]/3,y+2*h[1]/3),-1)]
    def centroid(s):return sum((q[...,None]*(s+image(c-s,L) if periodic else c)).sum((0,1)) for q,c in zip(charges,cs))/Q
    rq=centroid(seed);out.update(topo_x=float(rq[0]),topo_y=float(rq[1]))
    sensitivity=0.;seam=0.
    if periodic:
        for shift in ((h[0],0),(-h[0],0),(0,h[1]),(0,-h[1])):
            sensitivity=max(sensitivity,float(np.linalg.norm(image(centroid(seed+shift)-rq,L))))
        for q,c in zip(charges,cs):
            delta=abs(image(c-seed,L));near=((L/2-delta)<2*h[:2]).any(-1);seam+=float(abs(q[near]).sum()/abs(Q))
    out.update(chart_sensitivity_m=sensitivity,seam_abs_charge=seam)
    bg=1 if np.median(m[...,2])>=0 else -1;mask=bg*m[...,2]<0;seen=np.zeros((ny,nx),bool);cores=[]
    for y0,x0 in np.argwhere(mask):
        if seen[y0,x0]:continue
        todo=[(y0,x0)];seen[y0,x0]=True;size=0
        while todo:
            y0,x0=todo.pop();size+=1
            for y1,x1 in ((y0-1,x0),(y0+1,x0),(y0,x0-1),(y0,x0+1)):
                if periodic:y1%=ny;x1%=nx
                if 0<=y1<ny and 0<=x1<nx and mask[y1,x1] and not seen[y1,x1]:seen[y1,x1]=True;todo.append((y1,x1))
        cores.append(size)
    out['core_count']=len(cores)
    shift=np.array([ny//2-int(np.floor((seed[1]-origin[1])/h[1])),nx//2-int(np.floor((seed[0]-origin[0])/h[0]))]) if periodic else np.array([0,0])
    paths,amb=tool('contour_geometry').contours(np.roll(m[...,2],shift,(0,1)),h[:2],time.monotonic()+20)
    closed=[p for p in paths if p['closed'] and p['valid']]
    out.update(contour_count=len(paths),ambiguous_cells=amb)
    if len(cores)!=1 or len(paths)!=1 or len(closed)!=1 or amb:out['reasons'].append('not_unique_contractible_core_contour');return out
    v=np.array(closed[0]['vertices_nm'])*1e-9+origin[:2]+L/2-shift[::-1]*h[:2]
    if np.sum(v[:,0]*np.roll(v[:,1],-1)-v[:,1]*np.roll(v[:,0],-1))<0:v=v[::-1]
    A,rs,S,lam,U=moments(v)
    if periodic:
        delta=seed+image(rs-seed,L)-rs;v+=delta;rs+=delta
    if lam[0]<=0 or not inside(rs,v) or (periodic and (np.ptp(v,axis=0)>=L-2*h[:2]).any()):out['reasons'].append('nonlocal_or_invalid_area');return out
    R=np.sqrt(A/np.pi);major,minor=2*np.sqrt(lam[::-1]);alpha=float(np.arctan2(U[1,1],U[0,1])%np.pi)
    tq=image(rq-rs,L) if periodic else rq-rs
    out.update(area_m2=float(A),area_x=float(rs[0]),area_y=float(rs[1]),radius_m=float(R),major_m=float(major),minor_m=float(minor),axis_ratio=float(major/minor),ellipticity=float((major-minor)/(major+minor)),axis_raw_rad=alpha,topo_area_dx=float(tq[0]),topo_area_dy=float(tq[1]),topo_area_distance_m=float(np.linalg.norm(tq)),radius_cells=float(R/max(h[:2])),_cov=S,_area=rs,_topo=rq,_contour=v)
    out['valid_geometry']=True;out['valid_topology']=True
    try:
        p=phase(m,v,rs,h,origin,periodic,min(h[:2])/2);fine=phase(m,v,rs,h,origin,periodic,min(h[:2])/4)
        out.update(p);out['phase_sampling_error']=float(abs(wrap(p['chi_raw']-fine['chi_raw'])));out['coherence_sampling_error']=abs(p['coherence']-fine['coherence'])
        near=np.rint((rs-origin[:2])/h[:2]-.5).astype(int)%[nx,ny];polarity=int(np.sign(m[near[1],near[0],2]));out['polarity']=polarity
        out['valid_helicity']=p['n']==1 and polarity!=0 and (calibration is None or abs(Q-polarity*p['n'])<calibration['charge_error'])
        if not out['valid_helicity']:out['reasons'].append('unsupported_winding_or_polarity')
    except ValueError as exc:out['reasons'].append(str(exc))
    if calibration:
        if out['radius_cells']<calibration['min_radius_cells']:out['reasons'].append('outside_spatial_calibration');out['valid_geometry']=False
        if kappa>calibration['max_cancellation'] or sensitivity/R>calibration['chart_error_rel'] or seam>calibration['seam_charge']:
            out['reasons'].append('unstable_topology_chart');out['valid_topology']=False
        if periodic and abs(abs(Q)-1)>calibration['charge_error']:out['reasons'].append('nonunit_charge');out['valid_topology']=False
        gap=(lam[1]-lam[0])/(R*R);out['valid_axis']=bool(out['valid_geometry'] and gap>2*calibration['moment_error_rel'])
        if not out['valid_axis']:out['reasons'].append('near_circular_or_unresolved_axis')
        if out.get('coherence',0)<calibration['min_coherence'] or out.get('phase_sampling_error',float('inf'))>calibration['phase_sampling_error']:
            out['reasons'].append('noncoherent_or_unresolved_phase');out['valid_helicity']=False
        out['valid_helicity']=bool(out['valid_helicity'] and out['valid_geometry'])
    out['axis_rad']=alpha if out['valid_axis'] else float('nan')
    out['chi_rad']=out.get('chi_raw',float('nan')) if out['valid_helicity'] else float('nan')
    return out
