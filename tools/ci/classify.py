"""Small edits get quick checks; physics/state/output safety gets full regression."""
from pathlib import Path
import os,subprocess,json
base=os.environ.get('CI_BASE','');full=os.environ.get('CI_FULL','false')=='true'
try:files=subprocess.check_output(['git','diff','--name-only',base,'HEAD'],text=True).splitlines() if base and set(base)!={'0'} else ['.github/workflows/verify.yml']
except subprocess.CalledProcessError:files=['.github/workflows/verify.yml']
quick_only=('fimrun/postprocess/analysis.py','fimrun/micromagnetics/viewer/','docs/','README.md','CITATION.cff','LICENSE','COPYING','NOTICE','LICENSES/')
for f in files:
 if f.endswith('.ipynb'):
  try:
   old=json.loads(subprocess.check_output(['git','show',base+':'+f],text=True));new=json.loads(Path(f).read_text());full|=[c['source'] for c in old['cells'] if c['cell_type']=='code']!=[c['source'] for c in new['cells'] if c['cell_type']=='code']
  except Exception:full=True
 elif not any(f==x or x.endswith('/') and f.startswith(x) for x in quick_only):full=True
browser=full or any(f.startswith('fimrun/micromagnetics/viewer/') or f.endswith(('.cjs','.mjs')) for f in files)
with open(os.environ['GITHUB_OUTPUT'],'a') as out:out.write('full='+str(full).lower()+'\nbrowser='+str(browser).lower()+'\n')
print(json.dumps(dict(full=full,changed_files=files)))
