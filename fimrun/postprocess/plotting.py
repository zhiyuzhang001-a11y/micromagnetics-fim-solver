"""Dependency-free SVG result display; reads selected analysis rows only."""
from html import escape
import math

def _number(row,key,scale=1.):
    try:value=float(row.get(key,float('nan')))*scale
    except (TypeError,ValueError):return float('nan')
    return value if math.isfinite(value) else float('nan')

def _yes(row,key):return row.get(key) is True or str(row.get(key)).lower()=='true'

def summary_svg(rows):
    """Return a self-contained SVG for one stage, with validity/gap handling.

    Dynamic centers use tracked coordinates if any are available; otherwise
    wrapped centers are points only. Static centers always use wrapped values.
    No rows, plotting packages, browser, file writes or solver calls are required.
    """
    rows=list(rows);stages={r.get('stage') for r in rows if r.get('stage') is not None}
    if len(stages)>1:raise ValueError('select one stage for SVG display')
    dynamic=stages=={'rk4'};static=stages=={'sdesc'}
    tracked=dynamic and any(_yes(r,'valid_tracking') for r in rows)
    iterations=static and any(math.isfinite(_number(r,'iteration')) for r in rows)
    time_label='time [ps]' if dynamic else 'accepted iteration' if iterations else 'input index (time/iteration unknown)'
    def abscissa(r):
        return _number(r,'time_s',1e12) if dynamic else _number(r,'iteration') if iterations else _number(r,'input_index')
    def center(r,label):
        if not _yes(r,label+'_valid_geometry') or (tracked and not _yes(r,'valid_tracking')):return (math.nan,math.nan)
        prefix=label+'_area_'+('unwrapped_' if tracked else '')
        return _number(r,prefix+'x',1e9),_number(r,prefix+'y',1e9)
    def scalar(r,label,key,flag,scale=1.):
        return (abscissa(r),_number(r,label+'_'+key,scale)) if _yes(r,label+'_'+flag) else (math.nan,math.nan)
    definitions=[('Area center ('+('tracked' if tracked else 'wrapped points')+')','x [nm]','y [nm]',center,tracked),
                 ('Area radius',time_label,'radius [nm]',lambda r,l:scalar(r,l,'radius_m','valid_geometry',1e9),True),
                 ('Moment shape',time_label,'major / minor',lambda r,l:scalar(r,l,'axis_ratio','valid_geometry'),True),
                 ('Helicity (raw A/B reference)',time_label,'chi [rad]',lambda r,l:scalar(r,l,'chi_rad','valid_helicity'),True)]
    svg=['<svg xmlns="http://www.w3.org/2000/svg" width="1040" height="760" viewBox="0 0 1040 760" role="img" aria-labelledby="title desc">',
         '<title id="title">Selected offline skyrmion measurements</title>',
         '<desc id="desc">Four panels: area center, area radius, moment axis ratio and helicity. Invalid or missing points break lines. SI-derived axes; no solver calls.</desc>',
         '<rect width="1040" height="760" fill="white"/>',
         '<style>text{font-family:system-ui,sans-serif;fill:#182333}.title{font-size:16px;font-weight:600}.label{font-size:12px}.tick{font-size:11px;fill:#526070}</style>',
         '<text x="32" y="27" class="title">Offline OVF measurements — selected rows only</text>',
         '<text x="32" y="48" class="label">A: blue · B: orange · invalid/missing rows break lines · phase wraps break lines</text>']
    for panel,(title,xlabel,ylabel,values,connect) in enumerate(definitions):
        left=82+(panel%2)*510;top=95+(panel//2)*310;w=400;h=200
        series={label:[values(r,label) for r in rows] for label in ('A','B')}
        points=[p for seq in series.values() for p in seq if all(math.isfinite(z) for z in p)]
        svg.append(f'<text x="{left}" y="{top-18}" class="title">{escape(title)}</text>')
        if points:
            xmin=min(p[0] for p in points);xmax=max(p[0] for p in points);ymin=min(p[1] for p in points);ymax=max(p[1] for p in points)
            dx=xmax-xmin;dy=ymax-ymin
            dx=dx if dx>0 else max(abs(xmin)*.02,1.)
            dy=dy if dy>0 else max(abs(ymin)*.02,.1)
            # Equal physical aspect for centers prevents geometric distortion.
            if panel==0:dx=max(dx,dy*w/h);dy=dx*h/w
            cx=(xmin+xmax)/2;cy=(ymin+ymax)/2;xmin=cx-dx*.56;xmax=cx+dx*.56;ymin=cy-dy*.56;ymax=cy+dy*.56
        else:xmin,xmax,ymin,ymax=0.,1.,0.,1.
        def pixel(p):return left+(p[0]-xmin)/(xmax-xmin)*w,top+h-(p[1]-ymin)/(ymax-ymin)*h
        for j in range(5):
            x=left+j*w/4;y=top+j*h/4
            svg.append(f'<path d="M{x:.3f},{top}V{top+h} M{left},{y:.3f}H{left+w}" stroke="#e4e9ef" fill="none"/>')
            svg.append(f'<text x="{x:.3f}" y="{top+h+17}" text-anchor="middle" class="tick">{xmin+(xmax-xmin)*j/4:.5g}</text>')
            svg.append(f'<text x="{left-8}" y="{y+4:.3f}" text-anchor="end" class="tick">{ymax-(ymax-ymin)*j/4:.5g}</text>')
        svg.append(f'<rect x="{left}" y="{top}" width="{w}" height="{h}" fill="none" stroke="#8794a5"/>')
        svg.append(f'<text x="{left+w/2}" y="{top+h+38}" text-anchor="middle" class="label">{escape(xlabel)}</text>')
        svg.append(f'<text transform="translate({left-58},{top+h/2}) rotate(-90)" text-anchor="middle" class="label">{escape(ylabel)}</text>')
        if not points:svg.append(f'<text x="{left+w/2}" y="{top+h/2}" text-anchor="middle" class="label">No valid samples</text>')
        for label,color in (('A','#1864ab'),('B','#d36316')):
            previous=None
            for i,p in enumerate(series[label]):
                if not all(math.isfinite(z) for z in p):previous=None;continue
                x,y=pixel(p);r=rows[i]
                key=(r.get('run_id'),r.get('segment_id'),r.get('stage'),r.get('tracking_part') if panel==0 else None)
                if previous and connect:
                    old,oldkey,oldpixel=previous
                    # Do not bridge stage/segment, invalid rows, repeated clocks,
                    # or the discontinuity of a circular phase at +/-pi.
                    continuous=key==oldkey and (panel==0 or p[0]>old[0]) and (panel!=3 or abs(p[1]-old[1])<=math.pi)
                    if continuous:svg.append(f'<path data-series="{label}" d="M{oldpixel[0]:.3f},{oldpixel[1]:.3f}L{x:.3f},{y:.3f}" fill="none" stroke="{color}" stroke-width="1.5"/>')
                svg.append(f'<circle data-series="{label}" data-panel="{panel}" cx="{x:.3f}" cy="{y:.3f}" r="3" fill="{color}"/>')
                previous=(p,key,(x,y))
    invalid=sum(not(_yes(r,'A_valid_geometry') and _yes(r,'B_valid_geometry')) for r in rows)
    svg.append(f'<text x="32" y="728" class="label">Rows: {len(rows)} · invalid geometry pairs: {invalid} · empirical calibration domain; no continuum/time-sampling guarantee</text>')
    svg.append('<text x="32" y="747" class="label">Static centers use wrapped coordinates. Wrapped centers are points, not an inferred continuous trajectory.</text></svg>')
    return ''.join(svg)
