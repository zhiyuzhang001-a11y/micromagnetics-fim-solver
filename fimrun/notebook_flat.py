"""Notebook stage outputs: preflight, exclusive ownership and recoverable replacement.

No native field evaluation is performed by this adapter. Staged output is retained
on publication failure; the exception gives its recovery path.
"""
from dataclasses import asdict, replace
import csv
import hashlib
import io
import json
import os
from pathlib import Path
import tempfile
import time
import zipfile
import numpy as np
from .micromagnetics.simulation import Outputs, RK4, ResidualAndMxh, step_count, energy_columns

UNSET = object()
SCHEMA = 'notebook-flat-v1'


def name_component(value):
    if (not isinstance(value, str) or not value or value in ('.', '..') or
        Path(value).name != value or '/' in value or '\\' in value or
        any(ord(c) < 32 for c in value) or value.startswith('.')):
        raise ValueError('output_name must be a nonhidden filename component')
    return value


def safe_root(path):
    path = Path(path).expanduser().absolute()
    for part in (path, *path.parents):
        if part.is_symlink():raise ValueError('output_dir cannot contain symlinks')
    return path.resolve()


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def inventory(paths):
    result = {}
    for p in paths:
        if p.is_symlink():raise ValueError('output symlinks are forbidden: '+str(p))
        if p.is_dir():
            result[p.name+'/'] = None
            for child in sorted(p.rglob('*')):
                if child.is_symlink() or not child.is_file():
                    raise ValueError('unexpected nested directory or link: '+str(child))
                result[p.name+'/'+child.name] = digest(child)
        elif p.is_file():result[p.name] = digest(p)
        elif p.exists():raise ValueError('unsupported output object: '+str(p))
    return result


def publish_exclusive(source, target):
    """Never replace a destination created after preflight (files or directories)."""
    if source.is_file():
        os.link(source,target)
        source.unlink()
        return
    target.mkdir(exist_ok=False)
    created=[]
    try:
        for child in source.iterdir():
            os.link(child,target/child.name);created.append(target/child.name)
    except BaseException:
        for child in created:child.unlink()
        target.rmdir()
        raise


def withdraw_published(target, source):
    if target.is_file():
        os.link(target,source);target.unlink()
    else:
        # Source directory is retained until the whole family is published.
        if inventory([target])!=inventory([source]):
            raise RuntimeError('published directory changed; recovery must preserve both copies')
        for child in target.iterdir():child.unlink()
        target.rmdir()


def metadata(path):
    with zipfile.ZipFile(path) as z:
        body = z.read('manifest.json')
        if hashlib.sha256(body).hexdigest() != z.read('manifest.sha256').decode():
            raise ValueError('state manifest checksum mismatch')
        return json.loads(body).get('notebook_flat')


def annotate(path, value):
    from .micromagnetics.persistence import atomic_bytes
    with zipfile.ZipFile(path) as z:entries={n:z.read(n) for n in z.namelist()}
    manifest=json.loads(entries['manifest.json']);manifest['notebook_flat']=value
    body=json.dumps(manifest,sort_keys=True,allow_nan=False).encode()
    entries['manifest.json']=body;entries['manifest.sha256']=hashlib.sha256(body).hexdigest().encode()
    stream=io.BytesIO()
    with zipfile.ZipFile(stream,'w',compression=zipfile.ZIP_STORED) as z:
        for n,b in entries.items():z.writestr(n,b)
    atomic_bytes(path,stream.getvalue())


class FlatOutputs:
    def __init__(self, core, root, *, output_name='experiment', every=None,
                 scalars=('time','mean_m'), magnetization=True):
        self.core=core;self.root=safe_root(root)
        name_component(output_name)
        if type(magnetization) is not bool:raise TypeError('magnetization must be bool')
        Outputs(scalars=scalars,every=every)
        if every is not None and (core.solver.dt is None or step_count(every,core.solver.dt,'every') < 1):
            raise ValueError('every must include at least one step')
        self.settings=dict(output_name=output_name,scalars=scalars,magnetization=magnetization)
        self.cadences={'rk4':every,'sdesc':None}
        self.metrics={'io_s':0.,'published_bytes':0,'stages':0}
        self.pending=None
        self.original_begin=core._begin;self.original_finish=core._finish
        core._notebook_static_observe=True
        core._begin=self.begin;core._observe=self.observe;core._finish=self.finish
        core._notebook_snapshot_format='ovf' if magnetization else None
        core._outputs=replace(core.outputs,directory=None,every=None,snapshots=None,snapshot_times=())
        # Explicit manual saves also retain output policy for ordinary/strict restore.
        for name in ('save_state','save_checkpoint'):
            method=getattr(core,name)
            def saving(method):
                def save(path):
                    receipt=method(path)
                    annotate(path,{'schema':SCHEMA,**self.settings,'cadences':dict(self.cadences)})
                    return {**receipt,'sha256':digest(Path(path))}
                return save
            setattr(core,name,saving(method))

    def propose(self, kind, *, dt=UNSET, duration=None, output_name=UNSET,
                every=UNSET, scalars=UNSET, magnetization=UNSET, stop=None):
        core=self.core
        proposed=core.solver if dt is UNSET or dt is None else RK4(dt=dt)
        if proposed != core.solver and core._strict:
            raise ValueError('strict restored simulation cannot change dt')
        config=dict(self.settings)
        for key,value in [('output_name',output_name),('scalars',scalars),('magnetization',magnetization)]:
            if value is not UNSET:config[key]=value
        name_component(config['output_name'])
        if type(config['magnetization']) is not bool:raise TypeError('magnetization must be bool')
        Outputs(scalars=config['scalars'])
        cadence=self.cadences[kind] if every is UNSET else every
        if kind=='rk4':
            if proposed.dt is None:raise ValueError('run requires dt until dynamics has been configured')
            step_count(duration,proposed.dt,'duration')
            if cadence is not None and step_count(cadence,proposed.dt,'every') < 1:
                raise ValueError('every must include at least one dynamic step')
        else:
            from .micromagnetics.model import FM
            if isinstance(core.model,FM):raise NotImplementedError('FM static relaxation is not supported')
            if core.current is not None:raise ValueError('turn off current before static relaxation')
            if cadence is not None and (type(cadence) is not int or cadence < 1):
                raise ValueError('static every must be a positive accepted-iteration integer or None')
            if core._strict and core._sd is not None and core._sd['criterion']!=asdict(stop):
                raise ValueError('strict static continuation requires the checkpoint stop criterion')
        config.update(kind=kind,every=cadence,dt=proposed.dt)
        root=safe_root(self.root)
        n=config['output_name'];targets=[root/(n+'.csv'),root/(n+'_ovf'),root/(n+'.state')]
        before=inventory(targets)
        if before:
            state=targets[-1]
            if not state.is_file():raise ValueError('existing output ownership cannot be verified: '+str(state))
            owner=metadata(state)
            if not owner or owner.get('schema')!=SCHEMA or owner.get('output_name')!=n:
                raise ValueError('existing output does not belong to this output_name')
            actual=inventory(targets[:2])
            if actual!=owner.get('inventory'):
                raise ValueError('existing outputs changed or contain foreign files; preserve them and choose a new output_name')
            from .confirmation import confirm_overwrite
            if not confirm_overwrite(targets):return None
        # Lock after confirmation. Collision never starts computation or changes config.
        root.mkdir(parents=True,exist_ok=True)
        lock=root/('.'+n+'.lock')
        try:fd=os.open(lock,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
        except FileExistsError:raise RuntimeError('output is locked; preserve recovery files and choose a new name: '+str(lock)) from None
        os.close(fd)
        try:
            if inventory(targets)!=before:raise RuntimeError('outputs changed during confirmation')
            work=Path(tempfile.mkdtemp(prefix=n+'-running-',dir=root))
        except BaseException:
            lock.unlink();raise
        return dict(config=config,solver=proposed,targets=targets,before=before,work=work,lock=lock,
                    rows={},frames=set(),committed={},started=time.monotonic())

    def activate(self,pending):
        core=self.core
        # All scientifically failing validation has completed before this commit.
        if pending['solver']!=core.solver:core.set_solver(pending['solver'])
        self.settings={k:pending['config'][k] for k in ('output_name','scalars','magnetization')}
        self.cadences[pending['config']['kind']]=pending['config']['every']
        core._notebook_snapshot_format='ovf' if self.settings['magnetization'] else None
        self.pending=pending

    def begin(self,kind):
        if self.pending is None or self.pending['config']['kind']!=kind:
            raise RuntimeError('stage output requires preflight')
        segment=self.original_begin(kind)
        segment['notebook_output']={**self.pending['config'],'schema':SCHEMA}
        self.progress(segment, 'running')
        return segment

    def progress(self, segment, status, error=None):
        """Publish only fully written frame pairs; never invoke the solver."""
        from .micromagnetics.persistence import atomic_bytes
        p=self.pending
        value={'schema':'notebook-output-progress-v1', 'status':status,
               'error':str(error) if error is not None else None,
               'run_id':self.core.run_id, 'segment_id':segment['id'],
               'stage':segment['kind'], 'labels':list(self.core.labels),
               'time_s':self.core.time, 'output_name':p['config']['output_name'],
               'frames':[p['committed'][i] for i in sorted(p['committed'])]}
        body=json.dumps(value,sort_keys=True,allow_nan=False).encode()
        atomic_bytes(p['work']/'progress.json',body)

    def observe(self,segment,step,*,final=False):
        p=self.pending;c=p['config'];cadence=c['every']
        interval=(step_count(cadence,c['dt'],'every') if c['kind']=='rk4' else cadence) if cadence is not None else None
        if not final and (interval is None or step % interval):return
        start=time.monotonic();core=self.core;n=c['output_name'];work=p['work']
        if c['scalars']:
            row={'segment_id':segment['id'],'stage':c['kind'],'iteration':step if c['kind']=='sdesc' else '',
                 'step':step,'time_s':core.time,'status':segment['status'] if final else 'accepted'}
            H,energy=core._field,core._energy
            for key in c['scalars']:
                if key=='time':continue
                if key=='energy':row.update(energy_columns(energy,core.model))
                else:
                    values=(core._m.reshape(len(core.labels),-1,3).mean(axis=1) if key=='mean_m' else
                            core._residual(core._m,H) if key in ('residual','mxh') and H is not None else
                            [None]*len(core.labels) if key in ('residual','mxh') else getattr(core,key))
                    for i,label in enumerate(core.labels):
                        if key=='mean_m':
                            for axis,v in zip('xyz',values[i]):row[f'mean_m_{label}_{axis}']=float(v)
                        else:
                            divisor=(getattr(core.model.material,label).Ms if len(core.labels)>1 else core.model.material.Ms) if key=='mxh' else 1.
                            row[f'{key}_{label}']=float(values[i])/divisor if values[i] is not None else ''
            replacing=step in p['rows']
            p['rows'][step]=row
            path=work/(n+'.csv')
            exists=path.exists()
            with path.open('w' if replacing else 'a',newline='') as stream:
                writer=csv.DictWriter(stream,fieldnames=list(row))
                if replacing or not exists:writer.writeheader()
                if replacing:writer.writerows(p['rows'].values())
                else:writer.writerow(row)
        if c['magnetization'] and step not in p['frames']:
            from .micromagnetics.persistence import export_ovf
            folder=work/(n+'_ovf');folder.mkdir(exist_ok=True)
            paths={label:folder/f'{c["kind"]}-{step:012d}_{label}.ovf' for label in core.labels}
            export_ovf(core,paths)
            # OVF comments carry real time/iteration without another visible JSON.
            for path in paths.values():
                text=path.read_text()
                label=next(label for label,target in paths.items() if target==path)
                ms=getattr(core.model.material,label).Ms if len(core.labels)>1 else core.model.material.Ms
                desc=(f'boris_metadata_version=1; time_s={core.time!r}; stage={c["kind"]}; accepted_index={step}; '
                      f'quantity=unit_direction; run_id={core.run_id}; segment_id={segment["id"]}; '
                      f'boundary={core.model.mesh.boundary}; mirrors={",".join(map(str,core.model.mesh.mirrors))}; Ms_Apm={ms!r}')
                text=text.replace('# Begin: Header', '# Begin: Header\n# Desc: '+desc,1)
                path.write_text(text)
            p['committed'][step]={'accepted_index':step,'time_s':core.time,
                'files':{label:{'path':str(path.relative_to(work)), 'sha256':digest(path)}
                         for label,path in paths.items()}}
            p['frames'].add(step);core._counts['snapshot_writes']+=1
        self.progress(segment, 'finalizing' if final else 'running')
        self.metrics['io_s']+=time.monotonic()-start

    def finish(self,segment,status,steps,error=None,residual=None):
        try:
            return self._finish(segment,status,steps,error,residual)
        except BaseException as exc:
            # A final state/archive error must not hide previously committed frames.
            try:self.progress(segment,'failed',exc)
            except BaseException:pass  # Preserve the primary storage error.
            raise RuntimeError(f'output failed ({type(exc).__name__}: {exc}); saved output directory: {self.pending["work"]}') from exc

    def _finish(self,segment,status,steps,error=None,residual=None):
        p=self.pending
        if p.get('finishing'):
            segment.update(status='failed',error=error)
            self.core.last_result=replace(self.core.last_result,status='failed',error=error)
            self.core._publish_preview(force=True, residual=residual)
            self.progress(segment, 'failed', error)
            return self.core.last_result
        p['finishing']=True
        result=self.original_finish(segment,status,steps,error,residual)
        core=self.core;n=p['config']['output_name'];work=p['work'];state=work/(n+'.state')
        # Try final observation and state serialization independently. Failure of
        # either preserves all prior committed frames and still attempts the other.
        observation_error=None
        try:self.observe(segment,steps,final=True)
        except BaseException as exc:observation_error=exc
        save_started=time.monotonic()
        core.save_state(state)
        self.metrics['io_s']+=time.monotonic()-save_started
        if observation_error is not None:
            raise RuntimeError(f'final output failed ({type(observation_error).__name__}: {observation_error}); accepted state retained: {state}') from observation_error
        annotation_started=time.monotonic()
        annotate(state,{'schema':SCHEMA,**p['config'],'cadences':self.cadences,
                        'inventory':inventory([work/(n+'.csv'),work/(n+'_ovf')])})
        self.metrics['io_s']+=time.monotonic()-annotation_started
        start=time.monotonic()
        backup=work/'previous';backup.mkdir();moved=[];published=[]
        expected_new=inventory([work/target.name for target in p['targets']])
        try:
            safe_root(self.root)
            if inventory(p['targets'])!=p['before']:raise RuntimeError('output changed while computing; refusing replacement')
            for target in p['targets']:
                if target.exists():os.rename(target,backup/target.name);moved.append(target)
            for target in p['targets']:
                source=work/target.name
                if source.exists():
                    # A competing newly created destination is never overwritten.
                    if target.exists() or target.is_symlink():raise FileExistsError(str(target))
                    publish_exclusive(source,target);published.append(target)
        except BaseException as exc:
            # Restore old family; preserve new accepted-state artifacts for recovery.
            for target in reversed(published):
                if target.exists():
                    current=inventory([target])
                    if any(expected_new.get(key)!=value for key,value in current.items()):
                        raise RuntimeError(f'published output changed; preserve recovery data: {work}')
                    withdraw_published(target,work/target.name)
            for target in reversed(moved):
                if not target.exists():os.rename(backup/target.name,target)
            raise RuntimeError(f'output publication failed ({type(exc).__name__}: {exc}); accepted state and recovery data: {work}') from exc
        else:
            self.metrics['published_bytes']+=sum(f.stat().st_size for target in p['targets'] for f in ([target] if target.is_file() else target.rglob('*') if target.is_dir() else []) if f.is_file())
            import shutil
            shutil.rmtree(work)
            self.metrics['stages']+=1
            self.pending=None
        finally:
            p['lock'].unlink(missing_ok=True)
            self.metrics['io_s']+=time.monotonic()-start
        return result

    def abort_prebegin(self,p):
        if not self.core._busy and self.pending is p and (not self.core.segments or self.core.segments[-1]['status']!='running'):
            # Keep a completed/failed stage's staged artifacts on any output error.
            p['lock'].unlink(missing_ok=True)
            self.pending=None
