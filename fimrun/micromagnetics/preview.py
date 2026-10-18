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
import webbrowser
from urllib.parse import urlsplit, parse_qs
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import numpy as np
from .model import describe
from .native import ROOT

SCHEMA = 'micromagnetics-viewer-v2'
IDENTITY = ('run_id','binding_sha256','instance','stage_id','stage_epoch','case_id','case_identity','config_sha256')
ASSETS = Path(__file__).resolve().parent / 'viewer'


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,allow_nan=False).encode()).hexdigest()


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
                        'events':[], 'max_retained_frames':16,'max_retained_bytes':32*1024*1024,'byte_limit_scope':'immutable raw direction arrays; at most2 bounded display-response caches; not total process RSS'}
        self.active_requests = []

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
        static = bool(segment and segment['kind']=='sdesc')
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
            state = dict(new_api=True, convergence=gates, static_stop_enabled=static and stop is not None,
                         residual_scope='Conservative energy field; not the complete LLG/SOT RHS; no dynamic stop',name=type(sim.model).__name__,labels=list(sim.labels),run_source=sim.run_id,
                         stage='static' if static else 'rk4',phase=segment['status'] if segment else 'initialized',
                         step=steps,target_steps=None if static else getattr(sim,'_target_steps',None),
                         time_ps=None if static else sim.time*1e12,physical_time_s=sim.time,
                         target_ps=None if static or segment is None else getattr(sim,'_target_time',sim.time)*1e12,
                         dt_fs=None if static else sim.solver.dt*1e15,elapsed_s=elapsed,
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
                         geometry=geometry,labels=list(sim.labels),frame_seq=seq,frame_mtime_utc=None,
                         raw_bytes=m.nbytes,max_unit_error_squared=float(np.max(np.abs(np.sum(m*m,axis=-1)-1))),
                         cache_hit=False,read_ms=0.)
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
                return dict(run_id=self.sim.run_id,instance=self.instance,binding_epoch=self.binding_epoch), {}
        self._authorize(query)
        with self.lock:
            packet = self.latest
            if packet is None:
                raise ValueError('waiting for accepted state')
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
                    raise ValueError('stale stage/configuration request')
            requested = query.get('step',['latest'])[0]
            seq = packet['revision'] if requested=='latest' else int(requested)
            if seq not in self.frames:
                raise ValueError('frame evicted; refresh latest state')
            packet = self.frames[seq]
            stride = int(query.get('stride',['4'])[0])
            if stride not in (1,2,4,8,16):
                raise ValueError('unsupported display stride')
            cache_key = (seq, stride)
            if cache_key not in self.frame_cache:
                nx,ny,nz=packet['frame']['geometry']['n']
                ids=np.array([x+nx*(y+ny*z) for z in range(0,nz,stride) for y in range(0,ny,stride) for x in range(0,nx,stride)])
                if len(ids)>20000:
                    raise ValueError('too many visible arrows; increase display stride')
                vectors=packet['m'].reshape(len(packet['frame']['labels']),-1,3)[:,ids,:].tolist()
                self.frame_cache[cache_key]=dict(packet['frame'],indices=ids.tolist(),vectors=vectors,stride=stride)
                while len(self.frame_cache)>2:self.frame_cache.popitem(last=False)
            self.metrics['frame_requests']+=1
            self.metrics['events'].append({'event':'frame','monotonic':time.monotonic(),'frame_seq':seq,'epoch':self.epoch,'active':self.latest['state']['phase']=='running'})
            self.metrics['events']=self.metrics['events'][-512:]
            headers={'X-Boris-Schema':'micromagnetics-frame-v2','X-Boris-Version':'2','X-Boris-Frame-Seq':str(seq)}
            headers.update({'X-Boris-'+k.replace('_','-'):str(v) for k,v in packet['identity'].items()})
            return dict(self.frame_cache[cache_key],frame_age_s=max(0.,time.monotonic()-packet['published'])),headers

    def start(self):
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
                    self.send_error(409 if isinstance(error,ValueError) else 404,str(error))
        try:
            if not (ASSETS/'app.js').is_file():raise OSError('unified viewer assets are unavailable')
            self.publish(force=True)
            self.server=ThreadingHTTPServer(('127.0.0.1',self.port),Handler)
            self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
            self.url=f'http://127.0.0.1:{self.port}/?run_id={self.sim.run_id}&instance={self.instance}&source=script'
            webbrowser.open(self.url)
        except Exception as error:
            if self.server is not None:
                if self.thread is not None and self.thread.is_alive():
                    self.server.shutdown();self.thread.join()
                self.server.server_close();self.server=None
            warnings.warn(f'Preview unavailable; science continues: {error}',RuntimeWarning)

    def close(self):
        if self.server is not None:
            self.server.shutdown();self.server.server_close();self.thread.join();self.server=None
