"""Versioned read-only transient source for the existing unified 3D viewer."""
from collections import OrderedDict
from dataclasses import asdict
import hashlib
import json
import math
from pathlib import Path
import threading
import time
import uuid
import warnings
import weakref
import copy
import webbrowser
from urllib.parse import urlsplit, parse_qs
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import numpy as np
from .model import describe
from .native import ROOT

SCHEMA = 'micromagnetics-viewer-v2'
IDENTITY = ('run_id','binding_sha256','instance','stage_id','stage_epoch','case_id','case_identity','config_sha256')
ASSETS = Path(__file__).resolve().parent / 'viewer'
# A channel belongs to this Python process and explicit port, never another kernel.
_PORT_LOCK = threading.RLock()
_OWNED_PORTS = weakref.WeakValueDictionary()
_RETIRED_PORTS = OrderedDict()  # Capability/sequence metadata only, no old magnetic arrays.


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,allow_nan=False).encode()).hexdigest()


class PreviewRequestError(ValueError):
    def __init__(self, code, message, status):
        super().__init__(message)
        self.code, self.status = code, status


class LivePreview:
    def __init__(self, sim, port):
        self.sim, self.port = sim, port
        self.instance = str(uuid.uuid4())
        self.server = self.thread = None
        self.lock = threading.RLock()
        self.frames = OrderedDict()
        self.frame_cache = OrderedDict()
        self.sequence = 0
        self.epoch = None
        self.epoch_offset = 0
        self.binding_epoch = 0
        self.latest = None
        self.last_publish = -math.inf
        self.metrics = {'state_requests':0,'frame_requests':0,'published_frames':0,'bytes_sent':0,
                        'events':[], 'max_retained_frames':16,'max_retained_bytes':32*1024*1024,'byte_limit_scope':'immutable raw direction arrays; at most2 bounded display-response caches; 3D responses <=20000 samples/sublattice; 2D single XY plane <=65536 pixels/sublattice; not total process RSS'}
        self.active_requests = []
        self.handoff_error = self.handoff_notice = self.last_error = None

    @classmethod
    def acquire(cls, sim, port):
        """Reuse only our idle channel; never kill or probe an unknown listener."""
        with _PORT_LOCK:
            owner = _OWNED_PORTS.get(port) if port else None
            if owner is not None and owner.server is not None:
                if owner.sim is sim:
                    owner.handoff_error = owner.handoff_notice = None
                    return owner
                old = owner.sim
                busy = getattr(old, '_busy', False) or bool(old.segments and old.segments[-1]['status']=='running')
                if busy:
                    message=f'预览通道{port}仍属于正在计算的run {old.run_id}；新run {sim.run_id}未接管。独立实验请使用不同preview_port。'
                    owner.handoff_notice=message
                    failed=cls(sim,port);failed.last_error=message
                    warnings.warn(message,RuntimeWarning)
                    return failed
                with owner.lock:
                    snapshot={k:getattr(owner,k) for k in ('sim','epoch_offset','binding_epoch','sequence','epoch','url','latest','last_publish')}
                    frames=owner.frames.copy();cache=owner.frame_cache.copy();metrics=copy.deepcopy(owner.metrics)
                    try:
                        owner.rebind(sim)
                    except BaseException as error:
                        for k,value in snapshot.items():setattr(owner,k,value)
                        owner.frames=frames;owner.frame_cache=cache;owner.metrics=metrics
                        message=f'切换到run {sim.run_id}失败；未显示当前模拟。请重试sim.preview()。{error}'
                        owner.handoff_error=message
                        if not isinstance(error,Exception):raise
                        failed=cls(sim,port);failed.last_error=message
                        warnings.warn(message,RuntimeWarning)
                        return failed
                    if getattr(old,'_preview',None) is owner:old._preview=None
                    owner.handoff_error=owner.handoff_notice=None
                    return owner
            result=cls(sim,port)
            retired=_RETIRED_PORTS.get(port) if port else None
            if retired:
                result.instance=retired['instance'];result.binding_epoch=retired['binding_epoch']+1
                result.epoch_offset=retired['epoch']+1;result.sequence=retired['sequence']
            result.start(open_browser=not bool(retired))
            if result.server is not None:
                _OWNED_PORTS[result.port]=result
                _RETIRED_PORTS.pop(result.port,None)
            return result

    def publish(self, *, force=False, residual=None):
        now = time.monotonic()
        if not force and now-self.last_publish < 1.:
            return
        sim = self.sim
        segment = sim.segments[-1] if sim.segments else None
        epoch = self.epoch_offset + (segment['index']+1 if segment else 0)
        model = describe(sim.model)
        config = {'model':model,'solver':asdict(sim.solver),'current':asdict(sim.current) if sim.current else None,
                  'stop':getattr(sim,'_preview_stop',None)}
        config_hash = digest(config)
        m = sim.m
        if m.nbytes > 16*1024*1024 or m.shape != (len(sim.labels), *sim.model.mesh.shape) or not np.isfinite(m).all() or np.max(np.abs(np.sum(m*m,axis=-1)-1)) > 1e-9:
            raise ValueError('preview requires a complete finite unit-direction packet')
        m.setflags(write=False)
        elapsed = max(0.,now-getattr(sim,'_stage_started',now))
        if segment and segment['status']!='running':
            elapsed = getattr(sim,'_stage_elapsed',elapsed)
        static = bool(segment and segment['kind']=='sdesc') and not getattr(sim, '_restored_pending', False)
        steps = getattr(sim,'_active_steps',0)
        if residual is None and sim._field is not None:
            residual = sim._residual(sim._m, sim._field)
        ms = [getattr(sim.model.material, label).Ms for label in sim.labels] if len(sim.labels)>1 else [sim.model.material.Ms]
        stop = getattr(sim, '_preview_stop', None) if static else None
        gates = []
        for i,label in enumerate(sim.labels):
            r = float(residual[i]) if residual is not None else None
            q = r/ms[i] if r is not None else None
            rt = stop.get('tolerance') if stop else None
            qt = stop.get('mxh') if stop else None
            gates.append(dict(label=label,residual_Apm=r,mxh=q,Ms_Apm=ms[i],residual_limit_Apm=rt,mxh_limit=qt,
                residual_pass=(r<=rt) if r is not None and rt is not None else None,
                mxh_pass=(q<=qt) if q is not None and qt is not None else None,
                dominant=('residual' if rt<=ms[i]*qt else 'mxh') if rt is not None and qt is not None else None))
        geometry = {'n':list(sim.model.mesh.cells),'cell_nm':[v*1e9 for v in sim.model.mesh.cell_size],
                    'origin_nm':[v*1e9 for v in sim.model.mesh.origin]}
        with self.lock:
            if self.epoch != epoch:
                self.frames.clear()
                self.frame_cache.clear()
                self.epoch = epoch
            self.sequence += 1
            seq = self.sequence
            identity = dict(run_id=sim.run_id,binding_sha256=digest({'run_id':sim.run_id}),instance=self.instance,
                            stage_id=segment['id'] if segment else 'initial',stage_epoch=epoch,
                            case_id=type(sim.model).__name__,case_identity=config_hash,config_sha256=config_hash)
            from ..progress import simulation_snapshot
            progress = simulation_snapshot(sim, residual)
            state = dict(progress=progress, new_api=True, convergence=gates, static_stop_enabled=static and stop is not None,
                         residual_scope='Conservative energy field; not the complete LLG/SOT RHS; no dynamic stop',name=type(sim.model).__name__,labels=list(sim.labels),run_source=sim.run_id,
                         stage='static' if static else 'rk4',phase=progress['phase'],
                         step=steps,target_steps=None if static else getattr(sim,'_target_steps',None),
                         time_ps=None if static else sim.time*1e12,physical_time_s=sim.time,
                         target_ps=None if static or segment is None else getattr(sim,'_target_time',sim.time)*1e12,
                         dt_fs=None if static or sim.solver.dt is None else sim.solver.dt*1e15,elapsed_s=elapsed,
                         throughput_steps_s=steps/elapsed if elapsed else None,
                         energy_J=float(sim._energy.sum()) if sim._energy is not None else None,
                         residual_A_Apm=float(residual[0]) if residual is not None else None,
                         residual_B_Apm=float(residual[1]) if residual is not None and len(residual)>1 else None,
                         residual_step=steps if residual is not None else None,residual_time_ps=None if static else sim.time*1e12,
                         scalar_step=steps,checkpoint_step=seq,latest_signature=[self.instance,epoch,seq],
                         finished=bool(segment and segment['status']!='running'),stop_reason=segment.get('error') if segment else None,
                         failure=segment.get('error') if segment and segment['status']=='failed' else None,
                         source='transient accepted-state channel',configuration=config,geometry=geometry,
                         source_kind='bounded-memory',frame_seq=seq,frame_time_s=sim.time,
                         server_checked_utc=None,progress_mtime_utc=None,progress_age_s=0.)
            frame = dict(step=steps,time_ps=None if static else sim.time*1e12,physical_time_s=sim.time,
                         stage=state['stage'],source='transient accepted-state channel',source_signature=[self.instance,epoch,seq],
                         geometry=geometry,configuration=config,config_sha256=config_hash,labels=list(sim.labels),frame_seq=seq,frame_mtime_utc=None,
                         raw_bytes=m.nbytes,max_unit_error_squared=float(np.max(np.abs(np.sum(m*m,axis=-1)-1))),
                         progress=progress, energy_J=state['energy_J'], cache_hit=False,read_ms=0.)
            packet = {'identity':identity,'revision':seq,'state':state,'frame':frame,'m':m,'published':now}
            self.frames[seq] = packet
            while len(self.frames)>16 or sum(p['m'].nbytes for p in self.frames.values())>32*1024*1024:
                self.frames.popitem(last=False)
            for key in list(self.frame_cache):
                if key[0] not in self.frames:del self.frame_cache[key]
            self.latest = packet
            self.last_publish = now
            self.metrics['published_frames'] += 1
            event = {'event':'publish','monotonic':now,'frame_seq':seq,'epoch':epoch,'active':bool(segment and segment['status']=='running'),'step':steps}
            self.metrics['events'].append(event)
            self.metrics['events'] = self.metrics['events'][-512:]

    def rebind(self, sim):
        """Transfer one owned viewer; stable random instance authorizes binding discovery."""
        with self.lock:
            self.epoch_offset = (self.epoch or 0)+1
            self.binding_epoch += 1
            self.sim = sim
            self.url = f'http://127.0.0.1:{self.port}/?run_id={sim.run_id}&instance={self.instance}&source=script'
            self.frames.clear();self.frame_cache.clear();self.latest=None
            self.publish(force=True)

    def _authorize(self, query):
        if query.get('run_id',[None])[0]!=self.sim.run_id or query.get('instance',[None])[0]!=self.instance:
            raise ValueError('run or viewer instance mismatch')

    def response(self, path, query):
        if path == '/api/binding':
            if query.get('instance',[None])[0]!=self.instance:
                raise ValueError('viewer instance mismatch')
            with self.lock:
                return dict(run_id=self.sim.run_id,instance=self.instance,binding_epoch=self.binding_epoch,
                            handoff_error=self.handoff_error,handoff_notice=self.handoff_notice), {}
        self._authorize(query)
        with self.lock:
            packet = self.latest
            if packet is None:
                raise PreviewRequestError('waiting_for_state', '等待有效磁态。', 409)
            if path in ('/api/state','/api/ready'):
                self.metrics['state_requests'] += 1
                state = dict(packet['state'],frames=list(self.frames),progress_age_s=max(0.,time.monotonic()-packet['published']))
                self.metrics['events'].append({'event':'state','monotonic':time.monotonic(),'frame_seq':packet['revision'],'epoch':self.epoch,'active':state['phase']=='running'})
                self.metrics['events']=self.metrics['events'][-512:]
                return dict(schema=SCHEMA,version=2,revision=packet['revision'],**packet['identity'],data=state), {}
            if path == '/api/metrics':
                return dict(self.metrics,retained_frames=len(self.frames),retained_bytes=sum(p['m'].nbytes for p in self.frames.values())), {}
            if path != '/api/frame':
                raise KeyError('unknown endpoint')
            for key in IDENTITY:
                if str(packet['identity'][key]) != query.get(key,[None])[0]:
                    raise PreviewRequestError('source_changed', '阶段或配置已变化，请恢复最新磁态。', 409)
            requested = query.get('step',['latest'])[0]
            seq = packet['revision'] if requested=='latest' else int(requested)
            if seq not in self.frames:
                raise PreviewRequestError('frame_expired', '历史帧已过期，请恢复最新磁态。', 409)
            packet = self.frames[seq]
            stride = int(query.get('stride',['4'])[0])
            if stride not in (1,2,4,8,16):
                raise PreviewRequestError('invalid_sampling', '显示密度无效。', 400)
            view_mode=query.get('view',['3d'])[0]
            if view_mode not in ('3d','2d'):
                raise PreviewRequestError('invalid_view', '视图模式无效。', 400)
            cache_key = (seq, stride, view_mode)
            if cache_key not in self.frame_cache:
                nx,ny,nz=packet['frame']['geometry']['n']
                if view_mode=='2d' and (nz!=1 or nx*ny>65536):
                    raise PreviewRequestError('capacity_exceeded', '2D热图支持单层XY平面，最多65536个网格单元。', 422)
                layers=(0,) if view_mode=='2d' else range(0,nz,stride)
                count=((nx+stride-1)//stride)*((ny+stride-1)//stride)*len(layers)
                if view_mode=='3d' and count>20000:
                    raise PreviewRequestError('capacity_exceeded', '3D箭头超过每子晶格20000支的显示上限，请选择每2格或更疏的显示；2D可使用每1格。', 422)
                ids=np.array([x+nx*(y+ny*z) for z in layers for y in range(0,ny,stride) for x in range(0,nx,stride)])
                vectors=packet['m'].reshape(len(packet['frame']['labels']),-1,3)[:,ids,:].tolist()
                self.frame_cache[cache_key]=dict(packet['frame'],indices=ids.tolist(),vectors=vectors,stride=stride,view_mode=view_mode)
                while len(self.frame_cache)>2:self.frame_cache.popitem(last=False)
            self.metrics['frame_requests']+=1
            self.metrics['events'].append({'event':'frame','monotonic':time.monotonic(),'frame_seq':seq,'epoch':self.epoch,'active':self.latest['state']['phase']=='running'})
            self.metrics['events']=self.metrics['events'][-512:]
            headers={'X-Boris-Schema':'micromagnetics-frame-v2','X-Boris-Version':'2','X-Boris-Frame-Seq':str(seq)}
            headers.update({'X-Boris-'+k.replace('_','-'):str(v) for k,v in packet['identity'].items()})
            return dict(self.frame_cache[cache_key],frame_age_s=max(0.,time.monotonic()-packet['published'])),headers

    def start(self, *, open_browser=True):
        owner=self
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def do_GET(self):
                parsed=urlsplit(self.path);query=parse_qs(parsed.query)
                try:
                    if parsed.path.startswith('/api/'):
                        value,headers=owner.response(parsed.path,query)
                        body=json.dumps(value,allow_nan=False).encode();mime='application/json'
                    else:
                        if parsed.path=='/':owner._authorize(query)
                        name='index.html' if parsed.path=='/' else parsed.path.lstrip('/')
                        path=(ASSETS/name).resolve()
                        if not path.is_relative_to(ASSETS.resolve()) or path.suffix not in ('.html','.js'):
                            raise KeyError('unknown asset')
                        body=path.read_bytes();headers={};mime='text/html' if path.suffix=='.html' else 'text/javascript'
                    self.send_response(200)
                    self.send_header('Content-Type',mime);self.send_header('Content-Length',str(len(body)))
                    self.send_header('Cache-Control','no-store')
                    for key,value in headers.items():self.send_header(key,value)
                    self.end_headers();self.wfile.write(body)
                    with owner.lock:owner.metrics['bytes_sent']+=len(body)
                except (ValueError,KeyError,OSError) as error:
                    code = getattr(error,'code','source_changed' if isinstance(error,ValueError) else 'resource_missing')
                    body=json.dumps({'code':code,'message':str(error)},ensure_ascii=False).encode()
                    self.send_response(getattr(error,'status',409 if isinstance(error,ValueError) else 404))
                    self.send_header('Content-Type','application/json; charset=utf-8');self.send_header('Cache-Control','no-store')
                    self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
        try:
            if not (ASSETS/'app.js').is_file():raise OSError('unified viewer assets are unavailable')
            self.publish(force=True)
            self.server=ThreadingHTTPServer(('127.0.0.1',self.port),Handler)
            self.port=self.server.server_address[1]
            self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
            self.url=f'http://127.0.0.1:{self.port}/?run_id={self.sim.run_id}&instance={self.instance}&source=script'
            with _PORT_LOCK:
                _OWNED_PORTS[self.port]=self
            if open_browser:webbrowser.open(self.url)
        except Exception as error:
            if self.server is not None:
                if self.thread is not None and self.thread.is_alive():
                    self.server.shutdown();self.thread.join()
                self.server.server_close();self.server=None
            self.last_error=f'预览未连接当前run {self.sim.run_id}（端口{self.port}）；科学计算可继续。未接管未知服务。释放冲突后可重试sim.preview()。{error}'
            warnings.warn(self.last_error,RuntimeWarning)

    def close(self):
        with _PORT_LOCK:
            if self.server is not None:
                if _OWNED_PORTS.get(self.port) is self:
                    _RETIRED_PORTS[self.port]=dict(instance=self.instance,binding_epoch=self.binding_epoch,
                        epoch=self.epoch or 0,sequence=self.sequence)
                    while len(_RETIRED_PORTS)>16:_RETIRED_PORTS.popitem(last=False)
                    del _OWNED_PORTS[self.port]
                self.server.shutdown();self.server.server_close();self.thread.join();self.server=None
