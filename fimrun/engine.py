"""Opt-in orchestration of unchanged backends; --check is read-only."""
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
import argparse
import datetime
import json
import os
import shutil
import subprocess
import sys
import time
import uuid
from .api import Case
from .bridge import legacy, ROOT
from .configuration import validate, build_cases, path_value, ConfigError
from .protocol import atomic, read, sha, digest, binding, validate_manifest
from .qualification import (qualified, kernel_binding, ledger_snapshot, verify_bindings,
                            LineageLock)
from .resources import Guard, output_size, stop
from .preview import PreviewSession

@dataclass
class Plan:
    root: Path
    cases: dict
    source: dict | None
    ledger: Path
    inherited: int
    cap: int
    kernel: dict
    bindings: dict
    forecasts: dict
    minimum_fields: int
    preview_log_bytes: int
    def summary(self):
        return {'valid': True, 'managed_Model_calls': 0, 'managed_fields': 0,
                'root': str(self.root), 'cases': self.cases, 'kernel': self.kernel,
                'input_bindings': self.bindings, 'lineage': str(self.ledger),
                'S0': self.inherited, 'cumulative_cap': self.cap,
                'minimum_new_fields': self.minimum_fields, 'forecasts': self.forecasts,
                'preview_log_budget_bytes':self.preview_log_bytes,
                'drive_ready': self.source is not None if 'drive' in self.cases else False,
                'drive_status': 'qualified_source' if self.source else 'pending_preparation' if 'drive' in self.cases else 'not_requested'}

def minimum_fields(kind, c):
    n = c['dynamic']['steps']
    if kind == 'prepare': return 5*n+5 # dynamic native 1+5N, static initial1, independent3
    saved = set(range(0,n+1,c['output']['save_every'])) | {0,n} | set(c['output']['event_steps'])
    return 5*n+1+len(saved)

def preflight(case: Case, *, script):
    validate(case)
    base = Path(script).resolve().parent
    if os.name != 'posix': raise ConfigError('runtime: owned process groups/file locks require POSIX')
    source_hint = None
    if case.workflow == 'drive':
        report_path = path_value('prepared.report',case.prepared.report,base)
        source_hint = {'checkpoint':report_path.parent/'static/checkpoint.bin',
                       'metadata':report_path.parent/'static/checkpoint.bin.json'}
    root, prep, drive = build_cases(case,base,1000000,source_hint)
    if root.exists() or root.is_symlink(): raise ConfigError('output.directory: already exists; choose a new directory')
    if not root.parent.is_dir(): raise ConfigError('output.directory: parent must already exist')
    active = drive if case.workflow == 'drive' else prep
    kernel = kernel_binding(active)
    source = qualified(report_path,drive,kernel['sha256']) if source_hint else None
    inherited = source['spent'] if source else 0
    cap = inherited+case.budget.new_fields
    if cap > 1000000: raise ConfigError('budget.new_fields: S0+F exceeds backend cumulative cap 1000000; cannot clamp/reset')
    root,prep,drive = build_cases(case,base,cap,source)
    cases = {}
    if case.workflow != 'drive': cases['prepare']=prep
    if case.workflow != 'relax': cases['drive']=drive
    b=legacy(); forecasts={}; bindings={kernel['path']:kernel['sha256'],**kernel['evidence_bindings']}
    for kind,c in cases.items():
        binary=Path(c['output']['bins'])/('fim_user' if kind=='prepare' else 'fim_drive')
        if not binary.is_file() or not os.access(binary,os.X_OK): raise ConfigError('runtime.bins: missing executable '+str(binary))
        bindings[str(binary.resolve())]=sha(binary)
        if kind=='prepare': forecasts[kind]=b['run_user_workflow'].preflight(c)[3]
        elif source: forecasts[kind]=b['run_current_workflow'].preflight(c)[3]
        else:
            # Future CP cannot be validated yet. Use the backend's exact output forecast formula.
            n=c['dynamic']['steps']; frames=n//c['output']['save_every']+len(c['output']['event_steps'])+3
            size=(frames*3+8)*48*__import__('math').prod(c['geometry']['n'])+n*1024
            forecasts[kind]={'pending_preparation':True,'output_bytes_forecast':size,'CP_verified':False}
    if source: bindings.update(source['bindings'])
    for c in cases.values():
        for key in ('ovf_A','ovf_B'):
            if c['initial'].get(key): bindings[c['initial'][key]]=sha(c['initial'][key])
    estimate=sum(v.get('snapshot_bytes_upper_estimate',v.get('output_bytes_forecast',0)) for v in forecasts.values())
    estimate+=Path(kernel['path']).stat().st_size+65536 # private kernel + small orchestration files
    preview_log_bytes=case.preview.log_bytes if case.preview.enabled else 0
    if estimate+preview_log_bytes>case.budget.output_bytes: raise ConfigError('budget.output_bytes: whole-chain forecast plus reserved preview log exceeds root cap')
    minimum=sum(minimum_fields(k,c) for k,c in cases.items())
    if minimum>case.budget.new_fields: raise ConfigError('budget.new_fields: below minimum chain fields including independent checks')
    ledger=Path(source['ledger']) if source else root/'prepare.resource-costs.jsonl'
    return Plan(root,cases,source,ledger,inherited,cap,kernel,bindings,forecasts,minimum,preview_log_bytes)

class Manifest:
    def __init__(self, plan):
        b=binding(plan.root,str(uuid.uuid4()),plan.cases)
        first='prepare_dynamic' if 'prepare' in plan.cases else 'drive'
        self.path=plan.root/'run.json'
        self.value={'schema':'boris-run-v1','version':1,'binding':b,'binding_sha256':digest(b),
                    'revision':0,'state':'running','phase':first,'stage_epoch':1}
    def publish(self,state,phase=None):
        v=self.value
        if phase and phase!=v['phase']: v['phase']=phase; v['stage_epoch']+=1
        s=v['binding']['allowed_stages'][v['phase']]
        v.update(state=state,active_case=s['case_id'],active_output=s['output'],
                 revision=v['revision']+1,updated_at=datetime.datetime.now(datetime.timezone.utc).isoformat())
        validate_manifest(v)
        atomic(self.path,v)

def stage_worker(kind,c,plan,guard,manifest):
    request=plan.root/f'{kind}.request.json'; result=plan.root/f'{kind}.result.json'
    atomic(request,{'kind':kind,'case':c,'bindings':plan.bindings,'kernel_sha256':plan.kernel['sha256'],'result':str(result)})
    proc=None
    try:
        with (plan.root/f'{kind}.stdout').open('wb') as out, (plan.root/f'{kind}.stderr').open('wb') as err:
            proc=subprocess.Popen([sys.executable,'-m','fimrun._worker',str(request)],cwd=ROOT,
                                  stdout=out,stderr=err,start_new_session=True)
            while proc.poll() is None:
                guard.check()
                phase='drive' if kind=='drive' else 'prepare_static' if (plan.root/'prepare/static').exists() else 'prepare_dynamic'
                final_dir=plan.root/('drive/driven' if kind=='drive' else 'prepare/static')
                state='verifying' if (final_dir/'result.json').exists() else 'running'
                if (phase,state)!=(manifest.value['phase'],manifest.value['state']): manifest.publish(state,phase)
                time.sleep(.05)
        if proc.returncode: raise RuntimeError(f'{kind} backend failed (exit {proc.returncode}); see {kind}.stderr/report.json')
        return read(result)
    finally: stop(proc,include_orphans=True) # cleanup owned native descendants even if worker leader died

def private_kernel(plan):
    """Copy an already verified payload; get() will hit cache, never launch a builder."""
    b=legacy(); case=next(iter(plan.cases.values())); key=b['kernel_cache'].key_data(case)
    cache=plan.root/'kernel-cache'; folder=cache/b['user_case'].digest(key); folder.mkdir(parents=True)
    payload=folder/'kernel.f64'; shutil.copyfile(plan.kernel['path'],payload)
    if sha(payload)!=plan.kernel['sha256']: raise ValueError('kernel changed during copy')
    b['kernel_cache'].validate_kernel(case,payload,samples=None)
    meta=deepcopy(plan.kernel['qualification'])
    meta['copied_from']={'payload':plan.kernel['path'],'evidence_bindings':plan.kernel['evidence_bindings']}
    atomic(folder/'manifest.json',meta) # retain original qualification and provenance verbatim
    for c in plan.cases.values(): c['output']['cache']=str(cache)

def execute(case, *, script, executor=stage_worker):
    started=time.monotonic(); plan=preflight(case,script=script)
    guard=Guard(case.budget,started,plan.root,preview_log_bytes=plan.preview_log_bytes); guard.remaining()
    plan.root.mkdir() # atomic exclusive creation; no parents, exist_ok, overwrite or retry
    warnings=[]; reports={}; preview=None; manifest=None; failure=None; state='failed'; lock=None
    try:
        lock=LineageLock(plan.ledger); lock.__enter__()
        if plan.source and plan.ledger.exists() and ledger_snapshot(plan.ledger,plan.inherited)!=plan.inherited:
            raise ValueError('lineage advanced after preflight; rerun with fresh budget snapshot')
        verify_bindings(plan.bindings); guard.check(); private_kernel(plan)
        manifest=Manifest(plan); manifest.publish('running')
        atomic(plan.root/'plan.json',plan.summary())
        # Preview command executable/script paths are resolved relative to the user's script.
        from dataclasses import replace
        argv=list(case.preview.command); base=Path(script).resolve().parent
        for i,arg in enumerate(argv):
            if (i==0 and ('/' in arg or (base/arg).exists())) or (i>0 and not arg.startswith('-') and (base/arg).is_file()): argv[i]=str((base/arg).resolve())
        preview=PreviewSession(replace(case.preview,command=tuple(argv)),manifest.path,warnings.append); preview.start()
        for kind,c in plan.cases.items():
            phase='drive' if kind=='drive' else 'prepare_dynamic'
            manifest.publish('running',phase)
            guard.preview_pid=lambda:preview.pid
            verify_bindings(plan.bindings)
            spent=ledger_snapshot(plan.ledger,plan.inherited) if plan.ledger.exists() else plan.inherited
            if spent+minimum_fields(kind,c)>plan.cap: raise RuntimeError('remaining whole-chain field budget insufficient for next stage')
            if kind=='drive':
                if 'prepare' in reports:
                    source=qualified(plan.root/'prepare/report.json',c,plan.kernel['sha256'])
                    if Path(source['ledger'])!=plan.ledger: raise ValueError('handoff changed resource lineage')
                    plan.bindings.update(source['bindings'])
                legacy()['run_current_workflow'].preflight(c) # now actual CP, never pending
            c['resources']=guard.stage_resources(plan.cap)
            report=executor(kind,c,plan,guard,manifest)
            manifest.publish('verifying','drive' if kind=='drive' else 'prepare_static')
            module=legacy()['run_current_workflow' if kind=='drive' else 'run_user_workflow']
            good=module.successful(report) if kind=='drive' else module.requirements_met(report)
            saved=read(Path(c['output']['directory'])/'report.json')
            if saved!=report or not report.get('execution_completed') or not good: raise RuntimeError(kind+' did not pass persisted scientific/output gates')
            if Path(report['resource_ledger']).resolve()!=plan.ledger: raise ValueError('backend changed resource ledger')
            ledger_snapshot(plan.ledger,spent)
            reports[kind]=report
            if kind=='prepare': qualified(plan.root/'prepare/report.json',c,plan.kernel['sha256'])
            guard.check()
        state='completed'
    except BaseException as e:
        state='interrupted' if isinstance(e,(KeyboardInterrupt,SystemExit)) else 'failed'
        failure=f'{type(e).__name__}: {e}'
    finally:
        if preview: preview.close()
    try:
        try:
            total=legacy()['user_costs'].inspect_ledger(plan.ledger) if plan.ledger.exists() else plan.inherited
            if total<plan.inherited or total>plan.cap: raise ValueError('final resource ledger out of frozen range')
            new=total-plan.inherited
        except Exception as e:
            total=new=None; state='failed'; failure=(failure or '')+'; accounting failure: '+str(e)
        result={'state':state,'failure':failure,'S0':plan.inherited,'F':case.budget.new_fields,'C':plan.cap,
                'lineage':str(plan.ledger),'total_fields':total,'new_fields':new,'stages':list(reports),
                'science_owned_rss_peak_sampled_bytes':guard.peak_rss,'preview':preview.metrics if preview else None,
                'warnings':warnings,'wall_s':time.monotonic()-started}
        # Completion/report writes are themselves part of the budget and may fail the run.
        try:
            if state=='completed': guard.check()
            if manifest: manifest.publish(state)
            atomic(plan.root/'report.json',result)
            if state=='completed': guard.check()
        except Exception as e:
            result.update(state='failed',failure='final report/resource failure: '+str(e))
            if manifest:
                try: manifest.publish('failed')
                except OSError: pass
            try: atomic(plan.root/'report.json',result)
            except OSError: pass
        return result
    finally:
        if lock and lock.stream and not lock.stream.closed: lock.__exit__()

def cli(case, *, script):
    parser=argparse.ArgumentParser(description='Typed Boris workflow; --check starts no managed science/viewer processes')
    parser.add_argument('--check',action='store_true'); args=parser.parse_args()
    try:
        answer=preflight(case,script=script).summary() if args.check else execute(case,script=script)
        print(json.dumps(answer,indent=2,ensure_ascii=False,allow_nan=False))
        if not args.check and answer['state']!='completed': raise SystemExit(2)
    except (ValueError,OSError,RuntimeError,TimeoutError) as e:
        print('configuration/run failed: '+str(e),file=sys.stderr); raise SystemExit(2) from None
