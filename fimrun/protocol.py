"""Small shared manifest contract; no process or filesystem writes on import."""
import hashlib
import json
from pathlib import Path
from copy import deepcopy

FORMAT = 'paired-f64-le-2-z-y-x-xyz-v1'
STAGES = {'prepare_dynamic': ('prepare', 'prepare/dynamic'),
          'prepare_static': ('prepare', 'prepare/static'), 'drive': ('drive', 'drive/driven')}

def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False,
                      allow_nan=False).encode('utf-8')

def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()

def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''): h.update(block)
    return h.hexdigest()

def read(path):
    def pairs(items):
        out = {}
        for key, value in items:
            if key in out: raise ValueError(f'duplicate JSON key: {key}')
            out[key] = value
        return out
    return json.loads(Path(path).read_text(), object_pairs_hook=pairs,
                      parse_constant=lambda x: (_ for _ in ()).throw(ValueError(x)))

def config_hash(case):
    value = deepcopy(case)
    value.pop('resources', None)
    for key in ('directory', 'cache', 'bins'): value['output'].pop(key, None)
    return digest(value)

def atomic(path, value):
    p = Path(path)
    tmp = p.with_name(p.name + '.tmp')
    tmp.write_bytes(canonical(value) + b'\n')
    tmp.replace(p)

def inside(root, relative):
    if not isinstance(relative, str) or not relative or any(x in ('', '.', '..') for x in relative.split('/')) or Path(relative).is_absolute():
        raise ValueError(f'invalid relative path: {relative!r}')
    root = Path(root).resolve()
    result = (root / relative).resolve()
    if not result.is_relative_to(root): raise ValueError('path/symlink escapes run_root')
    return result

def binding(root, run_id, cases):
    table = {key: {'root': key, 'resolved_case': f'{key}/resolved_case.json',
                  'case_schema': c['schema'], 'case_identity': c['identity'],
                  'config_sha256': config_hash(c)} for key, c in cases.items()}
    stages = {s: {'case_id': k, 'output': p, 'snapshot_format': FORMAT}
              for s, (k, p) in STAGES.items() if k in cases}
    return {'run_id': run_id, 'run_root': str(Path(root).resolve()),
            'cases': table, 'allowed_stages': stages}

def validate_manifest(value, expected=None):
    if value.get('schema') != 'boris-run-v1' or type(value.get('version')) is not int or value['version'] != 1:
        raise ValueError('unsupported run schema/version')
    b = value['binding']
    if value['binding_sha256'] != digest(b) or expected is not None and b != expected:
        raise ValueError('immutable binding changed')
    import uuid
    uuid.UUID(b['run_id'])
    root = Path(b['run_root'])
    if not root.is_absolute() or str(root.resolve()) != str(root): raise ValueError('noncanonical run_root')
    for key, c in b['cases'].items():
        if key not in ('prepare', 'drive') or c['root'] != key or c['resolved_case'] != f'{key}/resolved_case.json':
            raise ValueError('unsupported case path')
        if c['case_schema'] != ('user_case_v1' if key == 'prepare' else 'user_case_v2'): raise ValueError('case schema')
        inside(root, c['resolved_case'])
    for stage, s in b['allowed_stages'].items():
        if stage not in STAGES or (s['case_id'], s['output']) != STAGES[stage] or s['case_id'] not in b['cases'] or s['snapshot_format'] != FORMAT:
            raise ValueError('unsupported stage/format')
        inside(root, s['output'])
    s = b['allowed_stages'][value['phase']]
    if (value['active_case'], value['active_output']) != (s['case_id'], s['output']): raise ValueError('active stage identity')
    if value['state'] not in ('running', 'verifying', 'completed', 'failed', 'interrupted'): raise ValueError('run state')
    for key in ('revision', 'stage_epoch'):
        if type(value[key]) is not int or value[key] < 1: raise ValueError(key)
    return b

def response_identity(value):
    return tuple(value[k] for k in ('run_id', 'binding_sha256', 'instance', 'stage_id',
                                    'stage_epoch', 'case_id', 'case_identity', 'config_sha256'))

def frame_matches(response, request, current):
    """Used by mock contract tests; viewer must enforce the same tuple on binary headers."""
    return response_identity(response) == response_identity(request) == response_identity(current)
