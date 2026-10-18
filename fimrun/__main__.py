"""Explicit installation diagnostics; no simulation, download or repair."""
import argparse,json,sys
from pathlib import Path
from .runtime import doctor
p=argparse.ArgumentParser();p.add_argument('command',choices=['doctor']);p.add_argument('--native',action='store_true');p.add_argument('--kernel')
a=p.parse_args()
try:
    report=doctor(native=a.native)
    roots=[Path(sys.prefix)/'share/jupyter/kernels',Path.home()/'Library/Jupyter/kernels']
    specs=[]
    for root in roots:
        for path in sorted(root.glob('*/kernel.json')):
            value=json.loads(path.read_text());argv=value.get('argv',[])
            specs.append(dict(name=path.parent.name,path=str(path),argv=argv,matches_interpreter=bool(argv) and Path(argv[0]).resolve()==Path(sys.executable).resolve()))
    report['executable']=sys.executable;report['kernels']=specs
    if a.kernel and not any(v['name']==a.kernel and v['matches_interpreter'] for v in specs):
        raise RuntimeError('Kernel missing or points to a different interpreter: '+a.kernel)
    print(json.dumps(report,ensure_ascii=False,indent=2))
except Exception as exc:
    print('Installation check failed: '+str(exc)+'; follow the release RECOVERY.md',file=sys.stderr);sys.exit(2)
