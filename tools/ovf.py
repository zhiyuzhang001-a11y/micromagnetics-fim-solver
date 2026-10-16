"""Strict rectangular OVF2 vector reader. No resampling and no private fixtures."""
from pathlib import Path
import re,struct
import numpy as np

def read(path,geometry,Ms,interpretation):
 raw=Path(path).read_bytes()
 if len(raw)>64*1024**2:raise ValueError('OVF input size')
 if not raw.splitlines()[0].lower().startswith(b'# oommf ovf 2.0'):raise ValueError('unsupported OVF version; OVF2 only')
 match=re.search(rb'#\s*Begin:\s*Data\s+(Text|Binary\s+[48])\s*\r?\n',raw,re.I)
 if not match:raise ValueError('unsupported OVF data format')
 head=raw[:match.start()].decode('ascii');meta={k.lower().strip():v.strip().strip('{}') for k,v in re.findall(r'^#\s*([^:\n]+):\s*(.*)$',head,re.M)}
 if meta.get('meshtype','').lower()!='rectangular' or int(meta.get('valuedim','0'))!=3:raise ValueError('OVF rectangular valuedim=3 required')
 if int(meta.get('segment count','1'))!=1:raise ValueError('one OVF segment required')
 if meta.get('meshunit','').lower() not in ['m','nm']:raise ValueError('OVF meshunit m/nm required')
 scale=1e-9 if meta['meshunit'].lower()=='nm' else 1.;n=geometry['n'];h=np.array(geometry['cell_nm'])*1e-9;origin=np.array(geometry['origin_nm'])*1e-9
 for a,key in enumerate('xyz'):
  if int(meta.get(key+'nodes','0'))!=n[a]:raise ValueError('OVF nodes mismatch')
  if not np.isclose(float(meta[key+'stepsize'])*scale,h[a],rtol=1e-12,atol=0):raise ValueError('OVF cell mismatch')
  if not np.isclose(float(meta[key+'base'])*scale,origin[a]+h[a]/2,rtol=1e-12,atol=1e-20):raise ValueError('OVF origin/base mismatch')
 fmt=match.group(1).lower().replace(b' ',b'');start=match.end();count=int(np.prod(n))*3
 if fmt==b'text':
  end=re.search(rb'#\s*End:\s*Data\s+Text',raw[start:],re.I)
  if not end:raise ValueError('OVF text end marker')
  values=np.array([float(q) for q in raw[start:start+end.start()].decode('ascii').split()]);eps=1e-12
 else:
  width=int(fmt[-1:]);sentinel=1234567. if width==4 else 123456789012345.;kind='f' if width==4 else 'd';marker=raw[start:start+width];endian=next((e for e in ['<','>'] if len(marker)==width and struct.unpack(e+kind,marker)[0]==sentinel),None)
  if endian is None:raise ValueError('OVF endian/check value')
  payload=raw[start+width:start+width+count*width]
  if len(payload)!=count*width:raise ValueError('OVF binary truncated')
  values=np.frombuffer(payload,dtype=endian+kind).astype(float);eps=1e-5 if width==4 else 1e-12
  if not re.match(rb'\s*#\s*End:\s*Data\s+Binary\s+[48]',raw[start+width+count*width:],re.I):raise ValueError('OVF binary end marker')
 if len(values)!=count or not np.isfinite(values).all():raise ValueError('OVF values dimension/finite')
 v=values.reshape(n[2],n[1],n[0],3);norm=np.linalg.norm(v,axis=-1)
 if np.any(norm==0):raise ValueError('OVF zero vector')
 units=meta.get('valueunits','').split()
 if interpretation=='magnetization_Apm':
  if not units or any(x!='A/m' for x in units) or np.max(np.abs(norm/Ms-1))>eps:raise ValueError('OVF A/m units or Ms magnitude mismatch')
 elif not units or any(x not in ['1','A/m','none'] for x in units):raise ValueError('unsupported OVF valueunits')
 return v/norm[...,None],{'format':fmt.decode(),'input_units':units,'norm_min':float(norm.min()),'norm_max':float(norm.max()),'normalization':'explicit direction extraction','interpretation':interpretation,'relative_magnitude_tolerance':eps,'original_sha256':__import__('hashlib').sha256(raw).hexdigest()}
