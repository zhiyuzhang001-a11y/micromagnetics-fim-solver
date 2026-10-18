"""Installed payload identity and writable cache; never discovers a checkout."""
from pathlib import Path
import hashlib,json,os,platform,sys
from ._version import __version__
PACKAGE_ROOT=Path(__file__).resolve().parent
RESOURCE_ROOT=PACKAGE_ROOT/'_runtime'
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def canonical(x):return json.dumps(x,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode()
def source_files():return {str(p.relative_to(PACKAGE_ROOT.parent)):p for p in sorted(PACKAGE_ROOT.rglob('*.py')) if '_runtime' not in p.parts}
_IMPORT_SNAPSHOT={k:sha(p) for k,p in source_files().items()}
def build_info():
    path=PACKAGE_ROOT/'_build_info.json'
    if not path.is_file():raise RuntimeError('Package build manifest missing. Install the verified wheel; see RECOVERY.md.')
    return json.loads(path.read_text())
def ensure_integrity():
    actual={k:sha(p) for k,p in source_files().items()}
    if actual!=_IMPORT_SNAPSHOT:raise RuntimeError('Package changed in this kernel. Select a fresh kernel; do not reload a running simulation.')
    info=build_info()
    if actual!=info['source_manifest']:raise RuntimeError('Installed Python files differ from the build manifest. Run python -m fimrun doctor; restore the verified wheel.')
    for rel,expected in info['payload_manifest'].items():
        p=PACKAGE_ROOT/rel
        if not p.is_file() or sha(p)!=expected:raise RuntimeError('Installed resource missing or changed: '+rel+'; see RECOVERY.md')
    return info

def cache_dir():
    path=Path(os.environ.get('FIMRUN_CACHE_DIR',str(Path.home()/'Library/Caches/fimrun'))).expanduser().absolute()
    if path==PACKAGE_ROOT or PACKAGE_ROOT in path.parents:raise ValueError('cache must be outside the installed package')
    return path

def identity():
    info=ensure_integrity();sources={k:sha(p) for k,p in source_files().items()}
    return dict(version=__version__,commit=info['source_commit'],dirty=None,vcs_status='not_queried',source_manifest_matches_build=True,build_source_tree_dirty=info['source_tree_dirty'],
        source_manifest=sources,source_manifest_sha256=hashlib.sha256(canonical(sources)).hexdigest(),
        build_manifest_sha256=sha(PACKAGE_ROOT/'_build_info.json'),serialization='analysis-json-v1',python=sys.version.split()[0])

def doctor(*,native=False):
    info=ensure_integrity();import numpy as np
    arch=platform.machine();os_version=platform.mac_ver()[0]
    if sys.platform!='darwin' or arch!='arm64' or not os_version.startswith('27.'):
        raise RuntimeError('This release is qualified for macOS 27 arm64 only; see RECOVERY.md')
    if sys.version_info[:3]!=(3,12,14) or np.__version__!='2.3.5':raise RuntimeError('Wrong Python/NumPy version; select the micromagnetics kernel or restore its environment.')
    report=dict(status='passed',package_version=__version__,prefix=sys.prefix,package_path=str(PACKAGE_ROOT),
       python=platform.python_version(),numpy=np.__version__,platform=sys.platform,architecture=arch,macOS=os_version,
       source_commit=info['source_commit'],source_manifest_sha256=identity()['source_manifest_sha256'],
       cache=str(cache_dir()),native_probe=native,fields=0,visual_inspection=False)
    if native:
        import ctypes
        for name in ('fm','fim'):ctypes.CDLL(str(RESOURCE_ROOT/'build-script-api'/('lib'+name+'.dylib')))
        builder=RESOURCE_ROOT/'build-script-api/kernel_builder'
        if not os.access(builder,os.X_OK):raise RuntimeError('Kernel builder is not executable')
        report['native_loads']='FM/FiM loaded without creating any Model'
    return report
