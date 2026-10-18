"""Offline restoration; archive-relative, no source checkout dependency."""
from pathlib import Path
import argparse,hashlib,json,os,subprocess,sys
p=argparse.ArgumentParser();p.add_argument('--branch',choices=['A','B'],required=True);p.add_argument('--prefix',type=Path,required=True);p.add_argument('--work',type=Path,required=True);p.add_argument('--manager',type=Path);p.add_argument('--kernel',required=True);p.add_argument('--bootstrap-prefix',type=Path,help='Internal shell entry: verified archived bootstrap already installed');a=p.parse_args()
r=Path(__file__).resolve().parent;prefix=a.prefix.resolve();work=a.work.resolve()
if prefix.exists() or work.exists():raise SystemExit('Refusing existing prefix/work directory')
for rel,digest in json.loads((r/'SHA256_MANIFEST.json').read_text()).items():
 if hashlib.sha256((r/rel).read_bytes()).hexdigest()!=digest:raise SystemExit('Archive SHA mismatch: '+rel)
work.mkdir(parents=True)
env={k:v for k,v in os.environ.items() if not (k.startswith(('CONDA','MAMBA','PYTHON','PIP','DYLD')))}
env.update(PATH='/usr/bin:/bin:/usr/sbin:/sbin',PYTHONNOUSERSITE='1',PYTHONDONTWRITEBYTECODE='1',CONDA_PKGS_DIRS=str(work/'conda-cache'),CONDA_ENVS_PATH=str(work/'envs'),PIP_CACHE_DIR=str(work/'pip-cache'),FIMRUN_CACHE_DIR=str(work/'fimrun-cache'),CONDA_OFFLINE='true',CONDA_NO_PLUGINS='true')
config=work/'condarc';config.write_text('offline: true\nchannels: []\nsolver: classic\nnotify_outdated_conda: false\n');env['CONDARC']=str(config)
if a.bootstrap_prefix is not None and a.branch!='B':raise SystemExit('--bootstrap-prefix is only valid for branch B')
if a.branch=='B' and a.bootstrap_prefix is not None:
 manager=a.bootstrap_prefix.resolve()
 if Path(sys.prefix).resolve()!=manager or not (manager/'conda-meta').is_dir():raise SystemExit('Branch B must run with its archived bootstrap interpreter')
elif a.branch=='B':
 manager=work/'bootstrap';installer=next((r/'bootstrap').glob('*.sh'))
 bootstrap_env=dict(env);bootstrap_env.pop('CONDA_NO_PLUGINS',None)
 subprocess.run(['/bin/bash',str(installer),'-b','-m','-p',str(manager)],env=bootstrap_env,check=True)
else:
 if a.manager is None:raise SystemExit('Branch A requires explicit --manager')
 manager=a.manager.resolve()
packages=json.loads((r/'CONDA_ARCHIVES.json').read_text());spec=work/'local-explicit.txt';spec.write_text('@EXPLICIT\n'+''.join((r/'conda'/v['fn']).as_uri()+'#'+v['sha256']+'\n' for v in packages))
# Restrict all context reinitializations to our one owned config; do not edit Conda files.
code="""import sys
import conda.base.constants as c
c.SEARCH_PATH=(sys.argv[1],)
import conda.base.context as x
x.SEARCH_PATH=(sys.argv[1],)
x.reset_context(search_path=(sys.argv[1],))
import conda
assert conda.__version__ in ('25.9.0','25.9.1'), conda.__version__
from conda.misc import explicit
with open(sys.argv[3]) as stream:
    explicit([line.strip() for line in stream if line.strip() and not line.startswith('#')], sys.argv[2])
"""
subprocess.run([str(manager/'bin/python'),'-I','-c',code,str(config),str(prefix),str(spec)],env=env,check=True)
python=str(prefix/'bin/python');wheel=next((r/'wheel').glob('*.whl'))
subprocess.run([python,'-I','-m','pip','install','--no-index','--no-deps','--no-cache-dir',str(wheel)],env=env,check=True)
subprocess.run([python,'-I','-m','pip','check'],env=env,check=True)
subprocess.run([python,'-I','-m','ipykernel','install','--prefix',str(prefix),'--name',a.kernel,'--display-name','Python ('+a.kernel+')'],env=env,check=True)
subprocess.run([python,'-I','-m','fimrun','doctor','--native'],env=env,check=True)
(work/'RESTORED.json').write_text(json.dumps({'status':'installed_pending_scientific_checks','branch':a.branch,'prefix':str(prefix),'manager':str(manager),'config_search':[str(config)],'archives':len(packages),'kernel':a.kernel,'bootstrap_prefix':str(a.bootstrap_prefix) if a.bootstrap_prefix is not None else None,'driver_python':sys.executable,'fields':0},indent=2)+'\n')
