"""Strict rectangular OVF2 vector reader. No resampling and no private fixtures."""
from pathlib import Path
import re,struct
import numpy as np

def parse_header(head):
 """OVF permits repeated Desc. Preserve text; parse only known metadata keys."""
 records=re.findall(r'^#[ \t]*([^:\r\n]+):[ \t]*(.*)$',head,re.M)
 meta={};descriptions=[];fields={}
 recognized={'time_s','stage','accepted_index','sublattice','run_id','segment_id',
             'boundary','mirrors','quantity','Ms_Apm','boris_metadata_version'}
 for key,value in records:
  key=key.lower().strip();value=value.strip().strip('{}')
  if key in ('begin','end'):continue
  if key=='desc':
   descriptions.append(value)
   for token in value.split(';'):
    if '=' not in token:continue
    name,val=(x.strip() for x in token.split('=',1))
    if name not in recognized:continue
    if name in fields and fields[name]!=val:raise ValueError('conflicting Desc metadata: '+name)
    fields[name]=val
  elif key in meta and meta[key]!=value:raise ValueError('conflicting OVF header: '+key)
  else:meta[key]=value
 meta['descriptions']=descriptions;meta['desc_fields']=fields
 return meta

def read(path,geometry,Ms,interpretation,*,header_overrides=None,magnitude_tolerance=None):
 from ..capacity import require_memory
 require_memory(4*Path(path).stat().st_size,'OVF read capacity')
 return read_bytes(Path(path).read_bytes(),geometry,Ms,interpretation,header_overrides=header_overrides,magnitude_tolerance=magnitude_tolerance)

def read_bytes(raw,geometry,Ms,interpretation,*,header_overrides=None,magnitude_tolerance=None):
 """Parse one immutable byte snapshot, including its provenance hash."""
 from ..capacity import require_memory
 require_memory(4*len(raw),'OVF parse capacity')
 if not raw or not raw.splitlines()[0].lower().startswith(b'# oommf ovf 2.0'):raise ValueError('unsupported OVF version; OVF2 only')
 match=re.search(rb'#\s*Begin:\s*Data\s+(Text|Binary\s+[48])\s*\r?\n',raw,re.I)
 if not match:raise ValueError('unsupported OVF data format')
 head=raw[:match.start()].decode('ascii');meta=parse_header(head)
 for key,value in (header_overrides or {}).items():
  if key in meta and meta[key]!=str(value):raise ValueError('header override conflicts: '+key)
  meta[key]=str(value)
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
 if magnitude_tolerance is not None:
  if not np.isfinite(magnitude_tolerance) or magnitude_tolerance<=0:raise ValueError('invalid explicit magnitude tolerance')
  eps=max(eps,float(magnitude_tolerance))
 units=meta.get('valueunits','').split()
 if interpretation=='magnetization_Apm':
  if not units or any(x!='A/m' for x in units) or np.max(np.abs(norm/Ms-1))>eps:raise ValueError('OVF A/m units or Ms magnitude mismatch')
 elif not units or any(x not in ['1','A/m','none'] for x in units):raise ValueError('unsupported OVF valueunits')
 return v/norm[...,None],{'descriptions':meta['descriptions'],'desc_fields':meta['desc_fields'],'format':fmt.decode(),'input_units':units,'norm_min':float(norm.min()),'norm_max':float(norm.max()),'normalization':'explicit direction extraction','interpretation':interpretation,'relative_magnitude_tolerance':eps,'original_sha256':__import__('hashlib').sha256(raw).hexdigest()}
