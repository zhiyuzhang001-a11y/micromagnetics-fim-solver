"""Offline analytic example, never LLG. Explicit fresh output directory required."""
from pathlib import Path
import json,sys
import numpy as np

from .pipeline import analyze_ovf
from .calibration import texture

def write_direction(path,m,h,o,label,metadata):
    ny,nx=m.shape[:2]
    head=['# OOMMF OVF 2.0','# Segment count: 1','# Begin: Segment','# Begin: Header',
          '# Desc: sublattice='+label,'# Desc: '+'; '.join(k+'='+str(v) for k,v in metadata.items()),
          '# meshtype: rectangular','# meshunit: m','# valuedim: 3','# valueunits: 1 1 1','# valuelabels: mx my mz']
    for i,(axis,n) in enumerate(zip('xyz',(nx,ny,1))):
        head.extend([f'# {axis}nodes: {n}',f'# {axis}base: {o[i]+h[i]/2:.17g}',f'# {axis}stepsize: {h[i]:.17g}',f'# {axis}min: {o[i]:.17g}',f'# {axis}max: {o[i]+n*h[i]:.17g}'])
    with Path(path).open('x') as f:
        f.write('\n'.join(head+['# End: Header','# Begin: Data Text'])+'\n')
        np.savetxt(f,m.reshape(-1,3),fmt='%.17g')
        f.write('# End: Data Text\n# End: Segment\n')

def generate(output):
    """Five nonuniform times, seam crossing, breathing and antiparallel B."""
    output=Path(output).resolve();output.mkdir(exist_ok=False);frames=[]
    for i,t in enumerate((0.,1e-10,2.5e-10,4.5e-10,7e-10)):
        pair={}
        for label,flip in (('A',False),('B',True)):
            center=np.array([254e-9,3e-9])+np.array([10.,-3.])*t+(np.array([6e-9,-3e-9]) if flip else 0)
            m,h,o,_=texture(cells=112,center=center,radius=(24e-9+i*.2e-9)*(1.08 if flip else 1),chi=3.+i*.1+(.15 if flip else 0),flip=flip)
            path=output/f'{i}_{label}.ovf'
            write_direction(path,m,h,o,label,dict(boris_metadata_version=1,quantity='unit_direction',stage='rk4',time_s=repr(t),accepted_index=i,boundary='periodic_xy',mirrors='10,10',run_id='analytic-example',segment_id='analytic-motion'))
            pair[label]=path
        frames.append(pair)
    (output/'inputs.json').write_text(json.dumps([{k:str(v) for k,v in p.items()} for p in frames],indent=2)+'\n')
    return analyze_ovf(frames,output/'analysis.csv',assume_temporal_sampling=True,ab_reference='antiparallel')

if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('output',type=Path,help='new directory; never overwrite')
    rows=generate(parser.parse_args().output)
    print(json.dumps({'rows':len(rows),'valid_geometry':all(r['A_valid_geometry'] and r['B_valid_geometry'] for r in rows),'valid_velocity_rows':sum(r['valid_velocity'] for r in rows),'scientific_fields':0}))
