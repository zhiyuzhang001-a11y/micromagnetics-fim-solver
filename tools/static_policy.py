"""Explicit policy/configuration and immutable saved-state identity helpers."""
from pathlib import Path
import hashlib
import json
import math
import re

POLICY_ID = 'FIM_POST_PH_MAX_V1'
KERNEL_SHA = 'db71f379e2bea728a475d9e0c6e5e1183c7830ee1ba91e6909f84c532ec012b6'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_json(path):
    def reject(value):
        raise ValueError('nonfinite JSON: ' + value)
    return json.loads(Path(path).read_text(), parse_constant=reject)


def clean(value):
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, dict):
        return {str(k): clean(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [clean(v) for v in value]
    return value


def has_nonfinite(value):
    if isinstance(value, float):
        return not math.isfinite(value)
    if isinstance(value, dict):
        return any(has_nonfinite(v) for v in value.values())
    if isinstance(value, (list, tuple)):
        return any(has_nonfinite(v) for v in value)
    return False


def write_json(path, value):
    path = Path(path)
    tmp = path.with_name(path.name + '.tmp')
    tmp.write_text(json.dumps(clean(value), indent=2, allow_nan=False) + '\n')
    tmp.replace(path)


def tolerance(value):
    if isinstance(value, bool):
        raise ValueError('tolerance must be finite and positive')
    number = float(value)
    if not math.isfinite(number) or number <= 0:
        raise ValueError('tolerance must be finite and positive')
    return number


def vector(value):
    if not isinstance(value, (list, tuple)) or len(value) != 3:
        raise ValueError('explicit external_H_Apm vector required')
    result = [float(v) for v in value]
    if not all(math.isfinite(v) for v in result):
        raise ValueError('external_H_Apm must be finite')
    return result


def read_supported_config(path):
    path = Path(path)
    if path.stat().st_size > 64 * 1024**2:
        raise ValueError('bounded configuration size')
    lines = path.read_text().splitlines()
    header = lines[0].split()
    if len(header) != 3 or header[0] != 'P-Anh-v1' or any(not re.fullmatch(r'[A-Za-z0-9_.-]{1,100}', v) for v in header[1:]):
        raise ValueError('unsupported configuration schema')
    expected = [[125,125,1],[4e-9,4e-9,3e-9],[1,1,0],[3e5,6e5],[5e-12,5e-12],[-8e6,-8e6],[-5e-12,-5e-12],
                [.00105,.00105],[109000,109000],[0,0],[0,0,1],[1,1,1,1]]
    actual = [[float(x) for x in line.split()] for line in lines[1:13]]
    if actual != expected:
        raise ValueError('only canonical fixed FiM model is supported; FM/missing B is not valid')
    if len(lines) < 15:
        raise ValueError('truncated configuration')
    budgets = [float(x) for x in lines[13].split()]
    if len(budgets) != 3 or not all(math.isfinite(v) for v in budgets) or not budgets[0].is_integer() or not budgets[2].is_integer() or not 1 <= budgets[0] <= 1000 or not 0 < budgets[1] <= 30 or not 0 < budgets[2] <= 2147483648:
        raise ValueError('unsupported configuration budgets')
    # Native reader independently checks every configuration state vector too.
    values = [float(x) for line in lines[14:] for x in line.split()]
    if len(values) != 93750 or not all(math.isfinite(v) for v in values):
        raise ValueError('invalid configuration magnetization body')
    if any(abs(math.sqrt(sum(v*v for v in values[k:k+3]))-1)>1e-12 for k in range(0,len(values),3)):
        raise ValueError('nonunit configuration magnetization')
    return {'schema': header[0], 'n': actual[0], 'cell_m': actual[1], 'pbc': actual[2], 'Ms_Apm': actual[3],
            'A_Jpm': actual[4], 'Ah': actual[5], 'Anh': actual[6], 'D': actual[7], 'K1': actual[8],
            'K2': actual[9], 'easy_axis': actual[10], 'active': actual[11]}


def read_sidecar(checkpoint, config_sha, kernel_sha, adopt_legacy):
    checkpoint = Path(checkpoint)
    path = Path(str(checkpoint) + '.policy.json')
    if not path.exists():
        if not adopt_legacy:
            raise ValueError('checkpoint has no policy sidecar; explicit --adopt-legacy-checkpoint required')
        return None
    sidecar = load_json(path)
    if sidecar['policy_id'] != POLICY_ID or sidecar['requested_tolerance']['unit'] != 'A/m':
        raise ValueError('checkpoint policy/unit mismatch')
    tolerance(sidecar['requested_tolerance']['value'])
    if sidecar['checkpoint_sha256'] != sha(checkpoint) or sidecar['configuration_sha256'] != config_sha or sidecar['kernel_sha256'] != kernel_sha:
        raise ValueError('checkpoint sidecar/input identity mismatch')
    raw = checkpoint.read_bytes()
    if len(raw) != 2250044 or hashlib.sha256(raw[44:750044]).hexdigest() != sidecar['final_m_sha256']:
        raise ValueError('checkpoint magnetization/sidecar identity mismatch')
    return sidecar


def resolve_policy(policy_config=None, override=None, sidecar=None, external_override=None):
    cfg = load_json(policy_config) if policy_config else None
    for item in [cfg, sidecar]:
        if item and (item.get('policy_id') != POLICY_ID or item.get('requested_tolerance',{}).get('unit') != 'A/m'):
            raise ValueError('unsupported policy/unit')
    previous = sidecar['requested_tolerance']['value'] if sidecar else None
    configured = cfg['requested_tolerance']['value'] if cfg else None
    value = override if override is not None else configured if cfg else previous
    if value is None:
        raise ValueError('explicit tolerance/policy configuration or inherited sidecar required')
    eps = tolerance(value)
    external = external_override if external_override is not None else cfg.get('external_H_Apm') if cfg else sidecar.get('external_H_Apm') if sidecar else None
    return {'policy_id': POLICY_ID, 'requested_tolerance': {'value': eps, 'unit': 'A/m'},
            'external_H_Apm': vector(external),
            'tolerance_provenance': {'source': 'CLI_override' if override is not None else 'policy_config' if cfg else 'checkpoint_sidecar',
                                     'sidecar_value': previous, 'configured_value': configured, 'CLI_override': override,
                                     'policy_config_sha256': sha(policy_config) if policy_config else None},
            'external_provenance': {'source': 'CLI_override' if external_override is not None else 'policy_config' if cfg else 'checkpoint_sidecar',
                                    'previous': sidecar.get('external_H_Apm') if sidecar else None}}


def success_status(native, independent, identities_match, timed_out=False):
    # Native stop reason is immutable evidence, never replaced with independent PH.
    if timed_out:
        return 'failed_timeout'
    if native.get('stop_reason') != 'residual_tolerance' or not native.get('native_candidate'):
        return 'not_success'
    if independent.get('status') == 'not_checked':
        return 'unverified'
    if independent.get('status') != 'passed' or not identities_match:
        return 'failed_independent_check'
    if not all(isinstance(independent.get(k),(float,int)) and math.isfinite(independent[k]) for k in ['achieved_A_Apm','achieved_B_Apm']):
        return 'failed_independent_check'
    return 'success'
