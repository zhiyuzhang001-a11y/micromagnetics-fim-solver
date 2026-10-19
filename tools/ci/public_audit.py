"""Static public-tree audit. Reports locations, never candidate secret values."""
from pathlib import Path
import json,re,subprocess
root=Path(__file__).resolve().parents[2]
files=subprocess.check_output(['git','ls-files'],cwd=root,text=True).splitlines();issues=[]
patterns=[('private-key',r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----'),('github-token',r'(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,})'),('aws-key',r'AKIA[0-9A-Z]{16}')]
for name in files:
 p=root/name
 if not p.exists():continue
 if p.suffix in ('.state','.ovf','.npz','.pem','.key','.bundle','.whl') or p.name.startswith('.env'):issues.append((name,'private/generated payload not authorized'))
 raw=p.read_bytes()
 if b'\0' in raw:continue
 text=raw.decode('utf8','replace')
 for label,pattern in patterns:
  if re.search(pattern,text):issues.append((name,label))
 if '/Users/'+'zhiyu' in text:issues.append((name,'private workstation path'))
 if name.endswith('.py'):compile(text,name,'exec')
 if name.endswith('.ipynb'):
  nb=json.loads(text)
  for cell in nb['cells']:
   if cell['cell_type']=='code':
    assert not cell.get('outputs'),name
    compile(''.join(cell['source']),name,'exec')
licenses={r['path'] for r in json.loads((root/'docs/FILE_LICENSE_MAP.json').read_text())}
issues += [(n,'missing file license mapping') for n in files if (root/n).exists() and n not in licenses]
if issues:raise SystemExit(json.dumps(issues,indent=2))
print(json.dumps(dict(status='passed',tracked_files=len(files),secret_signatures=0,notebook_outputs=0,license_map_complete=True)))
