"""Analytic textures and train-only calibration. No field or ODE calls."""
import numpy as np
from .geometry import measure,wrap
from .io import content_sha

def texture(*,cells=96,center=(112e-9,133e-9),radius=24e-9,ratio=1.,angle=.37,chi=.6,modulation=0.,flip=False,L=256e-9):
    nx,ny=(cells,cells) if isinstance(cells,int) else cells
    h=np.array([L/nx,L/ny,3e-9]);origin=np.zeros(3);yy,xx=np.meshgrid((np.arange(ny)+.5)*h[1],(np.arange(nx)+.5)*h[0],indexing='ij');dx=(xx-center[0]+L/2)%L-L/2;dy=(yy-center[1]+L/2)%L-L/2
    a=radius*np.sqrt(ratio);b=radius/np.sqrt(ratio);u=np.cos(angle)*dx+np.sin(angle)*dy;v=-np.sin(angle)*dx+np.cos(angle)*dy;r=radius*np.hypot(u/a,v/b)
    width=radius/6;s=np.clip((r-(radius-2*width))/(4*width),0,1);smooth=6*s**5-15*s**4+10*s**3;theta=np.pi*(1-smooth)
    phi=np.arctan2(dy,dx);psi=phi+chi+modulation*np.sin(2*phi);m=np.stack((np.sin(theta)*np.cos(psi),np.sin(theta)*np.sin(psi),np.cos(theta)),-1)
    if flip:m=-m
    rot=np.array([[np.cos(angle),-np.sin(angle)],[np.sin(angle),np.cos(angle)]]);S=rot@np.diag([a*a/4,b*b/4])@rot.T
    truth=dict(center=np.array(center),radius=radius,major=a,minor=b,axis=angle%np.pi,chi=float(wrap(chi+(np.pi if flip else 0))),Q=1. if flip else -1.,cov=S,modulation=modulation)
    return m,h,origin,truth

def calibrate():
    errors=[];train=[]
    for n in (64,96,128):
        for j,(ratio,modulation) in enumerate(((1.,0.),(1.35,0.),(1.,.2))):
            for corner in (False,True):
                center=((253.7e-9,2.9e-9) if corner else (111.37e-9,133.83e-9))
                m,h,o,t=texture(cells=n,center=center,ratio=ratio,modulation=modulation,angle=.37,chi=.63)
                v=measure(m,h,o,'periodic_xy')
                if not v['valid_geometry'] or v.get('n')!=1:raise RuntimeError('calibration training geometry failed; inspect without adjusting gates')
                L=np.array([n,n])*h[:2]
                ce=max(np.linalg.norm((np.array([v[k+'x'],v[k+'y']])-t['center']+L/2)%L-L/2) for k in ('area_','topo_'))/t['radius']
                e=dict(center_rel=float(ce),radius_rel=abs(v['radius_m']/t['radius']-1),moment_rel=float(np.linalg.norm(v['_cov']-t['cov'],2)/t['radius']**2),charge=abs(v['Q']-t['Q']),phase=float(abs(wrap(v['chi_raw']-t['chi']))),sampling=v['phase_sampling_error'])
                errors.append(e);train.append(dict(cells=n,corner=corner,ratio=ratio,modulation=modulation,errors=e,coherence=v['coherence'],radius_cells=v['radius_cells'],cancellation=v['charge_cancellation'],chart_rel=v['chart_sensitivity_m']/t['radius'],seam=v['seam_abs_charge'],coherence_sampling_error=v['coherence_sampling_error']))
    floor=128*128*128*np.finfo(float).eps
    # Factor two is a declared engineering margin over TRAIN error envelopes,
    # frozen before held-out data, not a universal physical confidence interval.
    bounds={k:max(floor,2*max(e[k] for e in errors)) for k in errors[0]}
    c=dict(schema='skyrmion-calibration-v1',id='compact-wall-train-v1',training=train,
           domain='single localized n=1 compact wall; R/h>=train minimum; weak local phase modulation<=0.2rad. Not a continuum certificate.',
           margin='2x train-only envelope plus accumulation floor; independent holdout never retunes thresholds',
           min_radius_cells=min(x['radius_cells'] for x in train),charge_error=bounds['charge'],
           max_cancellation=max(x['cancellation'] for x in train)+floor,
           chart_error_rel=max(floor,2*max(x['chart_rel'] for x in train)),seam_charge=max(floor,2*max(x['seam'] for x in train)),
           moment_error_rel=bounds['moment_rel'],min_coherence=min(x['coherence'] for x in train)-max(floor,2*max(x['coherence_sampling_error'] for x in train)),
           phase_sampling_error=bounds['sampling'],accuracy_envelopes=bounds,
           phase_policy='complete arclength coverage only; P=total perimeter; wrapped phase residual; raw phase retained when aggregate is invalid')
    c['sha256']=content_sha(c)
    return c

def validate_calibration(c):
    value=dict(c);expected=value.pop('sha256',None)
    if c.get('schema')!='skyrmion-calibration-v1' or expected!=content_sha(value):raise ValueError('calibration schema/content checksum mismatch')
    return c
