"""Small storage/lifetime helpers; scientific operations stay on Simulation."""
from contextlib import contextmanager
from dataclasses import replace
from functools import wraps
import hashlib
import inspect
import json
import os
from pathlib import Path
import sys
import tempfile
from .micromagnetics import Simulation, Outputs, RunResult, run_directory
from .micromagnetics.model import describe
from . import notebook_flat
from . import notebook_output  # Include the adapter in the first identity snapshot.

NOTEBOOK_API_VERSION = '1.3'


def module_identity(core_dir):
    root = Path(core_dir).resolve()
    modules = {}
    for name, module in list(sys.modules.items()):
        if name != 'fimrun' and not name.startswith('fimrun.'):
            continue
        path = Path(module.__file__).resolve()
        expected = root.joinpath(*name.split('.'))
        if path not in (expected.with_suffix('.py'), expected / '__init__.py'):
            raise RuntimeError('Module source mismatch; restart the kernel with the intended project: ' + name)
        modules[name] = {'id': id(module), 'file': str(path),
                         'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
    simulation_file = str(Path(inspect.getfile(Simulation)).resolve())
    helper_file = str(Path(inspect.getfile(NotebookSession)).resolve())
    if simulation_file != str(root/'fimrun/micromagnetics/simulation.py') or helper_file != str(root/'fimrun/notebook.py'):
        raise RuntimeError('Class source mismatch; restart the kernel')
    return {'modules': modules, 'Simulation': simulation_file, 'NotebookSession': helper_file,
            'notebook_api': NOTEBOOK_API_VERSION}


class CellStopped(RuntimeError):
    """A noncontinuable scientific result must also stop notebook execution."""

    def _render_traceback_(self):
        return ['CellStopped: ' + str(self)]


def summary(result: RunResult):
    if not isinstance(result, RunResult):
        raise TypeError('summary requires a RunResult')
    value = {'status': result.status, 'accepted_steps': result.steps,
             'start_s': result.t_start, 'end_s': result.t_end,
             'residual_Apm': result.residual_Apm}
    if result.status not in ('completed', 'converged'):
        value['error'] = result.error
        print(json.dumps(value))
        detail = '; ' + result.error if result.error else ''
        raise CellStopped(result.status + detail + '; last accepted state retained; choose any continuation explicitly')
    return value


def _model_hash(model):
    return hashlib.sha256(json.dumps(describe(model), sort_keys=True).encode()).hexdigest()[:12]


def configuration_summary(model, active=None):
    return {'configuration': 'Draft for a new experiment; active simulation unchanged',
            'draft_model': _model_hash(model), 'cells': model.mesh.cells,
            'active_run': active.run_id if active is not None else None,
            'active_model': _model_hash(active.model) if active is not None else None}


class NotebookSession:
    def __init__(self, sim, directory):
        self.sim = sim
        self.directory = directory
        self.trajectory = directory / 'trajectory'
        self.states = directory / 'states'
        self.closed = False
        self._guard_operations()

    def _guard_operations(self):
        # Only session-owned instances are guarded; the accepted core class is unchanged.
        readonly = {'check', 'describe', 'parameters', 'metrics'}
        def guarded(method):
            @wraps(method)
            def operation(*args, **kwargs):
                if self.closed:
                    raise RuntimeError('Notebook session is closed; create or load a new session')
                return method(*args, **kwargs)
            return operation
        for name in dir(Simulation):
            if name.startswith('_') or name in readonly or name == 'close':
                continue
            method = getattr(self.sim, name)
            if callable(method):setattr(self.sim, name, guarded(method))
        original_close = self.sim.close
        @wraps(original_close)
        def close():
            if self.sim.segments and self.sim.segments[-1]['status'] == 'running':
                raise RuntimeError('Finish or interrupt the current operation before closing the session')
            original_close()
            self.closed = True
        self.sim.close = close

    @staticmethod
    def _available(previous):
        if previous is not None and (not isinstance(previous, NotebookSession) or not previous.closed):
            raise RuntimeError('A session already exists; keep using sim, or explicitly close it before a new experiment')
        if previous is not None:
            previous.close()

    def preview(self, sim):
        if self.closed or sim is not self.sim:
            raise RuntimeError('Preview requires this open session and its current sim')
        self.sim.preview()
        return self.info()

    @staticmethod
    def _claim(directory):
        directory.parent.mkdir(parents=True, exist_ok=True)
        directory.mkdir(exist_ok=False)
        (directory / 'states').mkdir(exist_ok=False)

    @classmethod
    def start(cls, *, model, initial, solver, parent, name='experiment', output_settings=None, previous=None):
        cls._available(previous)
        directory = run_directory(parent, name).resolve()
        outputs = Outputs(directory=directory / 'trajectory', **(output_settings or {}))
        sim = Simulation(model=model, initial=initial, solver=solver, outputs=outputs)
        try:
            sim.check()
            cls._claim(directory)
            return cls(sim, directory)
        except BaseException:
            sim.close()
            raise

    @classmethod
    def load(cls, path, *, parent, name='restored', checkpoint=False, previous=None):
        cls._available(previous)
        if type(checkpoint) is not bool:
            raise TypeError('checkpoint requires bool')
        sim = Simulation.resume_checkpoint(path) if checkpoint else Simulation.load_state(path)
        try:
            directory = run_directory(parent, name).resolve()
            target = directory / 'trajectory' if sim.outputs.directory is not None else None
            sim.set_outputs(replace(sim.outputs, directory=target))
            cls._claim(directory)
            return cls(sim, directory)
        except BaseException:
            sim.close()
            raise

    def outputs(self, **settings):
        if self.closed:
            raise RuntimeError('Session is closed')
        return Outputs(directory=self.trajectory, **settings)

    def save(self, name, *, checkpoint=False):
        if self.closed:
            raise RuntimeError('Session is closed')
        if type(checkpoint) is not bool or not isinstance(name, str) or not name or name in ('.', '..') or Path(name).name != name:
            raise ValueError('save requires one filename and a bool checkpoint flag')
        if self.states.is_symlink() or not self.states.is_dir():
            raise ValueError('Session state directory has changed')
        path = self.states / name
        if path.exists() or path.is_symlink() or path.resolve().parent != self.states.resolve():
            raise FileExistsError('State destination exists or is outside the session state directory')
        # Publish without replacing a competing destination, even after serialization.
        with tempfile.TemporaryDirectory(prefix='.save-', dir=self.states) as folder:
            temporary = Path(folder) / 'state'
            receipt = self.sim.save_checkpoint(temporary) if checkpoint else self.sim.save_state(temporary)
            os.link(temporary, path)
        return {**receipt, 'path': str(path.resolve())}

    def info(self):
        return {'run_id': self.sim.run_id, 'model': _model_hash(self.sim.model),
                'time_s': self.sim.time, 'dt_s': self.sim.solver.dt,
                'directory': str(self.directory), 'closed': self.closed}

    def close(self):
        if self.sim.segments and self.sim.segments[-1]['status'] == 'running':
            raise RuntimeError('Finish or interrupt the current operation before closing the session')
        self.sim.close()
        self.closed = True


# Retain active facades until explicit close; rerunning a creation cell cannot
# orphan an experiment by replacing its last notebook variable.
import threading
import unicodedata

_ACTIVE_NOTEBOOKS = {}
_NOTEBOOK_LOCK = threading.RLock()
_NO_DURATION = object()


def _experiment_key(results, name):
    if not isinstance(name, str) or not name or name in ('.', '..') or Path(name).name != name:
        raise ValueError('name must be one nonempty filename component')
    parent = Path(results).expanduser().resolve()
    return parent, unicodedata.normalize('NFD', str(parent / name)).casefold()


def _sampling_preflight(outputs, dt, duration=_NO_DURATION):
    from .micromagnetics.simulation import step_count
    for key in ('every', 'snapshots'):
        value = getattr(outputs, key)
        if value is not None and step_count(value, dt, key) < 1:
            raise ValueError('sampling interval must include at least one step')
    for value in outputs.snapshot_times:
        step_count(value, dt, 'snapshot_times')
    if duration is not _NO_DURATION:
        step_count(duration, dt, 'duration')
        if any(value > duration for value in outputs.snapshot_times):
            raise ValueError('snapshot_times must lie inside the requested duration')


class NotebookResult:
    """Small, evaluation-free result; cancellation is raised before construction."""
    __slots__ = ('_value',)

    def __init__(self, value):
        from types import MappingProxyType
        object.__setattr__(self, '_value', MappingProxyType(dict(value)))

    def __setattr__(self, name, value):
        raise AttributeError('NotebookResult is read-only')

    def __getattr__(self, name):
        try:
            return self._value[name]
        except KeyError:
            raise AttributeError(name) from None

    def __repr__(self):
        text = f"{self.status}: {self.accepted_steps} steps, {self.start_s:g} -> {self.end_s:g} s"
        if self.residual_Apm is not None:
            text += f", residual={self.residual_Apm} A/m"
        return text


class NotebookSimulation:
    """One notebook object; SI inputs and the qualified core algorithms unchanged.

    dt and results are required. every/snapshots are physical intervals in s;
    omitted sampling/preview are disabled. name identifies one active experiment
    per canonical results directory. Repeated creation resets an idle experiment
    by default; replace=False preserves duplicate protection. Running is rejected.
    """

    def __init__(self, *, model, initial, dt, results, name='experiment',
                 every=None, snapshots=None, scalars=(), snapshot_times=(),
                 preview=False, preview_port=8766, replace=True, snapshot_format='npz'):
        from .micromagnetics import RK4
        if type(replace) is not bool:
            raise TypeError('replace requires bool')
        from .notebook_output import snapshot_format as validate_format
        snapshot_format = validate_format(snapshot_format)
        parent, key = _experiment_key(results, name)
        solver = RK4(dt=dt)
        settings = dict(every=every, snapshots=snapshots, scalars=scalars,
                        snapshot_times=snapshot_times, preview=preview, preview_port=preview_port)
        _sampling_preflight(Outputs(directory=parent / 'trajectory', **settings), dt)
        if snapshot_format is None:
            settings.update(snapshots=None, snapshot_times=())
        with _NOTEBOOK_LOCK:
            previous = _ACTIVE_NOTEBOOKS.get(key)
            if previous is not None:
                if not replace:
                    self._require_unused(key)
                previous._require_idle()
            # No old state/resources are changed until every candidate preflight
            # and independent directory claim has succeeded.
            session = NotebookSession.start(model=model, initial=initial, solver=solver,
                                            parent=parent, name=name, output_settings=settings)
            try:
                from .notebook_output import install
                install(session.sim, snapshot_format)
            except BaseException:
                session.close()
                raise
            self._adopt(session, key, previous=previous)

    @staticmethod
    def _require_unused(key):
        if key in _ACTIVE_NOTEBOOKS:
            raise RuntimeError('This experiment is active; keep using sim, or close it before creating/loading another')

    def _adopt(self, session, key, *, previous=None):
        self._session, self._key = session, key
        self._in_operation = False
        if previous is not None:
            retained = previous._session.sim._preview if session.sim.outputs.preview and hasattr(self,'_flat_outputs') else None
            if retained is not None:
                previous._session.sim._preview = None
            try:
                previous.close()
            except BaseException:
                if retained is not None:previous._session.sim._preview = retained
                session.close()
                raise
            rebind_error = None
            if retained is not None:
                session.sim._preview = retained
                try:
                    retained.rebind(session.sim)
                except (Exception, KeyboardInterrupt) as error:
                    rebind_error = error
            session.sim.events.append({'kind': 'notebook_reset', 'time_s': 0.,
                                       'previous_run_id': previous.run_id,
                                       'reset_to_initial': True})
            _ACTIVE_NOTEBOOKS[key] = self
            # The scientific replacement is committed. A display failure must
            # not make the caller lose the new sim on the RHS of assignment.
            if session.sim.outputs.preview:
                try:
                    if rebind_error is not None:raise rebind_error
                    session.preview(session.sim)
                except (Exception, KeyboardInterrupt) as error:
                    display = session.sim._preview
                    try:
                        if display is not None:
                            display.close()
                    except (Exception, KeyboardInterrupt) as cleanup_error:
                        # Keep the reference so close() can retry resource cleanup.
                        error = RuntimeError(str(error) + '; preview cleanup pending: ' + str(cleanup_error))
                    else:
                        session.sim._preview = None
                    import warnings
                    try:
                        warnings.warn('Experiment reset completed; preview unavailable: ' + str(error), RuntimeWarning)
                    except Warning:
                        pass
            return
        try:
            if session.sim.outputs.preview:
                session.preview(session.sim)
        except BaseException:
            session.close()
            raise
        _ACTIVE_NOTEBOOKS[key] = self

    def _open(self):
        if self.closed:
            raise RuntimeError('Simulation is closed or replaced; use the new sim object')
        return self._session.sim

    def _require_idle(self):
        core = self._open()
        if self._in_operation or core._busy or (core.segments and core.segments[-1]['status'] == 'running'):
            raise RuntimeError('Simulation is busy; finish or interrupt its operation before resetting or changing it')
        return core

    @contextmanager
    def _idle_operation(self):
        with _NOTEBOOK_LOCK:
            core = self._require_idle()
            self._in_operation = True
        try:
            yield core
        finally:
            with _NOTEBOOK_LOCK:
                self._in_operation = False

    def _operation(self, operation):
        core = self._open()
        previous = core.last_result
        try:
            result = operation()
        except Exception as error:
            if core.last_result is not previous and core.last_result is not None and core.last_result.status == 'failed':
                try:
                    # The outer output error carries recovery locations; custom
                    # Notebook tracebacks intentionally hide chained exceptions.
                    summary(replace(core.last_result, error=f'{type(error).__name__}: {error}'))
                except CellStopped as stopped:
                    raise stopped from error
            raise
        return NotebookResult(summary(result))

    def run(self, duration, *, dt=None):
        """Continue for duration [s]; optional dt [s] persists for later calls."""
        from .micromagnetics import RK4
        with self._idle_operation() as core:
            proposed = core.solver if dt is None else RK4(dt=dt)
            _sampling_preflight(core.outputs, proposed.dt, duration)
            if proposed != core.solver:
                core.set_solver(proposed)
            return self._operation(lambda: core.run(duration=duration))

    def relax(self, tolerance, *, consecutive=1):
        """Conservative FiM sdesc; tolerance [A/m], physical time unchanged."""
        from .micromagnetics import MaxTransverseField
        with self._idle_operation() as core:
            stop = MaxTransverseField(tolerance, consecutive=consecutive)
            # The core rejects active current, FM and strict criterion changes.
            return self._operation(lambda: core.relax(method='sdesc', stop=stop))

    def set_current(self, current):
        """Set supported FiMSOT, or explicitly disable it with None."""
        with self._idle_operation() as core:
            core.set_current(current)

    def set_field(self, *, H_ext=None, B_ext=None):
        """H_ext [A/m] or B_ext [T], following the core Zeeman convention."""
        with self._idle_operation() as core:
            core.set_field(H_ext=H_ext, B_ext=B_ext)

    def preview(self):
        """Show the same unified3D viewer without a field evaluation."""
        with self._idle_operation() as core:
            self._session.preview(core)

    def save(self, name, *, checkpoint=False):
        """Save a new filename under this experiment's states directory."""
        with self._idle_operation():
            return self._session.save(name, checkpoint=checkpoint)

    def export_ovf(self, name='magnetization'):
        """Export a new A/B OVF2 Text packet of unit directions; no evaluation."""
        if not isinstance(name, str) or not name or name in ('.', '..') or Path(name).name != name:
            raise ValueError('OVF export requires one new filename component')
        with self._idle_operation() as core:
            from .notebook_output import export_packet
            return export_packet(core, self.directory/'exports'/name)

    @classmethod
    def load(cls, path, *, results, name='restored', checkpoint=False):
        """New experiment from state; inherit saved dt/output/current settings."""
        parent, key = _experiment_key(results, name)
        with _NOTEBOOK_LOCK:
            cls._require_unused(key)
            from .notebook_output import install, saved_format
            fmt = saved_format(path)
            session = NotebookSession.load(path, parent=parent, name=name, checkpoint=checkpoint)
            try:
                install(session.sim, fmt)
            except BaseException:
                session.close()
                raise
            instance = cls.__new__(cls)
            instance._adopt(session, key)
            return instance

    def close(self):
        """Close resources and release this active name; safe to call twice."""
        with _NOTEBOOK_LOCK:
            if not self.closed:
                self._require_idle()
            self._session.close()
            if _ACTIVE_NOTEBOOKS.get(self._key) is self:
                del _ACTIVE_NOTEBOOKS[self._key]

    @property
    def closed(self):
        return self._session.closed

    @property
    def m(self):
        return self._session.sim.m

    @property
    def time(self):
        return self._session.sim.time

    @property
    def snapshot_format(self):
        return self._session.sim._notebook_snapshot_format

    @property
    def dt(self):
        return self._session.sim.solver.dt

    @property
    def dissipation(self):
        return self._session.sim.dissipation.copy()

    @property
    def drive_work(self):
        return self._session.sim.drive_work.copy()

    @property
    def run_id(self):
        return self._session.sim.run_id

    @property
    def directory(self):
        return self._session.directory

    def metrics(self):
        return self._session.sim.metrics()

    def __repr__(self):
        state = 'closed' if self.closed else 'ready'
        return f'NotebookSimulation({state}, time={self.time:g} s, dt={self.dt:g} s, results={str(self.directory)!r})'


def _save_alias(every,new,*,default):
    if every is not notebook_flat.UNSET and new is not notebook_flat.UNSET:
        raise TypeError('every and the new save parameter cannot both be supplied, including None')
    if every is not notebook_flat.UNSET:
        import warnings
        warnings.warn('every is deprecated; use save_interval for dynamics or save_every_steps for static relaxation',FutureWarning,stacklevel=3)
        return every
    return default if new is notebook_flat.UNSET else new


_LegacyNotebookSimulation = NotebookSimulation


class NotebookSimulation(_LegacyNotebookSimulation):
    """Sequential Notebook API with fixed output_dir and per-stage output_name.

    New calls use output_dir. The earlier results/name constructor remains an
    explicitly legacy path; its saved data and A/m tolerance retain their meaning.
    """
    def __init__(self, *, model, initial, dt, output_dir=notebook_flat.UNSET,
                 output_name='experiment', save_interval=notebook_flat.UNSET, every=notebook_flat.UNSET, scalars=notebook_flat.UNSET,
                 magnetization=True, preview=False, preview_port=8766, replace=True, **legacy):
        if 'save_every_steps' in legacy:raise TypeError('constructor save_every_steps is unsupported; set it on relax')
        if output_dir is notebook_flat.UNSET:
            if save_interval is not notebook_flat.UNSET:raise TypeError('save_interval requires output_dir, not legacy results/name')
            if 'results' not in legacy:
                raise TypeError('output_dir is required')
            if output_name!='experiment' or magnetization is not True:
                raise TypeError('Do not mix output_name/magnetization with legacy results/name')
            super().__init__(model=model,initial=initial,dt=dt,every=None if every is notebook_flat.UNSET else every,scalars=() if scalars is notebook_flat.UNSET else scalars,
                             preview=preview,preview_port=preview_port,replace=replace,**legacy)
            return
        if legacy:raise TypeError('Use output_dir/output_name/save_interval/magnetization; unsupported: '+', '.join(legacy))
        every=_save_alias(every,save_interval,default=None)
        if type(replace) is not bool:raise TypeError('replace must be bool')
        from .micromagnetics import RK4
        root=notebook_flat.safe_root(output_dir)
        if scalars is notebook_flat.UNSET:scalars=('time','mean_m')
        _,key=_experiment_key(root,'__flat_experiment__')
        with _NOTEBOOK_LOCK:
            previous=_ACTIVE_NOTEBOOKS.get(key)
            if previous is not None:
                if not replace:self._require_unused(key)
                previous._require_idle()
            core=Simulation(model=model,initial=initial,solver=RK4(dt=dt),
                            outputs=Outputs(preview=preview,preview_port=preview_port))
            try:
                adapter=notebook_flat.FlatOutputs(core,root,output_name=output_name,every=every,
                                                  scalars=scalars,magnetization=magnetization)
                core.check()
                root.mkdir(parents=True,exist_ok=True)
                session=NotebookSession(core,root);session.states=root
                self._flat_outputs=adapter
                self._adopt(session,key,previous=previous)
            except BaseException:
                core.close();raise

    def _flat_stage(self,kind,*,stop=None,**settings):
        from .runtime import ensure_integrity
        ensure_integrity()
        with self._idle_operation() as core:
            adapter=self._flat_outputs
            proposed=adapter.propose(kind,stop=stop,**settings)
            if proposed is None:
                raise CellStopped('Output overwrite declined; no calculation or configuration change')
            try:
                adapter.activate(proposed)
                duration=settings.get('duration')
                return self._operation(lambda:core.run(duration=duration) if kind=='rk4' else core.relax(method='sdesc',stop=stop))
            finally:
                adapter.abort_prebegin(proposed)

    def run(self,duration,*,dt=None,output_name=notebook_flat.UNSET,save_interval=notebook_flat.UNSET,every=notebook_flat.UNSET,
            scalars=notebook_flat.UNSET,magnetization=notebook_flat.UNSET):
        if not hasattr(self,'_flat_outputs'):
            if save_interval is not notebook_flat.UNSET:raise TypeError('save_interval requires output_dir, not legacy results/name')
            if any(v is not notebook_flat.UNSET for v in (output_name,every,scalars,magnetization)):
                raise TypeError('Per-stage outputs require the output_dir constructor')
            return super().run(duration,dt=dt)
        every=_save_alias(every,save_interval,default=notebook_flat.UNSET)
        return self._flat_stage('rk4',dt=dt,duration=duration,output_name=output_name,every=every,
                                scalars=scalars,magnetization=magnetization)

    def relax(self,*args,mxh=notebook_flat.UNSET,residual=1.,consecutive=1,
              output_name=notebook_flat.UNSET,save_every_steps=notebook_flat.UNSET,every=notebook_flat.UNSET,
              scalars=notebook_flat.UNSET,magnetization=notebook_flat.UNSET,**legacy):
        if not hasattr(self,'_flat_outputs'):
            if save_every_steps is not notebook_flat.UNSET or every is not notebook_flat.UNSET:raise TypeError('new static save parameters require output_dir')
            if mxh is not notebook_flat.UNSET:raise TypeError('mxh requires the output_dir constructor')
            return super().relax(*args,consecutive=consecutive,**legacy)
        if args or legacy or mxh is notebook_flat.UNSET:
            raise TypeError('Use relax(mxh=dimensionless_limit, residual=A_per_m_limit, ...); old positional/tolerance A/m is not mxh')
        every=_save_alias(every,save_every_steps,default=notebook_flat.UNSET)
        stop=notebook_flat.ResidualAndMxh(tolerance=residual,consecutive=consecutive,mxh=mxh)
        return self._flat_stage('sdesc',stop=stop,output_name=output_name,every=every,
                                scalars=scalars,magnetization=magnetization)

    @classmethod
    def load(cls,path,*,output_dir=notebook_flat.UNSET,output_name='restored',checkpoint=False,**legacy):
        if output_dir is notebook_flat.UNSET:return super().load(path,checkpoint=checkpoint,**legacy)
        if legacy:raise TypeError('Use output_dir/output_name for a new-layout restore')
        if type(checkpoint) is not bool:raise TypeError('checkpoint must be bool')
        root=notebook_flat.safe_root(output_dir)
        _,key=_experiment_key(root,'__flat_experiment__')
        with _NOTEBOOK_LOCK:
            cls._require_unused(key)
            core=Simulation.resume_checkpoint(path) if checkpoint else Simulation.load_state(path)
            try:
                saved=notebook_flat.metadata(path) or {}
                adapter=notebook_flat.FlatOutputs(core,root,output_name=output_name,
                        scalars=tuple(saved.get('scalars',core.outputs.scalars)),
                        magnetization=saved.get('magnetization',True))
                cadences=saved.get('cadences',{'rk4':None,'sdesc':None})
                # Validate saved settings without claiming files or running science.
                if set(cadences)!={'rk4','sdesc'}:raise ValueError('invalid saved output cadence')
                if cadences['rk4'] is not None:
                    _sampling_preflight(Outputs(every=cadences['rk4']),core.solver.dt)
                if cadences['sdesc'] is not None and (type(cadences['sdesc']) is not int or cadences['sdesc']<1):
                    raise ValueError('invalid static cadence')
                adapter.cadences=dict(cadences)
                root.mkdir(parents=True,exist_ok=True)
                session=NotebookSession(core,root);session.states=root
                instance=cls.__new__(cls);instance._flat_outputs=adapter
                instance._adopt(session,key)
                return instance
            except BaseException:
                core.close();raise

    @property
    def output_dir(self):return self.directory

    @property
    def output_name(self):
        if not hasattr(self,'_flat_outputs'):raise AttributeError('legacy constructor has no stage output_name')
        return self._flat_outputs.settings['output_name']

    def metrics(self):
        values=super().metrics()
        if hasattr(self,'_flat_outputs'):values['notebook_output']=dict(self._flat_outputs.metrics)
        return values

    def __repr__(self):
        if not hasattr(self,'_flat_outputs'):return super().__repr__()
        state='closed' if self.closed else 'ready'
        return f'NotebookSimulation({state}, time={self.time:g} s, dt={self.dt:g} s, output_dir={str(self.output_dir)!r}, output_name={self.output_name!r})'
