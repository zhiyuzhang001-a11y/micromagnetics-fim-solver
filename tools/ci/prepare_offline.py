"""Source-only zero-field CI identity; no binaries, installation or qualification."""
from pathlib import Path
import hashlib,json,shutil,subprocess
root=Path(__file__).resolve().parents[2];pkg=root/'fimrun';runtime=pkg/'_runtime'
assert not runtime.exists(),'Use a clean disposable checkout'
for name in ('src','validation/fm'):
 shutil.copytree(root/name,runtime/name)
(runtime/'examples').mkdir();shutil.copy2(root/'examples/kernel125-mirror10.f64',runtime/'examples/kernel125-mirror10.f64')
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
info=dict(schema='source-only-zero-field-ci',test_only=True,source_tree_dirty=False,source_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip(),source_manifest={str(p.relative_to(root)):sha(p) for p in sorted(pkg.rglob('*.py')) if '_runtime' not in p.parts},payload_manifest={str(p.relative_to(pkg)):sha(p) for p in runtime.rglob('*') if p.is_file()})
info['payload_manifest']['postprocess/calibration_v1.json']=sha(pkg/'postprocess/calibration_v1.json')
(pkg/'_build_info.json').write_text(json.dumps(info,indent=2)+'\n')
print('Source-only identity; Native construction/evaluation forbidden by quick runner; not a release')
