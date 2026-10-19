"""Sequential native FM/FiM operations with explicit physical clock and provenance."""
from dataclasses import dataclass, asdict, replace
from pathlib import Path
import copy
import csv
import json
import math
import threading
from fractions import Fraction
import uuid
import time
import warnings
import numpy as np
from .model import FM, FiM, FiMSOT, Zeeman, describe, scalar
from .initial import generate, directions
from .native import Native


@dataclass(frozen=True, kw_only=True)
class RK4:
    dt: float

    def __post_init__(self):
        scalar(self.dt, 'RK4.dt', positive=True)


@dataclass(frozen=True)
class _UnconfiguredDynamics:
    """Static/initial state with no physical integration step configured."""
    dt: None = None


def energy_columns(energy, model):
    """Map the accepted cached native packet to J columns without evaluation."""
    names = ('exchange', 'anh', 'ah', 'dmi', 'anisotropy', 'demag', 'zeeman')
    total = float(np.sum(energy)) if energy is not None else ''
    values = [''] * 7
    if energy is not None and np.shape(energy) == (7,):
        if isinstance(model, FiM):
            values = list(map(float, energy))
        else:
            # FM ABI uses exchange/anisotropy/Zeeman/demag in slots 0..3.
            values = [float(energy[0]), 0., 0., 0., float(energy[1]), float(energy[3]), float(energy[2])]
    return {'energy_J': total, 'energy_total_J': total,
            **{f'energy_{name}_J': value for name, value in zip(names, values)}}


@dataclass(frozen=True)
class MaxTransverseField:
    tolerance: float
    consecutive: int = 1

    def __post_init__(self):
        scalar(self.tolerance, 'tolerance [A/m]', positive=True)
        if type(self.consecutive) is not int or self.consecutive < 1:
            raise ValueError('consecutive must be a positive integer')


@dataclass(frozen=True)
class ResidualAndMxh(MaxTransverseField):
    """Accepted-state A/B transverse H gates; Ms is never net magnetization."""
    mxh: float = 1e-5

    def __post_init__(self):
        super().__post_init__()
        scalar(self.mxh, 'mxh [dimensionless]', positive=True)

    def satisfied(self, residual, model):
        ms = np.array([getattr(model.material, label).Ms for label in model.labels])
        return bool(np.all(residual <= self.tolerance) and np.all(residual / ms <= self.mxh))


@dataclass(frozen=True, kw_only=True)
class Outputs:
    directory: str | Path | None = None
    scalars: tuple[str, ...] = ()
    every: float | None = None
    snapshots: float | None = None
    snapshot_times: tuple[float, ...] = ()
    analysis: tuple[str, ...] = ()
    preview: bool = False
    preview_port: int = 8766

    def __post_init__(self):
        names = {'time', 'mean_m', 'energy', 'dissipation', 'drive_work', 'residual', 'mxh'}
        if not isinstance(self.scalars, tuple) or set(self.scalars) - names:
            raise ValueError('scalars: time, mean_m, energy, dissipation, drive_work, residual, mxh only')
        if not isinstance(self.analysis, tuple) or set(self.analysis) - {'structure'}:
            raise ValueError('analysis supports only the explicit structure operation')
        for key in ('every', 'snapshots'):
            if getattr(self, key) is not None:
                scalar(getattr(self, key), key, positive=True)
        if not isinstance(self.snapshot_times, tuple):
            raise TypeError('snapshot_times must be a tuple of stage-relative SI times')
        for value in self.snapshot_times:
            scalar(value, 'snapshot_times', nonnegative=True)
        if (self.snapshots is not None or self.snapshot_times) and self.directory is None:
            raise ValueError('snapshot output requires a directory')
        if type(self.preview) is not bool or type(self.preview_port) is not int or not 1024 <= self.preview_port <= 65535:
            raise ValueError('preview requires bool and explicit port 1024..65535')


@dataclass(frozen=True)
class RunResult:
    status: str
    t_start: float
    t_end: float
    steps: int
    residual_Apm: tuple | None
    error: str | None
    segment_id: str


def step_count(duration, dt, label):
    scalar(duration, label)
    if duration < 0:
        raise ValueError(f'{label} cannot be negative')
    n = duration / dt
    if not math.isfinite(n) or abs(n - round(n)) > 8 * math.ulp(max(1., n)):
        lo, hi = math.floor(n) * dt, math.ceil(n) * dt
        raise ValueError(f'{label} must be an integer number of dt; nearest valid values are {lo!r} and {hi!r} s')
    return int(round(n))


class Simulation:
    def __init__(self, *, model: FM | FiM, initial, solver: RK4 | None = None, outputs: Outputs | None = None):
        if not isinstance(model, (FM, FiM)) or (solver is not None and not isinstance(solver, (RK4, _UnconfiguredDynamics))):
            raise TypeError('model must be FM/FiM and solver must be RK4')
        self._model = model
        self._solver = solver if solver is not None else _UnconfiguredDynamics()
        self._outputs = outputs if outputs is not None else Outputs()
        if not isinstance(self.outputs, Outputs):
            raise TypeError('outputs must be Outputs')
        self._m = generate(model, initial)
        self.initial_source = {'type': type(initial).__name__, 'kind': 'explicit directions'}
        self._time = 0.
        self._clock = Fraction(0)
        self._state_lock = threading.RLock()
        self.total_steps = 0
        self._current = None
        self.dissipation = np.zeros(len(model.labels))
        self.drive_work = np.zeros(len(model.labels))
        self.energy_origin = None
        self.energy_changes = 0.
        self.run_id = str(uuid.uuid4())
        self.parent = None
        self.events = []
        self.segments = []
        self.records = []
        self.last_result = None
        self._native = None
        self._kernel_override = None
        self._field = None
        self._energy = None
        self._sd = None
        self._algorithm = 'rk4'
        self._root = None
        self._busy = False
        self._strict = False
        self._preview = None
        self._active_steps = 0
        self._target_steps = None
        self._target_time = 0.
        self._preview_stop = None
        self._contributions = [0, 0, 0, 0]
        self._counts = {'fields': 0, 'fft_transforms': 0, 'analysis_calls': 0, 'snapshot_writes': 0,
                        'sot_rhs_calls': 0, 'preview_starts': 0}
        self.restore_grade = 'fresh'
        self._validate_sampling()

    @property
    def time(self):
        return self._time

    @property
    def model(self):
        return self._model

    @property
    def solver(self):
        return self._solver

    @property
    def m(self):
        with self._state_lock:
            return self._m.copy()

    @property
    def outputs(self):
        return self._outputs

    @property
    def current(self):
        return self._current

    @property
    def labels(self):
        return self.model.labels

    def _validate_sampling(self):
        if self.solver.dt is None:
            if self.outputs.every is not None or self.outputs.snapshots is not None or self.outputs.snapshot_times:
                raise ValueError('configure dynamic dt before physical-time sampling')
            return
        for value in self.outputs.snapshot_times:
            step_count(value, self.solver.dt, 'snapshot_times')
        for key in ('every', 'snapshots'):
            value = getattr(self.outputs, key)
            if value is not None and step_count(value, self.solver.dt, 'outputs.' + key) < 1:
                raise ValueError('sampling interval must include at least one step')

    def check(self, *, duration=None):
        import sys
        from .native import ROOT
        if sys.platform != 'darwin':
            raise RuntimeError('the qualified script-native release requires macOS')
        name = 'libfm.dylib' if isinstance(self.model, FM) else 'libfim.dylib'
        if duration is not None:
            if self.solver.dt is None:raise ValueError('run requires an explicit dynamic dt')
            step_count(duration, self.solver.dt, 'duration')
            if any(value > duration for value in self.outputs.snapshot_times):
                raise ValueError('snapshot_times must lie inside the planned duration')
        if not (ROOT / 'build-script-api' / name).is_file():
            raise RuntimeError('native bindings missing; run tools/build_script_api.py')
        import ctypes
        ctypes.CDLL(str(ROOT / 'build-script-api' / name))
        return {'valid': True, 'managed_fields': 0, 'managed_Model_calls': 0, **self.describe()}

    def describe(self):
        return {**describe(self.model), 'time_s': self.time, 'solver': asdict(self.solver),
                'current': asdict(self.current) if self.current else None,
                'outputs': {**asdict(self.outputs), 'directory': str(self.outputs.directory) if self.outputs.directory is not None else None},
                'restore_grade': self.restore_grade, 'metrics': self.metrics(),
                'ordinary_continuation': 'fixed RK4; integer steps; fresh field at operation boundaries',
                'fm_static': 'unsupported', 'resource_budgets': None,
                'grid_input': {'requested_size_m': self.model.mesh.requested_size,
                               'effective_size_m': self.model.mesh.size,
                               'roundoff_m': tuple(a-b for a,b in zip(self.model.mesh.requested_size or self.model.mesh.size,self.model.mesh.size))}}

    parameters = describe

    def metrics(self):
        values = dict(self._counts)
        if self._native is not None:
            for key in ('fields', 'fft_transforms'):
                values[key] += self._native.counters()[key]
        values['subfields'] = len(self.labels)
        values['demag_cache_allocated'] = bool(self._native is not None and any(type(t).__name__ == 'Demag' for t in self.model.energy))
        counts = list(self._contributions)
        if self._native is not None:
            counts = [a+b for a,b in zip(counts, self._native.counters()['contribution_branches'])]
        names = ('exchange', 'anisotropy', 'zeeman', 'demag') if isinstance(self.model, FM) else ('exchange_and_Anh', 'onsite_Ah', 'DMI', 'anisotropy')
        values['contribution_branches'] = dict(zip(names, counts))
        values['contribution_counter_scope'] = 'actual native contribution branches; FiM main owner energy/A work, FM single field'
        return values

    def _engine(self):
        if self._native is None:
            self._native = Native(self.model, self._m, self._kernel_override)
        return self._native

    def _drop_engine(self):
        if self._native is not None:
            for key in ('fields', 'fft_transforms'):
                self._counts[key] += self._native.counters()[key]
            self._contributions = [a+b for a,b in zip(self._contributions,self._native.counters()['contribution_branches'])]
            self._native.close()
            self._native = None
        self._field = self._energy = None

    def _evaluate(self, m):
        return self._engine().evaluate(m)

    def _current_evaluation(self):
        if self._field is None:
            self._field, self._energy = self._evaluate(self._m)
        if self.energy_origin is None:
            self.energy_origin = float(self._energy.sum())
        return self._field, self._energy

    def _rhs(self, m, field):
        active = self.current is not None and any(self.current.J) and (self.current.xi_A != 0 or self.current.xi_B != 0) and np.any(np.cross(self.current.incident_direction, self.current.J))
        if active:
            self._counts['sot_rhs_calls'] += 1
        return self._engine().rhs(m, field, self.current if active else None)

    def _residual(self, m, H):
        transverse = H - m * np.sum(m * H, axis=-1, keepdims=True)
        return np.linalg.norm(transverse, axis=-1).reshape(len(self.labels), -1).max(axis=1)

    def _rk4_step(self):
        m = self._m
        dt = self.solver.dt
        e1, _ = self._evaluate(m)
        k1, p1 = self._rhs(m, e1)
        e2, _ = self._evaluate(m + k1 * (dt / 2))
        k2, p2 = self._rhs(m + k1 * (dt / 2), e2)
        e3, _ = self._evaluate(m + k2 * (dt / 2))
        k3, p3 = self._rhs(m + k2 * (dt / 2), e3)
        e4, _ = self._evaluate(m + k3 * dt)
        k4, p4 = self._rhs(m + k3 * dt, e4)
        candidate = m + (k1 + k2 * 2 + k3 * 2 + k4) * (dt / 6)
        norm = np.linalg.norm(candidate, axis=-1)
        if not np.isfinite(candidate).all() or not np.isfinite(norm).all() or np.any(norm == 0):
            raise FloatingPointError('nonfinite/zero RK4 candidate; previous accepted state retained')
        if self.current is not None and (self.current.xi_A != 0 or self.current.xi_B != 0) and np.any(np.cross(self.current.incident_direction, self.current.J)) and np.max(np.abs(norm - 1)) > 1e-8:
            raise FloatingPointError('driven raw unit-length gate 1e-8 exceeded')
        candidate /= norm[..., None]
        H, energy = self._evaluate(candidate)
        p = (p1 + 2 * p2 + 2 * p3 + p4) * (dt / 6)
        if not np.isfinite(p).all():
            raise FloatingPointError('nonfinite integrated power')
        next_dissipation = self.dissipation + p[:len(self.labels)]
        next_work = self.drive_work + p[2:2 + len(self.labels)]
        if not np.isfinite(next_dissipation).all() or not np.isfinite(next_work).all() or not math.isfinite(self.time + dt):
            raise FloatingPointError('cumulative quantity or time overflow')
        # Commit only after the entire candidate and its field have passed.
        with self._state_lock:
            self._m, self._field, self._energy = candidate, H, energy
            self.dissipation = next_dissipation
            self.drive_work = next_work
            self.total_steps += 1
            self._clock += Fraction.from_float(float(dt))
            self._time = float(self._clock)
        self._sd = None

    def _begin(self, kind):
        from ..runtime import ensure_integrity
        ensure_integrity()
        if self._busy:
            raise RuntimeError('recursive or concurrent operations are not supported')
        segment = {'id': str(uuid.uuid4()), 'index': len(self.segments), 'kind': kind,
                   'run_id': self.run_id, 'parent_segment': self.segments[-1]['id'] if self.segments else None,
                   't_start': self.time, 't_end': None, 'status': 'running', 'steps': 0,
                   'model': describe(self.model), 'current': asdict(self.current) if self.current else None,
                   'events_before': len(self.events)}
        if self.outputs.directory is not None:
            if self._root is None:
                self._root = Path(self.outputs.directory).resolve()
                self._root.parent.mkdir(parents=True, exist_ok=True)
                self._root.mkdir(exist_ok=False)
            folder = self._root / f'segment-{segment["index"]:05d}'
            folder.mkdir(exist_ok=False)
            segment['directory'] = folder.name
        self.segments.append(segment)
        self._busy = True
        self._restored_pending = False
        self._stage_started = time.monotonic()
        self._active_steps = 0
        return segment

    def _observe(self, segment, step, *, final=False):
        every = step_count(self.outputs.every, self.solver.dt, 'every') if self.outputs.every else 1
        if self.outputs.scalars and (final or step % every == 0):
            row = {'segment_id': segment['id'], 'step': step, 'requested_time_s': self.time,
                   'actual_time_s': self.time, 'boundary': 'end' if final else 'start' if step == 0 else 'accepted'}
            H, energy = self._current_evaluation()
            for key in self.outputs.scalars:
                if key == 'time':
                    row['time_s'] = self.time
                elif key == 'energy':
                    row.update(energy_columns(energy, self.model))
                elif key in ('mean_m', 'residual', 'mxh', 'dissipation', 'drive_work'):
                    values = self._m.reshape(len(self.labels), -1, 3).mean(axis=1) if key == 'mean_m' else self._residual(self._m, H) if key in ('residual','mxh') else getattr(self, key)
                    if key == 'mxh':
                        ms = [getattr(self.model.material, label).Ms for label in self.labels] if len(self.labels)>1 else [self.model.material.Ms]
                        values = self._residual(self._m,H)/np.array(ms)
                    for i, label in enumerate(self.labels):
                        if key == 'mean_m':
                            for axis, value in zip('xyz', values[i]):
                                row[f'mean_m_{label}_{axis}'] = float(value)
                        else:
                            row[f'{key}_{label}'] = float(values[i])
            self.records.append(row)
            if 'directory' in segment:
                path = (self._root / segment['directory']) / 'scalars.csv'
                exists = path.exists()
                with path.open('a', newline='') as stream:
                    writer = csv.DictWriter(stream, fieldnames=list(row))
                    if not exists:
                        writer.writeheader()
                    writer.writerow(row)
        interval = step_count(self.outputs.snapshots, self.solver.dt, 'snapshots') if self.outputs.snapshots else None
        event_steps = {step_count(value, self.solver.dt, 'snapshot_times') for value in self.outputs.snapshot_times}
        save_frame = (interval is not None and step % interval == 0) or step in event_steps or (final and (interval is not None or event_steps))
        if save_frame and 'directory' in segment:
            np.savez((self._root / segment['directory']) / f'm-{step:012d}.npz', m=self._m, time_s=self.time, labels=self.labels)
            self._counts['snapshot_writes'] += 1
        if self.outputs.analysis and final:
            segment['analysis'] = {name: self.analyze(name) for name in self.outputs.analysis}

    def _finish(self, segment, status, steps, error=None, residual=None):
        self._stage_elapsed = max(0., time.monotonic()-self._stage_started)
        segment.update(status=status, t_end=self.time, steps=steps, error=error)
        self.last_result = RunResult(status, segment['t_start'], self.time, steps,
                                     tuple(map(float, residual)) if residual is not None else None, error, segment['id'])
        self._busy = False
        self._active_steps = steps
        self._publish_preview(force=True, residual=residual)
        if 'directory' in segment:
            from .persistence import atomic_json
            saved = self.save_state((self._root / segment['directory']) / 'accepted.state')
            segment['accepted_state'] = saved
            atomic_json((self._root / segment['directory']) / 'result.json', segment)
            atomic_json(self._root / 'segments.json', {'schema': 'micromagnetics-segments-v1', 'run_id': self.run_id,
                        'parent': self.parent, 'segments': self.segments, 'events': self.events})
        return self.last_result

    def run(self, *, duration: float) -> RunResult:
        if self.solver.dt is None:raise ValueError('run requires an explicit dynamic dt')
        self._validate_sampling()
        count = step_count(duration, self.solver.dt, 'duration')
        if any(value > duration for value in self.outputs.snapshot_times):
            raise ValueError('snapshot_times must lie inside the requested stage duration')
        segment = self._begin('rk4')
        self._preview_stop = None
        self._target_steps = count
        self._target_time = self.time + count*self.solver.dt
        accepted = 0
        try:
            self._algorithm = 'rk4'
            self._current_evaluation()
            self._observe(segment, 0)
            self._publish_preview(force=True)
            if self.outputs.preview:
                self._start_preview()
            for _ in range(count):
                self._rk4_step()
                accepted += 1
                self._active_steps = accepted
                self._publish_preview()
                self._observe(segment, accepted)
            self._observe(segment, accepted, final=True)
            return self._finish(segment, 'completed', accepted)
        except KeyboardInterrupt:
            return self._finish(segment, 'cancelled', accepted, 'user cancellation; last accepted state retained')
        except Exception as error:
            self._finish(segment, 'failed', accepted, f'{type(error).__name__}: {error}')
            raise

    def relax(self, *, method, stop: MaxTransverseField):
        if method != 'sdesc' or isinstance(self.model, FM):
            raise NotImplementedError('only FiM sdesc is qualified; FM static relaxation is not supported')
        if not isinstance(stop, MaxTransverseField):
            raise TypeError('stop must be MaxTransverseField')
        if self.current is not None:
            raise ValueError('turn off current explicitly before conservative static relaxation')
        if self._strict and self._sd is not None and self._sd['criterion'] != asdict(stop):
            raise ValueError('strict static continuation requires the checkpoint stop criterion; branch first')
        segment = self._begin('sdesc')
        self._preview_stop = asdict(stop)
        self._target_steps = None
        accepted = 0
        origin = None
        change_committed = False
        def commit_static_change():
            nonlocal change_committed
            if not change_committed and origin is not None and self._energy is not None:
                self._record_static_change(origin)
                change_committed = True
        try:
            self._algorithm = 'sdesc'
            H, energy = self._current_evaluation()
            origin = float(energy.sum())
            if self.outputs.preview:
                self._start_preview()
            self._publish_preview(force=True)
            if self._sd is None:
                self._sd = {'prev': np.zeros_like(self._m), 'gradient': np.zeros_like(self._m),
                            'controls': np.array([0., 0., 0., 0., 1e-15]), 'consecutive': 0,
                            'criterion': asdict(stop), 'residual_checked': False}
            criterion = asdict(stop)
            if self._sd['criterion'] != criterion:
                if self._strict:
                    raise ValueError('strict static continuation requires the checkpoint stop criterion; branch first')
                self._sd.update(criterion=criterion, consecutive=0, residual_checked=False)
            while True:
                residual = self._residual(self._m, H)
                self._active_steps = accepted
                if not self._sd['residual_checked']:
                    self._sd['consecutive'] = self._sd['consecutive'] + 1 if (stop.satisfied(residual, self.model) if isinstance(stop, ResidualAndMxh) else np.max(residual) <= stop.tolerance) else 0
                    self._sd['residual_checked'] = True
                self._publish_preview(residual=residual)
                if getattr(self, '_notebook_static_observe', False):
                    self._observe(segment, accepted)
                if self._sd['consecutive'] >= stop.consecutive:
                    break
                candidate, gradient, controls = self._engine().sd_step(self._m, H, self._sd['prev'], self._sd['gradient'], self._sd['controls'])
                candidate = directions(candidate, self._m.shape)
                next_H, next_energy = self._evaluate(candidate)
                previous = self._m
                self._m, H, energy = candidate, next_H, next_energy
                self._field, self._energy = H, energy
                self._sd.update(prev=previous, gradient=gradient, controls=controls, residual_checked=False)
                accepted += 1
            commit_static_change()
            self._observe(segment, accepted, final=True)
            segment['stop'] = asdict(stop)
            return self._finish(segment, 'converged', accepted, residual=residual)
        except KeyboardInterrupt:
            commit_static_change()
            return self._finish(segment, 'cancelled', accepted, 'user cancellation; last accepted state retained')
        except Exception as error:
            commit_static_change()
            self._finish(segment, 'failed', accepted, f'{type(error).__name__}: {error}')
            raise

    def _record_static_change(self, before):
        after = float(self._energy.sum())
        self.energy_changes += after - before
        self.events.append({'kind': 'static_change', 'time_s': self.time, 'energy_before_J': before,
                            'energy_after_J': after, 'delta_energy_J': after - before,
                            'physical_time_advanced': False, 'dynamical_loss_added': False})

    def set_field(self, *, H_ext=None, B_ext=None):
        if self._strict:
            raise ValueError('strict-restored trajectory cannot change parameters; create an ordinary state branch')
        term = Zeeman(H_ext=H_ext, B_ext=B_ext)
        model = replace(self.model, energy=tuple(t for t in self.model.energy if not isinstance(t, Zeeman)) + (term,))
        self._change_model(model, 'field_switch')

    def set_outputs(self, outputs: Outputs):
        if self._busy or not isinstance(outputs, Outputs):
            raise ValueError('output changes require Outputs at a stage boundary')
        if self._root is not None and outputs.directory is not None and Path(outputs.directory).resolve() != self._root:
            raise ValueError('an existing experiment output root is immutable; use a branch for another directory')
        previous = self._outputs
        self._outputs = outputs
        try:
            self._validate_sampling()
        except Exception:
            self._outputs = previous
            raise

    def set_solver(self, solver: RK4):
        if self._busy or self._strict:
            raise ValueError('solver changes require an ordinary stage boundary')
        if not isinstance(solver, RK4):
            raise NotImplementedError('only fixed RK4 is supported')
        previous = self._solver
        self._solver = solver
        try:
            self._validate_sampling()
        except Exception:
            self._solver = previous
            raise
        self.events.append({'kind': 'solver_switch', 'time_s': self.time,
                            'before': asdict(previous), 'after': asdict(solver)})
        self._sd = None

    def set_current(self, current: FiMSOT | None):
        if self._busy:
            raise RuntimeError('current changes are allowed only at stage boundaries')
        if self._strict:
            raise ValueError('strict-restored trajectory cannot change current; branch first')
        if current is not None and (not isinstance(current, FiMSOT) or isinstance(self.model, FM)):
            raise TypeError('only explicit FiMSOT on FiM is supported; None disables it')
        self.events.append({'kind': 'current_switch', 'time_s': self.time,
                            'before': asdict(self.current) if self.current else None,
                            'after': asdict(current) if current else None, 'delta_energy_J': 0.})
        self._current = current
        self._sd = None

    def _change_model(self, model, kind):
        if self._busy:
            raise RuntimeError('model changes are allowed only at stage boundaries')
        _, old_energy = self._current_evaluation()
        before = float(old_energy.sum())
        old_model = self.model
        self._drop_engine()
        self._model = model
        try:
            H, E = self._evaluate(self._m)
        except BaseException:
            self._drop_engine()
            self._model = old_model
            raise
        self._field, self._energy = H, E
        after = float(E.sum())
        self.energy_changes += after - before
        self.events.append({'kind': kind, 'time_s': self.time, 'before': describe(old_model),
                            'after': describe(model), 'energy_before_J': before,
                            'energy_after_J': after, 'delta_energy_J': after - before})
        self._sd = None

    def branch(self, *, name, clock='inherit', model=None, outputs=None):
        if not isinstance(name, str) or not name or clock not in ('inherit', 'zero'):
            raise ValueError('branch requires a nonempty name and clock inherit/zero')
        target = model if model is not None else self.model
        if type(target) is not type(self.model) or target.mesh != self.model.mesh:
            raise ValueError('model/grid/boundary conversions require a new experiment')
        initial = self._m[0] if isinstance(target, FM) else {label: self._m[i] for i, label in enumerate(self.labels)}
        child = Simulation(model=target, initial=initial, solver=self.solver, outputs=outputs)
        child.parent = {'run_id': self.run_id, 'state_time_s': self.time, 'name': name, 'clock': clock,
                        'parent_model': describe(self.model), 'child_model': describe(target)}
        child._current = self.current
        child._time = self.time if clock == 'inherit' else 0.
        child._clock = self._clock if clock == 'inherit' else Fraction(0)
        if target == self.model and clock == 'inherit':
            child.dissipation = self.dissipation.copy()
            child.drive_work = self.drive_work.copy()
            child.energy_origin = self.energy_origin
            child.energy_changes = self.energy_changes
        child.events.append({'kind': 'branch', 'source': child.parent,
                             'cumulative_baseline': 'inherited' if target == self.model and clock == 'inherit' else 'new'})
        return child

    def initialize(self, initial):
        if self.segments or self.time or self._strict:
            raise ValueError('reinitializing a running experiment requires a new Simulation')
        self._m = generate(self.model, initial)
        self._drop_engine()
        self._sd = None
        self.energy_origin = None

    def analyze(self, name='structure'):
        if name != 'structure':
            raise ValueError('only structure analysis is supported')
        self._counts['analysis_calls'] += 1
        from .persistence import structure
        return structure(self)

    def execute(self, stages):
        if not isinstance(stages, (tuple, list)):
            raise TypeError('stages must be a sequence of descriptors')
        from .stages import Evolve, Relax, SetField, SetCurrent, SetSolver, SetOutputs, SaveState
        allowed = (Evolve, Relax, SetField, SetCurrent, SetSolver, SetOutputs, SaveState)
        if any(not isinstance(stage, allowed) for stage in stages):
            raise TypeError('unknown stage descriptor')
        results = []
        for index, stage in enumerate(stages):
            result = stage.execute(self)
            results.append(result)
            if isinstance(result, RunResult) and result.status not in ('completed', 'converged'):
                self.events.append({'kind': 'protocol_stopped', 'time_s': self.time,
                                    'stage_index': index, 'status': result.status,
                                    'remaining_stages': len(stages) - index - 1})
                break
        return results

    def save_state(self, path):
        from .persistence import save
        return save(self, path, strict=False)

    def save_checkpoint(self, path):
        from .persistence import save
        return save(self, path, strict=True)

    @classmethod
    def load_state(cls, path, *, outputs=None):
        from .persistence import load
        return load(path, strict=False, outputs=outputs)

    @classmethod
    def resume_checkpoint(cls, path, *, outputs=None):
        from .persistence import load
        return load(path, strict=True, outputs=outputs)

    def export_magnetization(self, paths):
        from .persistence import export_ovf
        return export_ovf(self, paths)

    def _publish_preview(self, *, force=False, residual=None):
        observer = getattr(self, '_progress_observer', None)
        if observer is not None:
            observer(force=force, residual=residual)
        if self._preview is not None and self._preview.server is not None:
            try:
                self._preview.publish(force=force, residual=residual)
            except Exception as error:
                warnings.warn(f'Preview update unavailable; science continues: {error}', RuntimeWarning)

    def preview(self):
        self._start_preview()

    def _start_preview(self):
        if self._preview is None or self._preview.server is None:
            from .preview import LivePreview
            self._preview = LivePreview.acquire(self, self.outputs.preview_port)
            self._counts['preview_starts'] += int(self._preview.server is not None)

    def close(self):
        if self._preview is not None:
            self._preview.close()
            self._preview = None
        self._drop_engine()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def __del__(self):
        if hasattr(self, '_native'):
            self.close()
