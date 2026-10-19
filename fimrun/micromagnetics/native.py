"""Thin lifetime-safe bindings to the existing one- and two-field native operators."""
from pathlib import Path
from dataclasses import asdict
import ctypes as ct
import hashlib
import json
import subprocess
import tempfile
import struct
import numpy as np
from .model import (FM, FiM, Exchange, FiMExchange, OnsiteCoupling, DMI,
                    UniaxialAnisotropy, FiMAnisotropy, Demag, Zeeman)
from ..runtime import RESOURCE_ROOT as ROOT, cache_dir, ensure_integrity
from .._support import kernel_cache as _kernel_cache


EVALUATIONS = {'fm': 0, 'fim': 0}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def fingerprint():
    paths = [ROOT / 'src/script_api/fm.cpp', ROOT / 'src/script_api/fim.cpp',
             ROOT / 'src/user_native.cpp', ROOT / 'src/local_field_team.hpp',
             ROOT / 'src/current_sot.hpp', ROOT / 'validation/fm/fm.hpp',
             ROOT / 'validation/fm/demag.hpp']
    paths += list((ROOT / 'build-script-api').glob('lib*.dylib'))
    return {str(p.relative_to(ROOT)): sha(p) for p in paths}


def kernel_geometry(model):
    grid = model.mesh
    return {'n': list(grid.cells), 'cell_nm': [v * 1e9 for v in grid.cell_size],
            'origin_nm': [v * 1e9 for v in grid.origin],
            'pbc': [1, 1, 0] if grid.boundary == 'periodic_xy' else [0, 0, 0],
            'mirrors': list(grid.mirrors)}


def kernel_key(model, archived_binary=None):
    return {'schema': 'script-qualified-kernel-v2', 'geometry': kernel_geometry(model),
            'source': sha(ROOT / 'src/script_api/kernel_builder.cpp'),
            'builder_binary': archived_binary if archived_binary is not None else sha(ROOT / 'build-script-api/kernel_builder'),
            'equations': {str(p.name): sha(p) for p in (ROOT / 'src/user_kernel').glob('*') if p.is_file()}}


def validate_qualification(model, path, meta, *, archived=False):
    key = meta.get('key', {})
    expected = kernel_key(model, key.get('builder_binary') if archived else None)
    if archived:
        # Physical state includes the actual previously qualified bytes; a different rebuild
        # of the same equations may consume those bytes without claiming strict continuation.
        expected['builder_binary'] = key.get('builder_binary')
        # Byte-regressed pre-capacity generator: same tensor equations and summation.
        if key.get('source') == '998f660a184db2fa005415940911a34dcb005a851d827424bccd0c1105de2f21':
            expected['source'] = key['source']
    if key != expected or not isinstance(key.get('builder_binary'), str) or (len(key['builder_binary']) != 64 or any(c not in '0123456789abcdef' for c in key['builder_binary'])):
        raise ValueError('kernel source/equations/binary provenance mismatch')
    if meta.get('sha256') != sha(path):
        raise ValueError('kernel payload checksum mismatch')
    v = meta.get('verification')
    if not isinstance(v, dict) or v.get('passed') is not True or v.get('failure_detail') or v.get('status', 'passed') not in ('passed', 'success', 'qualified'):
        raise ValueError('kernel qualification missing or explicitly failed')
    def bounded(value, limit, label):
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not np.isfinite(value) or not 0 <= value <= limit:
            raise ValueError('kernel qualification ' + label + ' missing/nonfinite/outside original gate')
    bounded(v.get('reciprocity_max'), 1e-12, 'reciprocity')
    if v.get('coverage') != 'tensor samples and effective zero block; full-kernel finite/reciprocity':
        raise ValueError('kernel qualification coverage missing')
    rows = v.get('reference_samples')
    if not isinstance(rows, list):
        raise ValueError('kernel reference samples missing')
    grid = model.mesh
    canonical = grid.cells == (125,125,1) and grid.cell_size == (4e-9,4e-9,3e-9) and grid.boundary == 'periodic_xy' and grid.mirrors == (10,10)
    known = canonical and meta['sha256'] == 'db71f379e2bea728a475d9e0c6e5e1183c7830ee1ba91e6909f84c532ec012b6' and meta.get('source') == 'bundled-qualified-canonical'
    if known:
        if rows or type(v.get('reference_tensor_evaluations')) is not int or v.get('reference_tensor_evaluations') != 0 or v.get('engineering_reference_error') is not None or v.get('historical_reference') != 'bundled canonical payload pinned by sha256':
            raise ValueError('canonical historical qualification record invalid')
    else:
        if meta.get('source') != 'script-api-mpfr128-asym40':
            raise ValueError('kernel generator source not recognized')
        cx = int(np.ceil(40 * max(grid.cell_size) / grid.cell_size[0]))
        cy = int(np.ceil(40 * max(grid.cell_size) / grid.cell_size[1]))
        coordinates = [(0,0),(1,0),(1,1),(cx-1,0),(cx,0),(cx+1,0),(0,cy-1),(0,cy),(0,cy+1),(29,28),(-1,1),(1,-1)]
        if len(rows) != len(coordinates) or any(not isinstance(row, dict) for row in rows) or any(type(row.get('i')) is not int or type(row.get('j')) is not int for row in rows) or [(row['i'],row['j']) for row in rows] != coordinates:
            raise ValueError('kernel reference sample coverage mismatch')
        for row in rows:
            bounded(row.get('error'), 1e-10, 'sample error')
            bounded(row.get('reference_precision_drift'), 1e-12, 'reference drift')
        bounded(v.get('engineering_reference_error'), 1e-10, 'aggregate error')
        if v['engineering_reference_error'] < max(row['error'] for row in rows):
            raise ValueError('kernel aggregate error below sample errors')
        expected_count = 2 * len(rows) + ((2*grid.mirrors[0]+1)*(2*grid.mirrors[1]+1) if grid.boundary == 'periodic_xy' else 1)
        if type(v.get('reference_tensor_evaluations')) is not int or v['reference_tensor_evaluations'] != expected_count:
            raise ValueError('kernel reference/zero-block count mismatch')
    _kernel_cache.validate_kernel({'geometry': kernel_geometry(model)}, path)
    return meta


def kernel_for(model):
    """Generate only explicitly selected demag; cache hits never waive reference qualification."""
    from ..capacity import model_capacity, require_memory
    require_memory(model_capacity(model)['kernel_working_bytes'], 'kernel capacity')
    b = {'kernel_cache': _kernel_cache}
    grid = model.mesh
    case = {'geometry': kernel_geometry(model)}
    key = kernel_key(model)
    token = hashlib.sha256(json.dumps(key, sort_keys=True).encode()).hexdigest()
    cache = cache_dir() / 'kernel-cache' / token
    if cache.exists():
        if not (cache / 'manifest.json').is_file() or not (cache / 'kernel.f64').is_file():
            raise ValueError('incomplete kernel cache; no automatic regeneration')
        meta = json.loads((cache / 'manifest.json').read_text())
        validate_qualification(model, cache / 'kernel.f64', meta)
        return cache / 'kernel.f64'
    cache.parent.mkdir(parents=True, exist_ok=True)
    import shutil
    needed = 2*model_capacity(model)['kernel_file_bytes']
    if needed > shutil.disk_usage(cache.parent).free:
        raise OSError(f'kernel capacity: temporary kernel needs {needed:,} free bytes')
    with tempfile.TemporaryDirectory(dir=cache.parent) as temp:
        folder = Path(temp)
        payload = folder / 'kernel.f64'
        canonical = grid.cells == (125,125,1) and grid.cell_size == (4e-9,4e-9,3e-9) and grid.boundary == 'periodic_xy' and grid.mirrors == (10,10)
        if canonical:
            source = ROOT / 'examples/kernel125-mirror10.f64'
            if sha(source) != 'db71f379e2bea728a475d9e0c6e5e1183c7830ee1ba91e6909f84c532ec012b6':
                raise ValueError('canonical kernel checksum mismatch')
            payload.write_bytes(source.read_bytes())
            verification = b['kernel_cache'].validate_kernel(case, payload)
            verification['historical_reference'] = 'bundled canonical payload pinned by sha256'
            source_name = 'bundled-qualified-canonical'
        else:
            args = [str(ROOT / 'build-script-api/kernel_builder'), *map(str, grid.cells[:2]),
                    *map(str, grid.cell_size), str(int(grid.boundary == 'periodic_xy')),
                    *map(str, grid.mirrors), str(payload)]
            subprocess.run(args, check=True, capture_output=True)
            samples = json.loads(Path(str(payload) + '.samples.json').read_text())
            verification = b['kernel_cache'].validate_kernel(case, payload, samples)
            source_name = 'script-api-mpfr128-asym40'
        verification['passed'] = True
        meta = {'key': key, 'sha256': sha(payload), 'source': source_name, 'verification': verification}
        validate_qualification(model, payload, meta)
        (folder / 'manifest.json').write_text(json.dumps(meta, indent=2))
        try:
            folder.rename(cache)
        except FileExistsError:
            validate_qualification(model, cache / 'kernel.f64', json.loads((cache / 'manifest.json').read_text()))
    return cache / 'kernel.f64'


def fm_kernel(model, raw_path):
    grid = model.mesh
    nx, ny, _ = grid.cells
    raw = np.fromfile(raw_path, '<f8').reshape(2 * ny, 2 * nx, 6)
    coefficients = np.array([raw[dy % (2 * ny), dx % (2 * nx)]
                             for dy in range(1 - ny, ny) for dx in range(1 - nx, nx)], dtype='<f8')
    body = struct.pack('<8sii3d', b'OPENv2\0\0', nx, ny, *grid.cell_size) + coefficients.tobytes()
    path = Path(raw_path).with_name('kernel-fm.openv2')
    if not path.exists():
        temp = path.with_suffix('.tmp')
        temp.write_bytes(body)
        temp.replace(path)
    if path.read_bytes() != body:
        raise ValueError('FM kernel binding mismatch')
    return path


class Native:
    def __init__(self, model, initial, kernel_override=None):
        from ..capacity import model_capacity, require_memory
        require_memory(model_capacity(model)['simulation_bytes'], 'native model capacity')
        ensure_integrity()
        self.model = model
        self.kind = 'fm' if isinstance(model, FM) else 'fim'
        self.path = ROOT / 'build-script-api' / ('lib' + self.kind + '.dylib')
        if not self.path.is_file():
            raise RuntimeError('Installed native resource missing; run python -m fimrun doctor and follow RECOVERY.md')
        self.lib = ct.CDLL(str(self.path))
        self.lib.mm_error.restype = ct.c_char_p
        self.lib.mm_create.argtypes = [ct.c_char_p, ct.c_char_p]
        self.lib.mm_create.restype = ct.c_void_p
        self.lib.mm_destroy.argtypes = [ct.c_void_p]
        double = ct.POINTER(ct.c_double)
        self.lib.mm_eval.argtypes = [ct.c_void_p, double, double, double]
        self.lib.mm_rhs.argtypes = [ct.c_void_p, double, double, double, double, double]
        for name in ('mm_calls', 'mm_fft_calls'):
            getattr(self.lib, name).argtypes = [ct.c_void_p]
            getattr(self.lib, name).restype = ct.c_ulong
        self.lib.mm_subfields.argtypes = [ct.c_void_p]
        self.lib.mm_local_calls.argtypes = [ct.c_void_p, ct.c_int]
        self.lib.mm_local_calls.restype = ct.c_ulong
        self.kernel = None
        if any(isinstance(t, Demag) for t in model.energy):
            if kernel_override is not None:
                self.kernel = Path(kernel_override)
                raw_kernel = self.kernel.parent / 'kernel.f64'
                meta = json.loads((self.kernel.parent / 'manifest.json').read_text())
                validate_qualification(model, raw_kernel, meta, archived=True)
                if isinstance(model, FM) and fm_kernel(model, raw_kernel) != self.kernel:
                    raise ValueError('FM archive kernel binding mismatch')
            else:
                raw_kernel = kernel_for(model)
                self.kernel = raw_kernel if isinstance(model, FiM) else fm_kernel(model, raw_kernel)
        with tempfile.TemporaryDirectory(prefix='micromagnetics-config-') as folder:
            config = Path(folder) / 'model.txt'
            config.write_text(self.config(initial))
            self.handle = self.lib.mm_create(str(config).encode(), str(self.kernel).encode() if self.kernel else b'')
        if not self.handle:
            raise RuntimeError(self.lib.mm_error().decode())

    def config(self, initial):
        model = self.model
        grid = model.mesh
        terms = {type(t): t for t in model.energy}
        H = terms[Zeeman].H if Zeeman in terms else (0., 0., 0.)
        if isinstance(model, FM):
            c = model.material
            lines = ['schema FM-SI-v1', 'units m_Apm_Jpm_Jpm3_s', 'mode trajectory',
                     'n ' + ' '.join(map(str, grid.cells[:2])), 'h ' + ' '.join(map(str, grid.cell_size)),
                     f'Ms {c.Ms}', f'A {terms[Exchange].A if Exchange in terms else 0.}',
                     f'K1 {terms[UniaxialAnisotropy].K1 if UniaxialAnisotropy in terms else 0.}',
                     'axis ' + ' '.join(map(str, terms[UniaxialAnisotropy].axis if UniaxialAnisotropy in terms else (0., 0., 1.))),
                     'H ' + ' '.join(map(str, H)), f'alpha {c.alpha}', 'grel 1',
                     f'gamma_G {c.gamma_H}', 'gamma_convention Gilbert',
                     'active ' + ' '.join(str(int(t in terms)) for t in (Exchange, UniaxialAnisotropy, Zeeman, Demag)),
                     # Parser compatibility fields; this binding never invokes its capped trajectory CLI.
                     'dt 1', 'steps 1', 'stride 1', 'wall 1', 'memory 1048576', 'state']
            if self.kernel is not None:
                lines[-1:-1] = ['kernel_path ' + str(self.kernel), 'kernel_sha256 ' + sha(self.kernel)]
            lines += [' '.join(map(str, row)) for row in initial.reshape(-1, 3)]
            return '\n'.join(lines) + '\n'
        c = model.material
        ex = terms.get(FiMExchange)
        an = terms.get(FiMAnisotropy)
        d = terms.get(DMI)
        rows = ['USER-FIM-v1', grid.cells, grid.cell_size,
                (1, 1, 0) if grid.boundary == 'periodic_xy' else (0, 0, 0),
                (c.A.Ms, c.B.Ms), (ex.A_A, ex.A_B) if ex else (0., 0.),
                (terms[OnsiteCoupling].Ah if OnsiteCoupling in terms else 0., ex.Anh if ex else 0.),
                (d.D_A, d.D_B) if d else (0., 0.),
                (an.K1_A, an.K1_B) if an else (0., 0.), (an.K2_A, an.K2_B) if an else (0., 0.),
                an.axis_A if an else (0., 0., 1.), an.axis_B if an else (0., 0., 1.),
                (c.A.alpha, c.B.alpha), (c.A.gamma_H, c.B.gamma_H), H,
                tuple(int(t in terms) for t in (FiMExchange, OnsiteCoupling, DMI, FiMAnisotropy)),
                # These legacy parser fields are not enforced by the field-only binding.
                (1., 1., 1, grid.cells[0] * (2 if grid.boundary == 'open' else 1), grid.cells[1] * (2 if grid.boundary == 'open' else 1), 1048576)]
        return '\n'.join(row if isinstance(row, str) else ' '.join(map(str, row)) for row in rows) + '\n'

    @staticmethod
    def ptr(a):
        return a.ctypes.data_as(ct.POINTER(ct.c_double))

    def evaluate(self, m):
        m = np.ascontiguousarray(m, dtype=np.float64)
        H = np.empty_like(m)
        parts = np.empty(7, dtype=np.float64)
        if self.lib.mm_eval(self.handle, self.ptr(m), self.ptr(H), self.ptr(parts)):
            raise RuntimeError(self.lib.mm_error().decode())
        EVALUATIONS[self.kind] += 1
        if not np.isfinite(H).all() or not np.isfinite(parts).all():
            raise FloatingPointError('nonfinite field/energy')
        return H, parts

    def rhs(self, m, H, current):
        m = np.ascontiguousarray(m, dtype=np.float64)
        H = np.ascontiguousarray(H, dtype=np.float64)
        spec = np.zeros(10)
        if current is not None:
            spec[:] = (*current.J, *current.incident_direction, current.xi_A, current.xi_B,
                       current.field_like_A, current.field_like_B)
        out = np.empty_like(m)
        power = np.empty(4)
        if self.lib.mm_rhs(self.handle, self.ptr(m), self.ptr(H), self.ptr(spec), self.ptr(out), self.ptr(power)):
            raise RuntimeError(self.lib.mm_error().decode())
        if not np.isfinite(out).all() or not np.isfinite(power).all():
            raise FloatingPointError('nonfinite RHS/power')
        return out, power

    def sd_step(self, m, H, prev, gradient, controls):
        if self.kind != 'fim':
            raise NotImplementedError('FM SDesc is not qualified in this release')
        double = ct.POINTER(ct.c_double)
        self.lib.mm_sd.argtypes = [double, double, double, double, ct.c_ulong, double, double, double, double]
        arrays = [np.ascontiguousarray(v, dtype=np.float64) for v in (m, H, prev, gradient, controls)]
        m, H, prev, gradient, controls = arrays
        controls = controls.copy()
        ms = np.array([self.model.material.A.Ms, self.model.material.B.Ms])
        out, next_gradient = np.empty_like(m), np.empty_like(m)
        if self.lib.mm_sd(self.ptr(m), self.ptr(H), self.ptr(prev), self.ptr(gradient), m[0].size // 3,
                          self.ptr(controls), self.ptr(ms), self.ptr(out), self.ptr(next_gradient)):
            raise RuntimeError(self.lib.mm_error().decode())
        return out, next_gradient, controls

    def counters(self):
        return {'fields': self.lib.mm_calls(self.handle), 'fft_transforms': self.lib.mm_fft_calls(self.handle),
                'subfields': self.lib.mm_subfields(self.handle),
                'contribution_branches': [self.lib.mm_local_calls(self.handle, i) for i in range(4)]}

    def close(self):
        if getattr(self, 'handle', None):
            self.lib.mm_destroy(self.handle)
            self.handle = None

    def __del__(self):
        self.close()
