"""Versioned, checksum-verified state/checkpoint containers and OVF2 interchange."""
from dataclasses import asdict
from pathlib import Path
import hashlib
import io
import json
import os
import tempfile
import uuid
import zipfile
import numpy as np
from . import model as models
from .model import FM, FiM, Grid, FMMaterial, FiMMaterial, Sublattice, FiMSOT
from .initial import directions
from .native import fingerprint, ROOT, sha
from ..runtime import PACKAGE_ROOT, cache_dir

SCHEMA = 'micromagnetics-state-v1'
TERMS = {name: getattr(models, name) for name in ('Exchange', 'FiMExchange', 'OnsiteCoupling',
         'DMI', 'UniaxialAnisotropy', 'FiMAnisotropy', 'Demag', 'Zeeman')}


def atomic_bytes(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(prefix=path.name + '.', suffix='.tmp', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
    finally:
        Path(temp).unlink(missing_ok=True)


def atomic_json(path, value):
    atomic_bytes(path, (json.dumps(value, ensure_ascii=True, allow_nan=False, indent=2) + '\n').encode())


def encode_model(model):
    return {'type': type(model).__name__, 'mesh': asdict(model.mesh), 'material': asdict(model.material),
            'energy': [{'type': type(t).__name__, 'parameters': asdict(t)} for t in model.energy]}


def decode_model(value):
    if set(value) != {'type', 'mesh', 'material', 'energy'}:
        raise ValueError('model schema fields mismatch')
    grid = dict(value['mesh'])
    for key in ('cells', 'cell_size', 'origin', 'mirrors'):
        grid[key] = tuple(grid[key])
    grid = Grid(**grid)
    if value['type'] == 'FM':
        material = FMMaterial(**value['material'])
        cls = FM
    elif value['type'] == 'FiM':
        material = dict(value['material'])
        material['A'] = Sublattice(**material['A'])
        material['B'] = Sublattice(**material['B'])
        material = FiMMaterial(**material)
        cls = FiM
    else:
        raise ValueError('unsupported model kind')
    energy = []
    for term in value['energy']:
        if set(term) != {'type', 'parameters'} or term['type'] not in TERMS:
            raise ValueError('unknown energy type/fields')
        energy.append(TERMS[term['type']](**term['parameters']))
    return cls(mesh=grid, material=material, energy=tuple(energy))


def npy(value):
    stream = io.BytesIO()
    np.save(stream, np.asarray(value, dtype='<f8'), allow_pickle=False)
    return stream.getvalue()


def strict_identity():
    import platform, sys
    result = fingerprint()
    result['runtime'] = {'platform': sys.platform, 'machine': platform.machine(), 'byteorder': sys.byteorder, 'numpy': np.__version__}
    result.update({'fimrun/micromagnetics/'+p.name: sha(p) for p in (PACKAGE_ROOT/'micromagnetics').glob('*.py')})
    return result


def save(sim, path, *, strict):
    if sim._busy:
        raise RuntimeError('save is allowed only at a completed accepted-step boundary')
    if strict and sim._algorithm not in ('rk4', 'sdesc'):
        raise NotImplementedError('checkpoint algorithm is not qualified')
    if strict and sim._algorithm == 'sdesc' and not isinstance(sim.model, FiM):
        raise NotImplementedError('FM static checkpoints are unsupported')
    # Serialize only registered model data; arbitrary Python objects are never pickled.
    model = encode_model(sim.model)
    arrays = {'m.npy': npy(sim._m), 'dissipation.npy': npy(sim.dissipation), 'drive_work.npy': npy(sim.drive_work)}
    sd = None
    if strict and sim._sd is not None:
        for key in ('prev', 'gradient', 'controls'):
            arrays['sd-' + key + '.npy'] = npy(sim._sd[key])
        sd = {key: sim._sd[key] for key in ('consecutive', 'criterion', 'residual_checked')}
    kernel = sim._native.kernel if sim._native is not None else sim._kernel_override
    if kernel is not None:
        arrays['kernel.f64'] = Path(kernel).read_bytes()
        arrays['kernel-source.f64'] = (Path(kernel).parent / 'kernel.f64').read_bytes()
        arrays['kernel-qualification.json'] = (Path(kernel).parent / 'manifest.json').read_bytes()
        from .native import validate_qualification
        validate_qualification(sim.model, Path(kernel).parent / 'kernel.f64', json.loads(arrays['kernel-qualification.json']), archived=True)
    metadata = {'schema': SCHEMA, 'grade': 'strict_checkpoint' if strict else 'physical_state',
                'version': 1, 'id': str(uuid.uuid4()), 'run_id': sim.run_id, 'parent': sim.parent,
                'model': model, 'labels': sim.labels, 'solver': {'type': 'RK4' if sim.solver.dt is not None else 'unconfigured', 'dt': sim.solver.dt},
                'algorithm': sim._algorithm, 'time_s': sim.time, 'total_steps': sim.total_steps,
                'clock_fraction': [str(sim._clock.numerator), str(sim._clock.denominator)],
                'grid_input': sim.describe()['grid_input'],
                'current': asdict(sim.current) if sim.current else None,
                'energy_origin_J': sim.energy_origin, 'parameter_energy_changes_J': sim.energy_changes,
                'events': sim.events, 'segments': sim.segments, 'sd': sd,
                'outputs': {**asdict(sim.outputs), 'directory': str(sim.outputs.directory) if sim.outputs.directory is not None else None},
                'rebuild': 'FFT plans/spectra and field; ordinary state also resets BB private history',
                'implementation': strict_identity(), 'platform': 'macOS native CPU; little-endian f64',
                'data': {name: {'sha256': hashlib.sha256(value).hexdigest(), 'bytes': len(value)} for name, value in arrays.items()}}
    body = json.dumps(metadata, ensure_ascii=True, allow_nan=False, sort_keys=True).encode()
    # Manifest itself is covered, so metadata corruption cannot silently change physical meaning.
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', compression=zipfile.ZIP_STORED) as archive:
        archive.writestr('manifest.json', body)
        archive.writestr('manifest.sha256', hashlib.sha256(body).hexdigest())
        for name, value in arrays.items():
            archive.writestr(name, value)
    atomic_bytes(path, buffer.getvalue())
    return {'path': str(Path(path).resolve()), 'id': metadata['id'], 'grade': metadata['grade'],
            'time_s': sim.time, 'sha256': hashlib.sha256(buffer.getvalue()).hexdigest()}


def load(path, *, strict, outputs=None):
    from .simulation import Simulation, RK4, Outputs
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        if len(set(names)) != len(names):
            raise ValueError('duplicate archive entries')
        body = archive.read('manifest.json')
        if hashlib.sha256(body).hexdigest() != archive.read('manifest.sha256').decode():
            raise ValueError('state manifest checksum mismatch')
        value = json.loads(body)
        if value.get('schema') != SCHEMA or value.get('version') != 1:
            raise ValueError('unsupported state schema/version')
        if value.get('grade') not in ('strict_checkpoint', 'physical_state'):
            raise ValueError('unknown restore grade')
        if strict and value['grade'] != 'strict_checkpoint':
            raise ValueError('physical state is not a strict checkpoint; no automatic downgrade')
        if strict and value['implementation'] != strict_identity():
            raise ValueError('strict checkpoint implementation/binary mismatch')
        expected = {'manifest.json', 'manifest.sha256', *value['data']}
        if set(names) != expected:
            raise ValueError('unexpected archive entries')
        data = {}
        for name, binding in value['data'].items():
            allowed = {'m.npy', 'dissipation.npy', 'drive_work.npy', 'sd-prev.npy', 'sd-gradient.npy', 'sd-controls.npy', 'kernel.f64', 'kernel-source.f64', 'kernel-qualification.json'}
            if name not in allowed:
                raise ValueError('unknown state data field')
            raw = archive.read(name)
            if len(raw) != binding['bytes'] or hashlib.sha256(raw).hexdigest() != binding['sha256']:
                raise ValueError('state data checksum mismatch')
            data[name] = raw
    def array(name):
        result = np.load(io.BytesIO(data[name]), allow_pickle=False)
        if result.dtype != np.dtype('<f8') or not np.isfinite(result).all():
            raise ValueError('state arrays require finite little-endian f64')
        return result
    model = decode_model(value['model'])
    provenance = value.get('grid_input', {}).get('requested_size_m')
    if provenance is not None:
        candidate = Grid(size=tuple(provenance), cell_size=model.mesh.cell_size, boundary=model.mesh.boundary, origin=model.mesh.origin, mirrors=model.mesh.mirrors)
        if candidate != model.mesh:raise ValueError('grid input provenance disagrees with effective geometry')
        object.__setattr__(model.mesh, '_requested_size', candidate.requested_size)
    if value['labels'] != list(model.labels) or value['solver']['type'] not in ('RK4', 'unconfigured'):
        raise ValueError('state labels/solver mismatch')
    kind = 'fm' if isinstance(model, FM) else 'fim'
    binary = ROOT / 'build-script-api' / ('lib' + kind + '.dylib')
    if not binary.is_file():
        raise RuntimeError('required native library is unavailable')
    import ctypes
    ctypes.CDLL(str(binary))
    m = directions(array('m.npy'), (len(model.labels), *model.mesh.shape))
    initial = m[0] if isinstance(model, FM) else {label: m[i] for i, label in enumerate(model.labels)}
    stored_outputs = dict(value['outputs'])
    stored_outputs['directory'] = (str(Path(path).resolve().parent / ('restored-' + uuid.uuid4().hex))
                                   if stored_outputs['directory'] is not None else None)
    for key in ('scalars', 'analysis', 'snapshot_times'):
        stored_outputs[key] = tuple(stored_outputs[key])
    if value['solver']['type']=='unconfigured' and value['solver']['dt'] is not None:
        raise ValueError('unconfigured solver must have no dt')
    solver = None if value['solver']['type']=='unconfigured' else RK4(dt=value['solver']['dt'])
    sim = Simulation(model=model, initial=initial, solver=solver,
                     outputs=outputs if outputs is not None else Outputs(**stored_outputs))
    for key in ('dissipation', 'drive_work'):
        a = array(key + '.npy')
        if a.shape != (len(model.labels),) or key == 'dissipation' and np.any(a < 0):
            raise ValueError('invalid cumulative physical quantity')
        setattr(sim, key, a)
    if not isinstance(value['time_s'], (float, int)) or not np.isfinite(value['time_s']) or value['time_s'] < 0 or type(value['total_steps']) is not int or value['total_steps'] < 0:
        raise ValueError('invalid physical clock/step count')
    from fractions import Fraction
    if not isinstance(value.get('clock_fraction'), list) or len(value['clock_fraction']) != 2:
        raise ValueError('exact physical clock representation missing')
    sim._clock = Fraction(int(value['clock_fraction'][0]), int(value['clock_fraction'][1]))
    if sim._clock < 0 or float(sim._clock) != value['time_s']:
        raise ValueError('physical clock representations disagree')
    sim._time = value['time_s']
    sim.total_steps = value['total_steps']
    sim.energy_origin = value['energy_origin_J']
    sim.energy_changes = value['parameter_energy_changes_J']
    if any(x is not None and not np.isfinite(x) for x in (sim.energy_origin, sim.energy_changes)):
        raise ValueError('invalid energy baseline')
    sim._current = FiMSOT(**value['current']) if value['current'] else None
    if isinstance(model, FM) and sim.current is not None:
        raise ValueError('FM cannot restore FiM SOT')
    sim.run_id = value['run_id'] if strict else str(uuid.uuid4())
    sim.parent = {'state_id': value['id'], 'source_run_id': value['run_id'], 'source_sha256': sha(path),
                  'restore_grade': 'strict_checkpoint' if strict else 'physical_state'}
    sim.events = value['events']
    # Preserve protocol position and provenance without ever reopening an old output directory.
    sim.events.append({'kind': 'restore', 'source': sim.parent, 'completed_segments': value['segments']})
    sim._algorithm = value['algorithm']
    sim.restore_grade = 'strict_checkpoint' if strict else 'physical_state; solver private history rebuilt'
    sim._strict = strict
    if strict and value['sd'] is not None:
        prev, grad, controls = array('sd-prev.npy'), array('sd-gradient.npy'), array('sd-controls.npy')
        if prev.shape != m.shape or grad.shape != m.shape or controls.shape != (5,):
            raise ValueError('static history shape mismatch')
        from .simulation import MaxTransverseField, ResidualAndMxh
        state = value['sd']
        if type(state['consecutive']) is not int or state['consecutive'] < 0 or type(state['residual_checked']) is not bool:
            raise ValueError('invalid static stopping position')
        criterion_type = ResidualAndMxh if 'mxh' in state['criterion'] else MaxTransverseField
        criterion = asdict(criterion_type(**state['criterion']))
        if state['consecutive'] > criterion['consecutive']:
            raise ValueError('invalid static consecutive count')
        sim._sd = {'prev': prev, 'gradient': grad, 'controls': controls,
                   'consecutive': state['consecutive'], 'criterion': criterion,
                   'residual_checked': state['residual_checked']}
    if 'kernel.f64' in data:
        if not any(isinstance(t, models.Demag) for t in model.energy):
            raise ValueError('unexpected kernel data for disabled demag')
        if 'kernel-source.f64' not in data or 'kernel-qualification.json' not in data:
            raise ValueError('state kernel qualification/source missing; no automatic regeneration')
        from .native import validate_qualification, fm_kernel
        raw = data['kernel-source.f64']
        meta_raw = data['kernel-qualification.json']
        meta = json.loads(meta_raw)
        folder = cache_dir() / 'state-kernels'
        folder.mkdir(parents=True, exist_ok=True)
        token = hashlib.sha256(raw + meta_raw).hexdigest()
        target_folder = folder / token
        with tempfile.TemporaryDirectory(dir=folder) as temp:
            staged = Path(temp)
            (staged / 'kernel.f64').write_bytes(raw)
            (staged / 'manifest.json').write_bytes(meta_raw)
            validate_qualification(model, staged / 'kernel.f64', meta, archived=True)
            native_name = 'kernel.f64'
            if isinstance(model, FM):
                native_name = fm_kernel(model, staged / 'kernel.f64').name
            if (staged / native_name).read_bytes() != data['kernel.f64']:
                raise ValueError('native kernel differs from qualified source tensor')
            if target_folder.exists():
                for candidate in staged.iterdir():
                    target = target_folder / candidate.name
                    if not target.is_file() or target.read_bytes() != candidate.read_bytes():
                        raise ValueError('state kernel cache content mismatch')
            else:
                staged.rename(target_folder)
        sim._kernel_override = target_folder / native_name

    return sim


def export_ovf(sim, paths):
    if isinstance(sim.model, FM) and isinstance(paths, (str, Path)):
        paths = {'FM': paths}
    if not isinstance(paths, dict) or set(paths) != set(sim.labels):
        raise ValueError('export requires one explicitly labelled path per independent field')
    if len({str(Path(p).resolve()) for p in paths.values()}) != len(paths):
        raise ValueError('independent sublattices need distinct OVF paths')
    grid = sim.model.mesh
    results = {}
    for i, label in enumerate(sim.labels):
        header = ['# OOMMF OVF 2.0', '# Segment count: 1', '# Begin: Segment', '# Begin: Header',
                  '# Title: magnetization_direction_' + label, '# Desc: sublattice=' + label,
                  '# meshtype: rectangular', '# meshunit: m', '# valuedim: 3', '# valueunits: 1 1 1', '# valuelabels: mx my mz']
        for j, axis in enumerate('xyz'):
            header += [f'# {axis}nodes: {grid.cells[j]}', f'# {axis}stepsize: {grid.cell_size[j]:.17g}',
                       f'# {axis}base: {grid.origin[j] + grid.cell_size[j] / 2:.17g}',
                       f'# {axis}min: {grid.origin[j]:.17g}', f'# {axis}max: {grid.origin[j] + grid.cells[j]*grid.cell_size[j]:.17g}']
        header += ['# End: Header', '# Begin: Data Text']
        rows = [' '.join(f'{v:.17g}' for v in row) for row in sim._m[i].reshape(-1, 3)]
        atomic_bytes(paths[label], ('\n'.join(header + rows + ['# End: Data Text', '# End: Segment']) + '\n').encode())
        results[label] = {'path': str(Path(paths[label]).resolve()), 'sha256': sha(paths[label]), 'quantity': 'unit_direction'}
    return results


def structure(sim):
    import importlib
    from ..bridge import legacy
    legacy()
    m = sim._m
    grid = sim.model.mesh
    case = {'geometry': {'n': list(grid.cells), 'cell_nm': [v * 1e9 for v in grid.cell_size],
                        'origin_nm': [v * 1e9 for v in grid.origin], 'pbc': [1, 1, 0] if grid.boundary == 'periodic_xy' else [0, 0, 0]},
            'output': {'goal': 'observe'}}
    from .analysis import observe
    value = observe(m, case)
    return {label: value['sublattices'][i] for i, label in enumerate(sim.labels)}


def read_segments(directory):
    """Return ordered rows with segment/event identities; never erase same-time switch events."""
    import csv
    root = Path(directory)
    value = json.loads((root / 'segments.json').read_text())
    if value['schema'] != 'micromagnetics-segments-v1':
        raise ValueError('unknown segment manifest')
    rows = []
    last_end = None
    for segment in value['segments']:
        if last_end is not None and segment['t_start'] != last_end:
            rows.append({'kind': 'gap_or_overlap', 'previous_end': last_end, 'next_start': segment['t_start']})
        if 'directory' not in segment:
            rows.append({'kind': 'unstored_segment', 'segment_id': segment['id'], 't_start': segment['t_start'], 't_end': segment['t_end']})
            last_end = segment['t_end']
            continue
        folder = (root / segment['directory']).resolve()
        if not folder.is_relative_to(root.resolve()):
            raise ValueError('segment path escapes output root')
        path = folder / 'scalars.csv'
        if path.exists():
            rows.extend(dict(row, kind='sample') for row in csv.DictReader(path.open()))
        last_end = segment['t_end']
    return {'run_id': value['run_id'], 'parent': value['parent'], 'rows': rows,
            'events': value['events'], 'deduplication': 'none; same-time samples retain segment and boundary identity',
            'analysis': 'no cross-segment velocity inference is performed'}
