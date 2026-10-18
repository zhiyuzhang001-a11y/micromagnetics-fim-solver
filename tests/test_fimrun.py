"""Zero-physics contracts. Ledger 'fields' here are SYNTHETIC test tokens only.
No native executable, Model, field evaluator, compiler or browser is invoked.
"""
from dataclasses import replace
import json
import io
import os
from pathlib import Path
import socket
import struct
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch,Mock
import uuid
import numpy as np
from fimrun import *
from fimrun.bridge import legacy,ROOT
from fimrun.engine import preflight,execute,Manifest
from fimrun.configuration import ConfigError,validate
from fimrun.protocol import atomic,read,sha,digest,validate_manifest,frame_matches
from fimrun.qualification import qualified,kernel_binding,ledger_snapshot,LineageLock
from fimrun.resources import Guard
from fimrun.preview import PreviewSession,check_ready

class FakeStage:
    """Synthetic persistence/ledger fixture, NOT numerical qualification evidence."""
    def __init__(self, prepare_cost=5, fail=False): self.calls=[]; self.prepare_cost=prepare_cost;self.fail=fail
    def __call__(self,kind,c,plan,guard,manifest):
        self.calls.append((kind,c['resources'].copy()))
        if self.fail: raise RuntimeError('synthetic scientific failure')
        out=Path(c['output']['directory']);out.mkdir()
        ancestor=read(c['handoff']['metadata']) if kind=='drive' else None
        if ancestor is not None:ancestor['_metadata_path']=c['handoff']['metadata']
        costs=legacy()['user_costs'].ResourceCosts(out,ancestor)
        count=2 if kind=='drive' else self.prepare_cost
        token=costs.reserve(count,c['resources']['max_fields'],'SYNTHETIC CONTRACT TOKENS')
        costs.settle(token,count)
        atomic(out/'resolved_case.json',c)
        binary=Path(c['output']['bins'])/('fim_user' if kind=='prepare' else 'fim_drive')
        atomic(out/'manifest.json',{'identity':c['identity'],'physics_sha256':c['physics_sha256'],
                                  'binary_sha256':sha(binary),'user_config':c})
        atomic(out/'kernel.json',{'payload_sha256':plan.kernel['sha256']})
        report={'execution_completed':True,'mandatory_outputs_written':True,
                'structure_goal':{'requested':'none','status':'not_requested'},
                'requested_step_sensitivity':False,'resource_ledger':str(costs.path),
                'started_fields':costs.total(),'new_fields':count}
        if kind=='prepare':
            folder=out/'static';folder.mkdir();cp=folder/'checkpoint.bin'
            n=int(np.prod(c['geometry']['n']));raw=bytearray(168+144*n)
            struct.pack_into('<QQQ',raw,0,0x3150435245535546,n,64);raw[24:88]=c['identity'].encode()
            struct.pack_into('<iii',raw,88,*c['geometry']['n'])
            m=np.zeros((2,n,3),dtype='<f8');m[0,:,2]=1.;m[1,:,2]=-1.;raw[168:168+48*n]=m.tobytes();cp.write_bytes(raw)
            atomic(str(cp)+'.json',{'schema':'user-checkpoint-v1','phase':'static',
                'checkpoint_sha256':sha(cp),'identity':c['identity'],'physics_sha256':c['physics_sha256'],
                'shape':c['geometry']['n'],'binary_sha256':sha(binary),'kernel_sha256':plan.kernel['sha256'],
                'spent_fields':costs.total(),'resource_ledger':str(costs.path)})
            report.update(static_criterion={'status':'met','independent':{'passed':True,'static_criterion_met':True}},
                          dynamic_step_sensitivity={'status':'not_checked'},
                          final_checkpoint=str(cp),final_checkpoint_metadata=str(cp)+'.json')
        else: report.update(trajectory_reached=True,independent={'passed':True})
        atomic(out/'report.json',report);return report

class Contracts(unittest.TestCase):
    def setUp(self):
        # Sandbox denies ps/loopback; supervision/HTTP receive deterministic mock IO.
        from fimrun.resources import owned_rss
        self._rss_original=owned_rss
        rss=patch('fimrun.resources.owned_rss',return_value=16*1024**2);rss.start();self.addCleanup(rss.stop)
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.script=self.root/'my_case.py';self.script.write_text('# synthetic')
        bins=self.root/'bins';bins.mkdir()
        for name in ('fim_user','fim_drive'):
            p=bins/name;p.write_text('NOT A REAL EXECUTABLE; TEST MUST NEVER LAUNCH THIS');p.chmod(0o700)
        self.case=Case(workflow='prepare_then_drive',initial=Initial(kind='uniform'),
            preparation=Preparation(dynamics=Dynamics(dt_fs=100.,T_ps=0.),max_updates=0),
            drive=Drive(dynamics=Dynamics(dt_fs=25.,T_ps=0.),times_ps=(0.,)),
            output=Output(directory='new',goal='none'),runtime=Runtime(bins='bins',cache='cache'),
            budget=Budget(new_fields=7,wall_s=20.,output_bytes=128*1024**2))
    def tearDown(self):self.tmp.cleanup()
    def prep(self):
        c=replace(self.case,workflow='relax',budget=replace(self.case.budget,new_fields=5))
        r=execute(c,script=self.script,executor=FakeStage());self.assertEqual(r['state'],'completed',r)
        return self.root/'new/prepare/report.json'
    def test_types_rejected_before_preflight(self):
        bad=[replace(self.case,mesh=Mesh(n=(True,125,1))),replace(self.case,drive=Drive(dynamics=Dynamics(dt_fs='25',T_ps=0.))),
             replace(self.case,budget=Budget(new_fields=True)),replace(self.case,field=Field(H_Apm=(0.,float('nan'),0.))),
             replace(self.case,mesh=Mesh(cell_nm=(4.,4.))),replace(self.case,output=Output(directory='x',save_every=1.5))]
        for c in bad:
            with self.subTest(c=c),self.assertRaises(ConfigError):validate(c)
        with self.assertRaisesRegex(TypeError,'unknown_field'):Mesh(unknown_field=3)
    def test_backend_physics_and_mutual_field_validation(self):
        for c in [replace(self.case,field=Field()),replace(self.case,field=Field(H_Apm=(0,0,0),mu0_H_T=(0,0,0))),
                  replace(self.case,mesh=Mesh(pbc=(1,0,0)))]:
            with self.assertRaises(ValueError):preflight(c,script=self.script)
    def test_check_zero_managed_actions_and_cwd_independent(self):
        before=set(self.root.rglob('*'));cwd=Path.cwd()
        with patch('subprocess.Popen',side_effect=AssertionError('process forbidden')),patch('webbrowser.open',side_effect=AssertionError('browser forbidden')):
            a=preflight(self.case,script=self.script).summary()
            try:
                os.chdir(self.root);b=preflight(self.case,script=self.script).summary()
            finally:os.chdir(cwd)
        self.assertEqual(a,b);self.assertEqual(before,set(self.root.rglob('*')))
        self.assertFalse(a['drive_ready']);self.assertEqual(a['drive_status'],'pending_preparation')
    def test_drive_missing_source_hard_error(self):
        with self.assertRaises(ValueError):preflight(replace(self.case,workflow='drive'),script=self.script)
        with self.assertRaises(FileNotFoundError):preflight(replace(self.case,workflow='drive',prepared=PreparedState(report='absent')),script=self.script)
    def test_two_stages_one_cap_no_double_charge(self):
        f=FakeStage();r=execute(self.case,script=self.script,executor=f)
        self.assertEqual(r['state'],'completed',r);self.assertEqual(r['new_fields'],7)
        self.assertEqual([x[1]['max_fields'] for x in f.calls],[7,7])
        self.assertLess(f.calls[1][1]['wall_s'],f.calls[0][1]['wall_s'])
        self.assertLess(f.calls[1][1]['output_bytes'],f.calls[0][1]['output_bytes'])
        self.assertEqual(read(self.root/'new/run.json')['phase'],'drive')
    def test_second_stage_budget_does_not_reset(self):
        f=FakeStage(prepare_cost=6);r=execute(self.case,script=self.script,executor=f)
        self.assertEqual(r['state'],'failed');self.assertEqual(len(f.calls),1);self.assertEqual(r['new_fields'],6)
    def test_prepare_failure_prevents_drive(self):
        f=FakeStage(fail=True);r=execute(self.case,script=self.script,executor=f)
        self.assertEqual(r['state'],'failed');self.assertEqual(len(f.calls),1)
    def test_live_lineage_total_not_CP_snapshot(self):
        report=self.prep();meta=read(self.root/'new/prepare/static/checkpoint.bin.json')
        costs=legacy()['user_costs'].ResourceCosts(self.root/'unused',meta);token=costs.reserve(3,100,'SYNTHETIC prior branch');costs.settle(token,3)
        c=replace(self.case,workflow='drive',prepared=PreparedState(report=report),output=Output(directory='drive-only',goal='none'),budget=replace(self.case.budget,new_fields=2))
        p=preflight(c,script=self.script);self.assertEqual((p.inherited,p.cap),(8,10))
        r=execute(c,script=self.script,executor=FakeStage());self.assertEqual((r['new_fields'],r['total_fields']),(2,10))
    def test_pending_reservation_and_regressed_missing_ledger(self):
        report=self.prep();md=read(self.root/'new/prepare/static/checkpoint.bin.json')
        c=replace(self.case,workflow='drive',prepared=PreparedState(report=report),output=Output(directory='later',goal='none'))
        costs=legacy()['user_costs'].ResourceCosts(self.root/'unused',md);costs.reserve(1,100,'SYNTHETIC incomplete')
        with self.assertRaisesRegex(ValueError,'unfinished'):preflight(c,script=self.script)
        Path(md['resource_ledger']).unlink()
        with self.assertRaises(FileNotFoundError):preflight(c,script=self.script)
    def test_regressed_and_damaged_ledger_rejected(self):
        report=self.prep();mdpath=self.root/'new/prepare/static/checkpoint.bin.json';md=read(mdpath);r=read(report)
        costs=legacy()['user_costs'].ResourceCosts(self.root/'regressed',None)
        md['resource_ledger']=r['resource_ledger']=str(costs.path);atomic(mdpath,md);atomic(report,r)
        c=replace(self.case,workflow='drive',prepared=PreparedState(report=report),output=Output(directory='later',goal='none'))
        with self.assertRaisesRegex(ValueError,'regressed'):preflight(c,script=self.script)
        costs.path.write_text('broken\n')
        with self.assertRaisesRegex(ValueError,'incomplete'):preflight(c,script=self.script)
    def test_legacy_source_import_once(self):
        report=self.prep();mdpath=self.root/'new/prepare/static/checkpoint.bin.json';md=read(mdpath);r=read(report)
        del md['resource_ledger'];del r['resource_ledger'];atomic(mdpath,md);atomic(report,r)
        # Existing sibling ledger has live 5 tokens. Reuse it, never import another5.
        c=replace(self.case,workflow='drive',prepared=PreparedState(report=report),output=Output(directory='legacy-drive',goal='none'),budget=replace(self.case.budget,new_fields=2))
        result=execute(c,script=self.script,executor=FakeStage())
        self.assertEqual((result['state'],result['S0'],result['total_fields']),('completed',5,7),result)
    def test_source_physics_goal_and_binary_binding(self):
        report=self.prep();r=read(report);r['structure_goal']={'requested':'single_skyrmion','status':'not_met'};atomic(report,r)
        c=replace(self.case,workflow='drive',prepared=PreparedState(report=report),output=Output(directory='later',goal='none'))
        with self.assertRaisesRegex(ValueError,'gates'):preflight(c,script=self.script)
        r['structure_goal']={'requested':'none','status':'not_requested'};atomic(report,r)
        with self.assertRaisesRegex(ValueError,'identity'):
            preflight(replace(c,field=Field(H_Apm=(0,0,0))),script=self.script)
        (self.root/'bins/fim_user').write_text('changed binary')
        with self.assertRaisesRegex(ValueError,'binary hash'):preflight(c,script=self.script)
    def test_cumulative_cap_backend_limit_is_not_clamped(self):
        report=self.prep()
        c=replace(self.case,workflow='drive',prepared=PreparedState(report=report),output=Output(directory='later',goal='none'),budget=replace(self.case.budget,new_fields=1000000))
        with self.assertRaisesRegex(ValueError,'cannot clamp'):preflight(c,script=self.script)
    def test_report_gate_and_CP_tamper(self):
        report=self.prep();original=read(report)
        for key in ('execution_completed','mandatory_outputs_written'):
            r=original.copy();r[key]=False;atomic(report,r)
            with self.assertRaisesRegex(ValueError,'gates'):qualified(report,preflight(self.case_for_new(),script=self.script).cases['prepare'],kernel_binding(preflight(self.case_for_new(),script=self.script).cases['prepare'])['sha256'])
        atomic(report,original);cp=self.root/'new/prepare/static/checkpoint.bin';raw=cp.read_bytes();cp.write_bytes(raw[:-1]+b'X')
        c=replace(self.case,workflow='drive',prepared=PreparedState(report=report),output=Output(directory='later',goal='none'))
        with self.assertRaisesRegex(ValueError,'checksum'):preflight(c,script=self.script)
    def case_for_new(self):return replace(self.case,output=Output(directory='unused',goal='none'))
    def test_no_overwrite(self):
        (self.root/'new').mkdir()
        with self.assertRaisesRegex(ValueError,'already exists'):preflight(self.case,script=self.script)
    def test_unsupported_kernel_never_generates(self):
        with self.assertRaisesRegex(ValueError,'automatic generation disabled'):
            preflight(replace(self.case,initial=Initial(kind='uniform'),mesh=Mesh(n=(126,126,1))),script=self.script)
    def test_lineage_lock_exclusion(self):
        with LineageLock(self.root/'l'):
            with self.assertRaisesRegex(ValueError,'busy'):
                with LineageLock(self.root/'l'):pass
    def test_whole_wall_and_output_guard(self):
        g=Guard(replace(self.case.budget,wall_s=.001),time.monotonic()-.01,self.root)
        with self.assertRaises(TimeoutError):g.remaining()
        g=Guard(replace(self.case.budget,output_bytes=1),time.monotonic(),self.root)
        with self.assertRaisesRegex(RuntimeError,'whole-root'):g.check()
    def test_rss_scope_excludes_preview_tree(self):
        from fimrun.resources import owned_rss
        table={1:(0,10),2:(1,20),3:(2,30),4:(1,40),5:(4,50),6:(0,1000)}
        with patch('fimrun.resources.process_table',return_value=table):
            # Imported function is the test's outer mocked sampler; use its original.
            import fimrun.resources as resources
            original=self._rss_original
            self.assertEqual(original(1,[4]),60)
    def test_manifest_mutable_state_immutable_binding_and_boundary(self):
        p=preflight(self.case,script=self.script);p.root.mkdir();m=Manifest(p);m.publish('running');h=m.value['binding_sha256']
        m.publish('verifying','prepare_static');self.assertEqual(h,m.value['binding_sha256']);validate_manifest(read(m.path))
        v=read(m.path);v['schema']='old';
        with self.assertRaises(ValueError):validate_manifest(v)
        v=read(m.path);v['binding']['run_id']=str(uuid.uuid4())
        with self.assertRaises(ValueError):validate_manifest(v)
        (p.root/'prepare').symlink_to(self.root/'bins',target_is_directory=True)
        with self.assertRaisesRegex(ValueError,'escapes'):validate_manifest(read(m.path))
    def ready_fixture(self,p,m,instance,pid=42,port=9000):
        from importlib.util import spec_from_file_location,module_from_spec
        spec=spec_from_file_location('mock_viewer',ROOT/'tests/mock_viewer.py');mod=module_from_spec(spec);spec.loader.exec_module(mod)
        from types import SimpleNamespace
        r=mod.ready(SimpleNamespace(manifest=m.path,instance=instance,port=port));r['pid']=pid;return r
    def test_ready_wrong_identity_and_old_frames(self):
        p=preflight(self.case,script=self.script);p.root.mkdir();m=Manifest(p);m.publish('running');instance=str(uuid.uuid4());r=self.ready_fixture(p,m,instance)
        check_ready(r,m.value,instance,42,9000)
        for key,value in [('run_id',str(uuid.uuid4())),('binding_sha256','0'*64),('run_root','/old400'),('case_id','drive'),('instance','old'),('schema','old')]:
            bad=dict(r);bad[key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):check_ready(bad,m.value,instance,42,9000)
        m.publish('running','drive');current=self.ready_fixture(p,m,instance)
        self.assertFalse(frame_matches(r,r,current));self.assertTrue(frame_matches(current,current,current))
    def test_preview_missing_command_and_science_failure_independent(self):
        c=replace(self.case,preview=Preview(enabled=True))
        r=execute(c,script=self.script,executor=FakeStage(fail=True))
        self.assertEqual(r['state'],'failed');self.assertTrue(r['warnings'])
    def test_preview_failure_does_not_fail_successful_science(self):
        r=execute(replace(self.case,preview=Preview(enabled=True)),script=self.script,executor=FakeStage())
        self.assertEqual(r['state'],'completed',r);self.assertTrue(r['warnings'])
    def test_report_write_failure_nonzero_state(self):
        from fimrun import engine
        real=engine.atomic
        def write(path,value):
            if Path(path).resolve()==(self.root/'new/report.json').resolve():
                with self.assertRaisesRegex(ValueError,'busy'):
                    with LineageLock(self.root/'new/prepare.resource-costs.jsonl'):pass
                raise OSError('synthetic disk full')
            return real(path,value)
        with patch('fimrun.engine.atomic',side_effect=write):r=execute(self.case,script=self.script,executor=FakeStage())
        self.assertEqual(r['state'],'failed');self.assertEqual(read(self.root/'new/run.json')['state'],'failed')
    def test_mock_preview_opens_once_across_stages(self):
        p=preflight(self.case,script=self.script);p.root.mkdir();m=Manifest(p);m.publish('running')
        port=9876
        warnings=[];opened=[]
        options=Preview(enabled=True,command=(sys.executable,str(ROOT/'tests/mock_viewer.py')),port=port,startup_s=2.)
        def browser(url):
            opened.append(url)
            if getattr(self,'browser_error',False):raise OSError('synthetic browser unavailable')
            return True
        session=PreviewSession(options,m.path,warnings.append,opener=browser)
        proc=Mock(pid=42);proc.poll.return_value=None
        def spawn(*args,**kwargs):
            raw=self.ready_fixture(p,m,session.instance,pid=42,port=port)
            self.assertEqual(kwargs['stdout'],-1) # PIPE: child can never write disk directly
            proc.stdout=io.BytesIO(json.dumps(raw).encode()+b'\n');return proc
        response=Mock();response.__enter__=Mock(return_value=response);response.__exit__=Mock(return_value=False)
        response.read.side_effect=lambda n:json.dumps(self.ready_fixture(p,m,session.instance,pid=42,port=port)).encode()
        http=Mock();http.open.return_value=response
        with patch('fimrun.preview.socket.socket') as sock,patch('fimrun.preview.subprocess.Popen',side_effect=spawn),patch('fimrun.preview.urllib.request.build_opener',return_value=http),patch('fimrun.preview.owned_rss',return_value=1024),patch('fimrun.resources.os.killpg'):
            session.start()
            try:
                until=time.monotonic()+2
                while not opened and not warnings and time.monotonic()<until:time.sleep(.01)
                self.assertEqual(len(opened),1,warnings);m.publish('running','drive');time.sleep(.12)
                self.assertEqual(len(opened),1)
            finally:session.close()
        if getattr(self,'browser_error',False):self.assertTrue(any('browser open failed' in x for x in warnings))
        else:self.assertFalse(warnings,warnings)
        proc.wait.assert_called()
    def test_browser_exception_warns_once(self):
        self.browser_error=True;self.test_mock_preview_opens_once_across_stages()
    def test_ready_timeout_stops_only_owned_mock(self):
        p=preflight(self.case,script=self.script);p.root.mkdir();m=Manifest(p);m.publish('running');warnings=[]
        session=PreviewSession(Preview(enabled=True,command=('mock',),startup_s=.08),m.path,warnings.append,opener=lambda _:self.fail('must not open'))
        proc=Mock(pid=42);proc.poll.return_value=None
        proc.stdout=io.BytesIO(b'')
        proc.wait.side_effect=lambda:setattr(proc.poll,'return_value',-9)
        with patch('fimrun.preview.socket.socket'),patch('fimrun.preview.subprocess.Popen',return_value=proc),patch('fimrun.preview.owned_rss',return_value=1024),patch('fimrun.resources.os.killpg') as kill:
            session.start();session.thread.join(2);session.close()
        self.assertTrue(any('timeout' in x for x in warnings),warnings);kill.assert_called_once()
    def test_bad_reference_cache_records_are_rejected_without_recompute(self):
        from copy import deepcopy
        p=preflight(self.case,script=self.script);c=p.cases['prepare'];kc=legacy()['kernel_cache'];key=kc.key_data(c)
        folder=Path(c['output']['cache'])/legacy()['user_case'].digest(key);folder.mkdir(parents=True)
        np.zeros((125,125,6),'<f8').tofile(folder/'kernel.f64')
        base={'key':key,'payload_sha256':sha(folder/'kernel.f64'),'source':'MPFR128-Newell/BORIS-asymptotic',
              'verification':{'engineering_reference_error':0.,'reciprocity_max':0.,'reference_samples':[{'i':0,'j':0,'error':0.,'reference_precision_drift':0.}],
              'reference_tensor_evaluations':443,'coverage':'tensor samples and effective zero block; full-kernel finite/reciprocity'}}
        records=[]
        for field,value in [('error',1.),('reference_precision_drift',1.),('error',float('inf')),('error',None)]:
            m=deepcopy(base);m['verification']['reference_samples'][0][field]=value;records.append(m)
        m=deepcopy(base);m['verification']['reference_samples']=[];records.append(m)
        m=deepcopy(base);m['verification']={'historical_reference':'arbitrary label'};records.append(m)
        m=deepcopy(base);m['source']='unknown provenance';records.append(m)
        m=deepcopy(base);m['verification']['engineering_reference_error']=1.;records.append(m)
        for m in records:
            # json writer deliberately permits Infinity to exercise strict reader rejection.
            (folder/'manifest.json').write_text(json.dumps(m))
            with self.subTest(m=m),patch.object(kc,'grid_tensor',side_effect=AssertionError('no reference re-evaluation')),self.assertRaises(ValueError):kernel_binding(c)
    def test_canonical_hash_and_private_copy_keep_qualification(self):
        from fimrun.engine import private_kernel
        p=preflight(self.case,script=self.script);p.root.mkdir();original=p.kernel['qualification']
        private_kernel(p);copied=kernel_binding(p.cases['prepare'])
        self.assertEqual(copied['qualification']['verification'],original['verification'])
        self.assertEqual(copied['qualification']['source'],original['source'])
        meta=copied['qualification'];meta['payload_sha256']='0'*64
        from fimrun.qualification import reference_record
        with self.assertRaises(ValueError):reference_record(p.cases['prepare'],meta)
    def test_existing_reviewed_fine_kernel_record_and_private_copy(self):
        from fimrun.configuration import build_cases
        from fimrun.engine import private_kernel
        from types import SimpleNamespace
        cache=ROOT.parent/'current_sot_fine250_execution_20261016/cache'
        if not cache.is_dir():self.skipTest('local reviewed fine-kernel evidence unavailable')
        c=replace(self.case,mesh=Mesh(n=(250,250,1),cell_nm=(2.,2.,3.)),runtime=replace(self.case.runtime,cache=cache))
        _,prep,_=build_cases(c,self.root,7)
        with patch.object(legacy()['kernel_cache'],'grid_tensor',side_effect=AssertionError('no tensor reference execution')):
            actual=kernel_binding(prep)
            self.assertEqual(actual['qualification']['source'],'qualified-isolated-G1-import')
            root=self.root/'private-fine';root.mkdir();plan=SimpleNamespace(root=root,cases={'prepare':prep},kernel=actual)
            private_kernel(plan);copied=kernel_binding(prep)
        self.assertEqual(copied['qualification']['verification'],actual['qualification']['verification'])
        self.assertEqual(copied['qualification']['actual_generator_source_sha256'],actual['qualification']['actual_generator_source_sha256'])
    def test_preview_reservation_is_fixed_before_science(self):
        cap=65536;p=preflight(replace(self.case,preview=Preview(enabled=True,log_bytes=cap)),script=self.script)
        self.assertEqual(p.preview_log_bytes,cap);p.root.mkdir()
        g=Guard(self.case.budget,time.monotonic(),p.root,preview_log_bytes=cap)
        before=g.stage_resources(7)['output_bytes']
        (p.root/'preview.log').write_bytes(b'x'*cap)
        self.assertEqual(before,g.stage_resources(7)['output_bytes']);g.check()
    def test_ready_then_4MiB_log_is_bounded_and_science_completes(self):
        """Deterministic pipe/HTTP mock, actual bounded log file and sparse science IO."""
        from fimrun.resources import output_size
        from fimrun.preview import check_service
        handshake=threading.Event();noise=threading.Event();sessions=[]
        f=FakeStage();port=9876;proc=Mock(pid=42);proc.poll.return_value=None
        proc.wait.side_effect=lambda:setattr(proc.poll,'return_value',-9)
        c=replace(self.case,budget=replace(self.case.budget,output_bytes=40*1024**2),
                  preview=Preview(enabled=True,command=('mock',),port=port,log_bytes=65536,startup_s=2.))
        def factory(options,path,warn):
            s=PreviewSession(options,path,warn,opener=lambda _:handshake.set() or True);sessions.append(s);return s
        def ready():
            s=sessions[0];m=read(s.manifest_path);b=m['binding'];stage=b['allowed_stages'][m['phase']];case=b['cases'][stage['case_id']]
            path=Path(b['run_root'])/case['resolved_case'];exists=path.exists()
            return dict(schema='boris-viewer-ready-v1',version=1,run_id=b['run_id'],binding_sha256=m['binding_sha256'],run_root=b['run_root'],allowed_stages=b['allowed_stages'],instance=s.instance,pid=42,url=f'http://127.0.0.1:{port}',binding_state='bound',revision=m['revision'],stage_id=m['phase'],stage_epoch=m['stage_epoch'],case_id=stage['case_id'],case_identity=case['case_identity'],config_sha256=case['config_sha256'],resolved_case_sha256=sha(path) if exists else None,case_state='verified' if exists else 'pending',data_state='waiting_for_native' if exists else 'waiting_for_case')
        class Stream:
            first=True;remaining=4*1024**2
            def read1(self,n):
                if self.first:self.first=False;return json.dumps(ready()).encode()+b'\n'
                if not noise.wait(3):return b''
                count=min(n,self.remaining);self.remaining-=count;return b'x'*count
            def close(self):pass
        proc.stdout=Stream()
        def stage(kind,case,plan,guard,manifest):
            report=f(kind,case,plan,guard,manifest)
            if kind=='drive':
                self.assertTrue(handshake.wait(2),'valid stdout + HTTP ready before noisy output')
                log=plan.root/'preview.log';used=output_size(plan.root)-log.stat().st_size
                with (plan.root/'synthetic-science-padding.bin').open('wb') as out:out.truncate(39*1024**2-used)
                noise.set();until=time.monotonic()+2
                while not sessions[0].log_full.is_set() and time.monotonic()<until:time.sleep(.01)
                self.assertTrue(sessions[0].log_full.is_set());guard.check()
            return report
        response=Mock();response.__enter__=Mock(return_value=response);response.__exit__=Mock(return_value=False)
        response.read.side_effect=lambda n:json.dumps(ready()).encode();http=Mock();http.open.return_value=response
        with patch('fimrun.engine.PreviewSession',side_effect=factory),patch('fimrun.preview.socket.socket'),patch('fimrun.preview.subprocess.Popen',return_value=proc),patch('fimrun.preview.urllib.request.build_opener',return_value=http),patch('fimrun.preview.owned_rss',return_value=1024),patch('fimrun.resources.os.killpg'):
            result=execute(c,script=self.script,executor=stage)
        self.assertEqual(result['state'],'completed',result)
        self.assertEqual(result['new_fields'],7) # synthetic tokens, no actual fields
        self.assertLessEqual((self.root/'new/preview.log').stat().st_size,65536)
        self.assertLess(output_size(self.root/'new'),40*1024**2)
        self.assertTrue(any('log budget' in x for x in result['warnings']),result)
    def test_port_conflict_and_browser_exception_only_warn(self):
        p=preflight(self.case,script=self.script);p.root.mkdir();m=Manifest(p);m.publish('running');warnings=[]
        with patch('fimrun.preview.socket.socket') as socket_factory:
            socket_factory.return_value.__enter__.return_value.bind.side_effect=OSError('port occupied')
            port=9876
            session=PreviewSession(Preview(enabled=True,command=('unused',),port=port),m.path,warnings.append,opener=lambda _:self.fail('must not open'))
            session.start();session.thread.join(2);session.close()
        self.assertTrue(warnings);self.assertIsNone(session.proc)

if __name__=='__main__':unittest.main()
