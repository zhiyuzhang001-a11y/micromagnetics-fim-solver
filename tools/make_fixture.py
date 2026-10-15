"""Generate a synthetic fixed-material fixture. No private OVF input."""
from pathlib import Path
import argparse,math,struct,json,hashlib
HEADER='P-Anh-v1 synthetic public_synthetic\n125 125 1\n4e-9 4e-9 3e-9\n1 1 0\n300000 600000\n5e-12 5e-12\n-8e6 -8e6\n-5e-12 -5e-12\n0.00105 0.00105\n109000 109000\n0 0\n0 0 1\n1 1 1 1\n1 30 2147483648\n'
def make(out,texture='uniform'):
 out=Path(out);out.mkdir(parents=True,exist_ok=False);A=[]
 for y in range(125):
  for x in range(125):
   if texture=='uniform':v=(0.,0.,1.)
   elif texture=='near-stop':
    t=5e-6;v=(t,0.,math.sqrt(1-t*t))
   elif texture=='smooth':
    # Deliberately synthetic periodic tilt; compatibility test, not a relaxed skyrmion.
    t=.01*math.cos(2*math.pi*(x+y)/125);v=(t,0.,math.sqrt(1-t*t))
   else:raise ValueError('unknown fixture')
   A.append(v)
 B=[tuple(-q for q in v) for v in A]
 (out/'config.dat').write_text(HEADER+''.join(' '.join(format(q,'.17g') for q in (*a,*b))+'\n' for a,b in zip(A,B)))
 (out/'seed.f64').write_bytes(b''.join(struct.pack('=3d',*v) for sub in [A,B] for v in sub))
 (out/'metadata.json').write_text(json.dumps({'kind':'synthetic '+texture,'shape':[2,1,125,125,3],'storage':'native-endian binary64; A block then B; x fastest','energy_origin':'must be evaluated with fim_inspect; never assumed zero','physical_start_ps':0},indent=2)+'\n')
if __name__=='__main__':
 a=argparse.ArgumentParser();a.add_argument('out',type=Path);a.add_argument('--texture',choices=['uniform','smooth','near-stop'],default='uniform');x=a.parse_args();make(x.out,x.texture)
