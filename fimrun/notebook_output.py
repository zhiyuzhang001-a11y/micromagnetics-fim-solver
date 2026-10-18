"""Safe notebook OVF packets and output adapters; no field/solver changes."""
from dataclasses import replace
from functools import wraps
import hashlib
import io
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import zipfile


def snapshot_format(value):
    if value is not None and (not isinstance(value, str) or value not in ('npz', 'ovf')):
        raise ValueError("snapshot_format must be 'npz', 'ovf' or None")
    return value


def saved_format(path):
    with zipfile.ZipFile(path) as archive:
        body = archive.read('manifest.json')
        if hashlib.sha256(body).hexdigest() != archive.read('manifest.sha256').decode():
            raise ValueError('state manifest checksum mismatch')
        value = json.loads(body).get('notebook_output', {'snapshot_format': 'npz'})
    if not isinstance(value, dict) or set(value) != {'snapshot_format'}:
        raise ValueError('invalid notebook output metadata')
    return snapshot_format(value['snapshot_format'])


def _annotate_state(path, fmt):
    from .micromagnetics.persistence import atomic_bytes
    with zipfile.ZipFile(path) as archive:
        contents = {name: archive.read(name) for name in archive.namelist()}
    value = json.loads(contents['manifest.json'])
    value['notebook_output'] = {'snapshot_format': fmt}
    body = json.dumps(value, ensure_ascii=True, sort_keys=True, allow_nan=False).encode()
    contents['manifest.json'] = body
    contents['manifest.sha256'] = hashlib.sha256(body).hexdigest().encode()
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', compression=zipfile.ZIP_STORED) as archive:
        for name, data in contents.items():archive.writestr(name, data)
    atomic_bytes(path, buffer.getvalue())
    return hashlib.sha256(buffer.getvalue()).hexdigest()


def export_packet(core, directory):
    """A new directory; manifest.json is the pair-completion marker."""
    from .micromagnetics.persistence import export_ovf
    directory = Path(directory)
    # Packet parents are owned experiment paths; reject redirection via symlinks.
    for parent in (directory, *directory.parents):
        if parent.is_symlink():raise ValueError('OVF packet path cannot contain a symlink')
    directory.parent.mkdir(parents=True, exist_ok=True)
    directory.mkdir(exist_ok=False)
    with core._state_lock:
        frozen = SimpleNamespace(model=core.model, labels=core.labels, _m=core.m)
        time_s, run_id, steps = core.time, core.run_id, core.total_steps
    marker = directory / 'INCOMPLETE'
    with marker.open('x') as stream:
        stream.write('OVF packet is incomplete until manifest.json exists\n')
    with tempfile.TemporaryDirectory(prefix='.ovf-', dir=directory) as folder:
        stage = Path(folder)
        receipts = export_ovf(frozen, {label:stage/(label+'.ovf') for label in core.labels})
        result = {'complete': True, 'quantity': 'unit_direction', 'valueunits': '1 1 1',
                  'format': 'OVF2 Text', 'time_s': time_s, 'total_steps': steps,
                  'run_id': run_id, 'cells': list(core.model.mesh.cells),
                  'cell_size_m': list(core.model.mesh.cell_size), 'origin_m': list(core.model.mesh.origin),
                  'sublattices': {}}
        for label, receipt in receipts.items():
            target = directory/(label+'.ovf')
            os.link(stage/(label+'.ovf'), target)
            result['sublattices'][label] = {**receipt, 'path': str(target.resolve())}
        # Exclusive completion publication; never claim a partially linked pair.
        body = json.dumps(result, sort_keys=True, indent=2)+'\n'
        completed = stage/'manifest.json'
        completed.write_text(body)
        os.link(completed, directory/'manifest.json')
    marker.unlink()
    return result


def install(core, fmt):
    """Observe the accepted core's cadence, suppressing only NPZ when requested."""
    from .micromagnetics.simulation import step_count
    fmt = snapshot_format(fmt)
    core._notebook_snapshot_format = fmt
    if fmt == 'npz':return
    observed = set()
    failures = {}
    original_observe, original_finish = core._observe, core._finish

    def emit(segment, step):
        key = (segment['id'], step)
        if key in failures:raise failures[key]
        if key in observed:return
        if 'directory' not in segment:return
        try:
            export_packet(core, core._root/segment['directory']/'ovf'/f'm-{step:012d}')
        except Exception as error:
            failures[key] = error
            raise
        observed.add(key)
        core._counts['snapshot_writes'] += 1

    def enabled():
        return fmt == 'ovf' and (core.outputs.snapshots is not None or bool(core.outputs.snapshot_times))

    @wraps(original_observe)
    def observe(segment, step, *, final=False):
        output = core._outputs
        core._outputs = replace(output, snapshots=None, snapshot_times=())
        try:original_observe(segment, step, final=final)
        finally:core._outputs = output
        segment['notebook_snapshot_format'] = fmt
        interval = step_count(output.snapshots, core.solver.dt, 'snapshots') if output.snapshots else None
        events = {step_count(value, core.solver.dt, 'snapshot_times') for value in output.snapshot_times}
        if enabled() and (final or (interval is not None and step % interval == 0) or step in events):
            emit(segment, step)

    @wraps(original_finish)
    def finish(segment, status, steps, error=None, residual=None):
        result = original_finish(segment, status, steps, error, residual)
        # No interpolation: cancelled/failed final is the last accepted state.
        if enabled():emit(segment, steps)
        return result

    core._observe, core._finish = observe, finish
    for name in ('save_state', 'save_checkpoint'):
        original = getattr(core, name)
        def annotate(method):
            @wraps(method)
            def save(path):
                receipt = method(path)
                return {**receipt, 'sha256': _annotate_state(path, fmt)}
            return save
        setattr(core, name, annotate(original))
