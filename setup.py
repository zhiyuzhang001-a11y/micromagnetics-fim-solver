"""Platform wheel built only from explicitly prepared and hash-bound payloads."""
from pathlib import Path
from setuptools import setup,find_packages
from wheel.bdist_wheel import bdist_wheel
import json,hashlib
ROOT=Path(__file__).parent;PKG=ROOT/'fimrun'
class QualifiedWheel(bdist_wheel):
    def finalize_options(self):super().finalize_options();self.root_is_pure=False
    def get_tag(self):return 'py3','none','macosx_27_0_arm64'
info=json.loads((PKG/'_build_info.json').read_text())
for rel,expected in info['payload_manifest'].items():
    p=PKG/rel
    if not p.is_file() or hashlib.sha256(p.read_bytes()).hexdigest()!=expected:raise RuntimeError('unprepared or changed runtime payload: '+rel)
data=[str(p.relative_to(PKG)) for p in PKG.rglob('*') if p.is_file() and p.suffix not in ('.py','.pyc') and '__pycache__' not in p.parts]
setup(packages=find_packages(include=['fimrun','fimrun.*']),package_data={'fimrun':data},include_package_data=True,cmdclass={'bdist_wheel':QualifiedWheel})
