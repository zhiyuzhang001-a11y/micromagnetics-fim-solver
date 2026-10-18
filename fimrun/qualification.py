"""Read-only binding checks around the existing scientific success predicates."""
from pathlib import Path
import fcntl
import os
import math
from copy import deepcopy
from .bridge import legacy, ROOT
from .protocol import read, sha

CANONICAL_SHA='db71f379e2bea728a475d9e0c6e5e1183c7830ee1ba91e6909f84c532ec012b6'

def canonical_geometry(case):
    g=case['geometry']
    return g['n']==[125,125,1] and g['cell_nm']==[4,4,3] and g['pbc']==[1,1,0] and g['mirrors']==[10,10]

def reference_record(case,meta):
    """Inspect existing evidence using the original cache writer's gates, never rerun it."""
    v=meta.get('verification',{})
    if not isinstance(v,dict) or ('passed' in v and v['passed'] is not True) or ('status' in v and v['status'] not in ('passed','success','qualified')) or v.get('failure_detail'):
        raise ValueError('kernel qualification explicitly failed/missing')
    def bounded(value,limit,label):
        if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value) or not 0<=value<=limit:
            raise ValueError('kernel qualification '+label+' missing/nonfinite/outside original gate')
    bounded(v.get('reciprocity_max'),1e-12,'reciprocity_max')
    if v.get('coverage')!='tensor samples and effective zero block; full-kernel finite/reciprocity': raise ValueError('kernel qualification coverage missing')
    rows=v.get('reference_samples')
    if not isinstance(rows,list): raise ValueError('kernel qualification reference_samples missing')
    for row in rows:
        if not isinstance(row,dict) or any(type(row.get(k)) is not int for k in ('i','j')): raise ValueError('kernel qualification sample coordinates missing')
        bounded(row.get('error'),1e-10,'sample.error')
        bounded(row.get('reference_precision_drift'),1e-12,'sample.reference_precision_drift')
    known=canonical_geometry(case) and meta['payload_sha256']==CANONICAL_SHA and meta.get('source')=='bundled-qualified-canonical'
    if known and not rows:
        if not isinstance(v.get('historical_reference'),str) or not v['historical_reference'] or type(v.get('reference_tensor_evaluations')) is not int or v['reference_tensor_evaluations']!=0 or 'engineering_reference_error' not in v:
            raise ValueError('canonical kernel qualification record incomplete')
        if v.get('engineering_reference_error') is not None: bounded(v['engineering_reference_error'],1e-10,'engineering_reference_error')
    else:
        if not rows: raise ValueError('kernel qualification reference_samples empty')
        bounded(v.get('engineering_reference_error'),1e-10,'engineering_reference_error')
        if v['engineering_reference_error']<max(r['error'] for r in rows): raise ValueError('kernel reference aggregate below sample error')
        g=case['geometry']; expected=2*len(rows)+(math.prod(2*m+1 for m in g['mirrors']) if g['pbc'][0] else 1)
        if type(v.get('reference_tensor_evaluations')) is not int or v['reference_tensor_evaluations']!=expected:
            raise ValueError('kernel qualification reference count/zero-block coverage')
        if v.get('coverage')!='tensor samples and effective zero block; full-kernel finite/reciprocity': raise ValueError('kernel qualification coverage missing')
        if meta.get('source')=='MPFR128-Newell/BORIS-asymptotic':
            pass # actual key/source digest already bound to current generator source by key_data
        elif meta.get('source')=='qualified-isolated-G1-import':
            # The existing reviewed no-map import has a distinct actual generator identity.
            # Keep that provenance explicit; a historical_reference string cannot replace it.
            if not (g['n']==[250,250,1] and g['cell_nm']==[2,2,3] and g['pbc']==[1,1,0] and g['mirrors']==[10,10]
                    and meta['payload_sha256']=='fa09e930ac483924fb35491c96319721cc68c9adc7f71d1866a2b4f3d9f6784e'
                    and meta.get('not_generated_by_current_builder') is True and meta.get('qualified_new_geometry') is True
                    and meta.get('actual_generator_source_sha256')=='5a403df25f390f165b9c9a1a9cf8583eebb24aaa4cf482551adc41a528272b78'
                    and meta.get('actual_generator_binary_sha256')=='275f984740a98b1b5e6c3641df3aff16a6e0ce0b51b8b832c2d89dd0e0014284'):
                raise ValueError('kernel isolated import provenance not recognized')
            regression=read(meta['same_implementation_125_regression'])
            if regression.get('status')!='SAME_IMPLEMENTATION_MAP_REMOVAL_BYTE_REGRESSION_PASSED' or regression.get('payload_byte_identical') is not True or regression.get('samples_byte_identical') is not True:
                raise ValueError('kernel isolated import source regression failed')
        elif not known:
            raise ValueError('kernel qualification source not recognized')
    return deepcopy(meta)

def ledger_snapshot(path, floor=0):
    b = legacy()['user_costs']
    with Path(path).open() as stream:
        fcntl.flock(stream, fcntl.LOCK_SH)
        events = b.read_events(stream)
    if not events: raise ValueError('empty resource ledger; cannot reset')
    pending = set()
    for e in events:
        if e['kind'] == 'reserve':
            if e['reservation'] in pending: raise ValueError('duplicate reservation')
            pending.add(e['reservation'])
        elif e['kind'] == 'settle': pending.discard(e['reservation'])
    total = b.total(events)
    if total < floor: raise ValueError('resource ledger regressed below checkpoint')
    if pending: raise ValueError('unfinished resource reservation; reconcile, never reset')
    return total

def lineage(meta):
    if meta.get('resource_ledger'):
        p = Path(meta['resource_ledger']).resolve()
        return p, ledger_snapshot(p, meta['spent_fields'])
    source, seed = legacy()['user_costs'].legacy_source_cost(meta)
    p = source.with_name(source.name + '.resource-costs.jsonl')
    return p, ledger_snapshot(p, seed) if p.exists() else seed

def kernel_binding(case):
    b = legacy(); kc = b['kernel_cache']; uc = b['user_case']
    key = kc.key_data(case)
    folder = Path(case['output']['cache']) / uc.digest(key)
    if folder.exists():
        meta = read(folder / 'manifest.json'); payload = folder / 'kernel.f64'
        if meta['key'] != key or sha(payload) != meta['payload_sha256']: raise ValueError('kernel cache checksum/identity')
        meta=reference_record(case,meta)
        evidence={str((folder/'manifest.json').resolve()):sha(folder/'manifest.json')}
        if meta.get('source')=='qualified-isolated-G1-import':
            p=Path(meta['same_implementation_125_regression']).resolve();evidence[str(p)]=sha(p)
    else:
        if not canonical_geometry(case):
            raise ValueError('runtime.cache: verified geometry-bound kernel required; automatic generation disabled')
        payload = ROOT / 'examples/kernel125-mirror10.f64'
        if sha(payload) != CANONICAL_SHA: raise ValueError('bundled kernel hash')
        v=kc.validate_kernel(case,payload,samples=None)
        v['historical_reference']='qualified canonical finite mirror10 kernel; original bytes retained'
        meta={'key':key,'payload_sha256':CANONICAL_SHA,'verification':v,'source':'bundled-qualified-canonical'}
        evidence={}
    kc.validate_kernel(case, payload, samples=None)
    return {'path': str(payload.resolve()), 'sha256': sha(payload),'qualification':meta,'evidence_bindings':evidence}

def qualified(report_path, target, kernel_hash):
    """No Model/evaluate. Reuse requirements_met and native CP direction parser."""
    b = legacy(); p = Path(report_path).resolve(); out = p.parent
    r = read(p)
    check=r.get('static_criterion',{}).get('independent',{})
    if r.get('execution_completed') is not True or r.get('mandatory_outputs_written') is not True or check.get('passed') is not True or check.get('static_criterion_met') is not True or not b['run_user_workflow'].requirements_met(r):
        raise ValueError('prepared.report: preparation scientific/output/goal gates not met')
    cp = out / 'static/checkpoint.bin'; md = Path(str(cp) + '.json')
    if Path(r['final_checkpoint']).resolve() != cp.resolve() or Path(r['final_checkpoint_metadata']).resolve() != md.resolve():
        raise ValueError('prepared.report: final checkpoint path not bound to static output')
    if not cp.resolve().is_relative_to(out) or not md.resolve().is_relative_to(out): raise ValueError('prepared checkpoint symlink escapes source')
    c = read(out / 'resolved_case.json'); manifest = read(out / 'manifest.json'); km = read(out / 'kernel.json')
    physics={'geometry':c['geometry'],'material':c['material'],'field':c['field']['H_Apm']}
    if b['user_case'].digest(physics)!=c['physics_sha256'] or b['user_case'].digest({'physics':physics,'dt_fs':c['dynamic']['dt_fs'],'schema':c['schema']})!=c['identity']:
        raise ValueError('prepared resolved physics/numerical identity invalid')
    _, meta = b['current_case'].cp_directions(cp, target, md)
    binary = Path(c['output']['bins']) / 'fim_user'
    if meta.get('schema') != 'user-checkpoint-v1' or meta.get('phase') != 'static': raise ValueError('prepared checkpoint must be static user checkpoint')
    if meta['identity'] != c['identity'] or manifest['identity'] != c['identity'] or c['physics_sha256'] != target['physics_sha256'] or manifest['physics_sha256'] != target['physics_sha256']:
        raise ValueError('prepared physics/config identity mismatch')
    if meta['binary_sha256'] != sha(binary) or manifest['binary_sha256'] != meta['binary_sha256']:
        raise ValueError('prepared source binary hash mismatch')
    if meta['kernel_sha256'] != kernel_hash or km['payload_sha256'] != kernel_hash: raise ValueError('prepared kernel binding mismatch')
    if manifest.get('user_config') != c: raise ValueError('prepared resolved configuration mismatch')
    if bool(r.get('resource_ledger'))!=bool(meta.get('resource_ledger')) or r.get('resource_ledger') and Path(r['resource_ledger']).resolve()!=Path(meta['resource_ledger']).resolve(): raise ValueError('source report/CP ledger mismatch')
    path, total = lineage(meta)
    if total < r.get('started_fields', 0): raise ValueError('ledger regressed below source report')
    files = [p, cp, md, out/'resolved_case.json', out/'manifest.json', out/'kernel.json', binary]
    return {'checkpoint': str(cp.resolve()), 'metadata': str(md.resolve()), 'ledger': str(path),
            'spent': total, 'bindings': {str(f.resolve()): sha(f) for f in files}}

def verify_bindings(bindings):
    for p, expected in bindings.items():
        if sha(p) != expected: raise ValueError(f'input changed since preflight: {p}')

class LineageLock:
    """Advisory exclusion among unified runners; no ledger costs added here."""
    def __init__(self, path): self.path = Path(str(path) + '.runner.lock'); self.stream = None
    def __enter__(self):
        self.stream = self.path.open('a+')
        try: fcntl.flock(self.stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            self.stream.close(); raise ValueError('resource lineage busy in another runner') from None
        return self
    def __exit__(self, *args): self.stream.close()
