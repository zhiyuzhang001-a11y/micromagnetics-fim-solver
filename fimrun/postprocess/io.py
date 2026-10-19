"""Read-only OVF/state provenance. No native engine or pickle loading."""
from .session import read_bytes, parsed
import hashlib,importlib.util,io,json,re,struct,subprocess,sys,zipfile
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[2]
VERSION='skyrmion-offline-1'

def sha(path):return hashlib.sha256(read_bytes(path)).hexdigest()
def canonical(value):return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode()
def content_sha(value):return hashlib.sha256(canonical(value)).hexdigest()
from ..runtime import PACKAGE_ROOT, identity as _installed_identity
_SOURCE_AT_IMPORT={str(p.relative_to(ROOT)):sha(p) for p in list(Path(__file__).parent.glob('*.py'))+[PACKAGE_ROOT/'_support/ovf.py',PACKAGE_ROOT/'_support/contour_geometry.py']}

def tool(name):
    if name not in ('ovf','contour_geometry'):raise ValueError('unknown postprocessing helper')
    path=PACKAGE_ROOT/'_support'/(name+'.py')
    if sha(path)!=_SOURCE_AT_IMPORT[str(path.relative_to(ROOT))]:raise RuntimeError('postprocessing source changed; select a fresh kernel')
    return __import__('importlib').import_module('fimrun._support.'+name)


def read_ovf(path,*,Ms=None,legacy=None):
    path=Path(path).resolve();raw=read_bytes(path);match=re.search(rb'#\s*Begin:\s*Data\s+(?:Text|Binary\s+[48])\s*\r?\n',raw,re.I)
    if not match:raise ValueError('unsupported OVF data')
    header=tool('ovf').parse_header(raw[:match.start()].decode('ascii'))
    scale={'m':1.,'nm':1e-9}.get(header.get('meshunit','').lower())
    if scale is None:raise ValueError('unknown meshunit')
    cells=tuple(int(header[a+'nodes']) for a in 'xyz');h=np.array([float(header[a+'stepsize'])*scale for a in 'xyz']);overrides={}
    if legacy and 'origin_m' in legacy:
        for j,a in enumerate('xyz'):
            if a+'base' not in header:overrides[a+'base']=(float(legacy['origin_m'][j])+h[j]/2)/scale
    if 'valueunits' not in header and legacy and legacy.get('quantity') in ('unit_direction','magnetization_Apm'):
        overrides['valueunits']='1 1 1' if legacy['quantity']=='unit_direction' else 'A/m A/m A/m'
    header.update({k:str(v) for k,v in overrides.items()})
    base=np.array([float(header[a+'base'])*scale for a in 'xyz']);origin=base-h/2
    if cells[2]!=1 or min(cells)<1 or not np.isfinite(h).all() or (h<=0).any() or not np.isfinite(origin).all():raise ValueError('only finite rectangular single-layer inputs supported')
    for j,a in enumerate('xyz'):
        for suffix,expected in (('min',origin[j]),('max',origin[j]+cells[j]*h[j])):
            if a+suffix in header and not np.isclose(float(header[a+suffix])*scale,expected,rtol=1e-12,atol=1e-20):raise ValueError('OVF bounding box conflict')
    fields=header['desc_fields'];units=header.get('valueunits','').split()
    if 'Ms_Apm' in fields and Ms is not None and float(fields['Ms_Apm'])!=float(Ms):raise ValueError('OVF/state or mapping Ms conflict')
    if units==['1'] or units==['1','1','1']:interpretation='direction';ms=1.
    elif units==['A/m'] or units==['A/m']*3:
        ms=float(fields.get('Ms_Apm',Ms)) if fields.get('Ms_Apm',Ms) is not None else None
        if ms is None or not np.isfinite(ms) or ms<=0:raise ValueError('A/m OVF requires own positive Ms')
        interpretation='magnetization_Apm'
    else:raise ValueError('ambiguous OVF value units')
    if fields.get('quantity') not in (None,'unit_direction' if interpretation=='direction' else 'magnetization_Apm'):raise ValueError('OVF quantity/units conflict')
    geometry={'n':list(cells),'cell_nm':(h*1e9).tolist(),'origin_nm':(origin*1e9).tolist()}
    tolerance=None
    if legacy and legacy.get('normalization_roundoff')=='binary32-gamma12':
        # Explicit finite-precision assumption, NEVER inferred from .ovf or width8.
        # Only exact binary32 component values in a binary8 container qualify.
        if b'binary 8' not in match.group().lower():raise ValueError('binary32 provenance check requires binary8 container')
        marker=raw[match.end():match.end()+8]
        endian=next((e for e in ('<','>') if len(marker)==8 and struct.unpack(e+'d',marker)[0]==123456789012345.),None)
        if endian is None:raise ValueError('OVF endian/check value')
        values=np.frombuffer(raw[match.end()+8:match.end()+8+int(np.prod(cells))*24],dtype=endian+'f8')
        if not np.array_equal(values,values.astype('f4').astype('f8')):raise ValueError('components are not exact binary32 values')
        u=np.finfo(np.float32).eps/2;tolerance=12*u/(1-12*u)
    m,report=tool('ovf').read_bytes(raw,geometry,ms,interpretation,header_overrides=overrides,magnitude_tolerance=tolerance)
    report['roundoff_assumption']=legacy.get('normalization_roundoff') if legacy else None
    report['roundoff_assumption_scope']='explicit gamma12 binary32 operation envelope, not proof of original arithmetic or physical Ms accuracy' if tolerance else 'storage precision only'
    # Direction data must already be unit length up to storage roundoff.
    eps=report['relative_magnitude_tolerance'];expected=ms if interpretation=='magnetization_Apm' else 1.
    if max(abs(report['norm_min']/expected-1),abs(report['norm_max']/expected-1))>eps:raise ValueError('unresolved vector normalization; refusing silent repair')
    label=fields.get('sublattice');title=header.get('title','')
    if label is None and title.startswith('magnetization_direction_'):label=title.removeprefix('magnetization_direction_')
    legacy=[key for key in ['valuelabels','xmin','ymin','zmin','xmax','ymax','zmax'] if key not in header]
    return dict(path=str(path),sha256=hashlib.sha256(raw).hexdigest(),m=m[0],cells=cells,h=h,origin=origin,fields=fields,label=label,legacy_missing_header=legacy,normalization=report,legacy_header_overrides=overrides)

def _read_state(path):
    path=Path(path).resolve()
    raw=read_bytes(path)
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        body=z.read('manifest.json')
        if hashlib.sha256(body).hexdigest()!=z.read('manifest.sha256').decode():raise ValueError('state manifest checksum mismatch')
        value=json.loads(body)
        if value.get('schema')!='micromagnetics-state-v1' or value.get('version')!=1:raise ValueError('unsupported state metadata schema/version')
    return value,dict(path=str(path),sha256=hashlib.sha256(raw).hexdigest(),member='manifest.json',member_sha256=hashlib.sha256(body).hexdigest())

def implementation():
    for rel,expected in _SOURCE_AT_IMPORT.items():
        if sha(ROOT/rel)!=expected:raise RuntimeError('postprocessing source changed; select a fresh kernel')
    return _installed_identity()


def read_state(path):
    return parsed(path, "state", lambda: _read_state(path))
