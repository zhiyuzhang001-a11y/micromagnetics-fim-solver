"""Prepare identity only in a disposable SOURCE candidate for offline tests.

No native payload, environment installation, or release qualification is implied.
Never use this manifest to replace the verified installed package.
"""
import hashlib
import json
import subprocess
from pathlib import Path
root = Path(__file__).resolve().parents[1]
pkg = root/'fimrun'
if (pkg/'_runtime').exists():
    raise SystemExit('Refusing a payload-bearing tree; use a disposable source clone')
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
info = {'source_commit': subprocess.check_output(['git','rev-parse','HEAD'], cwd=root, text=True).strip(),
        'source_tree_dirty': True, 'test_only': True,
        'source_manifest': {str(p.relative_to(root)): sha(p) for p in sorted(pkg.rglob('*.py'))},
        'payload_manifest': {'postprocess/calibration_v1.json': sha(pkg/'postprocess/calibration_v1.json')}}
(pkg/'_build_info.json').write_text(json.dumps(info, sort_keys=True, indent=2)+'\n')
print('Source-only offline test identity prepared; native payload absent; not an installed release')
