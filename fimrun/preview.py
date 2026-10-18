"""Optional bounded read-only viewer startup. Never catches scientific exceptions."""
import json
import os
from pathlib import Path
import socket
import subprocess
import threading
import time
import urllib.request
import uuid
import webbrowser
from .protocol import read, validate_manifest, sha, config_hash
from .resources import stop, owned_rss

def check_service(r, manifest, instance, pid, port):
    b = validate_manifest(manifest)
    expected = dict(schema='boris-viewer-ready-v1', version=1, run_id=b['run_id'],
                    binding_sha256=manifest['binding_sha256'], run_root=b['run_root'],
                    allowed_stages=b['allowed_stages'], instance=instance, pid=pid,
                    url=f'http://127.0.0.1:{port}', binding_state='bound')
    if any(r.get(k) != v for k, v in expected.items()): raise ValueError('viewer ready identity/schema mismatch')
    return b

def check_ready(r, manifest, instance, pid, port):
    b=check_service(r,manifest,instance,pid,port)
    s = b['allowed_stages'].get(r.get('stage_id'))
    if not s or r.get('case_id') != s['case_id']: raise ValueError('viewer case/stage mismatch')
    c = b['cases'][s['case_id']]
    if r.get('case_identity') != c['case_identity'] or r.get('config_sha256') != c['config_sha256']: raise ValueError('viewer case hash mismatch')
    if type(r.get('revision')) is not int or type(r.get('stage_epoch')) is not int or min(r['revision'],r['stage_epoch']) < 1: raise ValueError('viewer revision/epoch')
    # Verify the advertised revision is still current. A concurrent stage update retries.
    if (r['revision'],r['stage_epoch'],r['stage_id']) != (manifest['revision'],manifest['stage_epoch'],manifest['phase']): raise ValueError('viewer state changed; retry ready')
    cp = Path(b['run_root']) / c['resolved_case']
    if r.get('case_state') == 'pending':
        if cp.exists() or r.get('resolved_case_sha256') is not None or r.get('data_state') != 'waiting_for_case': raise ValueError('false pending case')
    elif r.get('case_state') == 'verified':
        value = read(cp)
        if value['identity'] != c['case_identity'] or config_hash(value) != c['config_sha256'] or sha(cp) != r.get('resolved_case_sha256'): raise ValueError('viewer saved case not verified')
        if r.get('data_state') not in ('waiting_for_native','ready'): raise ValueError('viewer data_state')
    else: raise ValueError('viewer case_state')
    return r['url']

class PreviewSession:
    def __init__(self, options, manifest_path, warn, *, opener=webbrowser.open):
        self.options=options; self.manifest_path=Path(manifest_path); self.warn=warn; self.opener=opener
        self.proc=None; self.thread=None; self.done=threading.Event(); self.instance=str(uuid.uuid4())
        self.binding=None
        self.log_full=threading.Event();self.capture_error=None;self.collector=None
        self.metrics={'fields':0,'startup_s':0.,'requests':0,'response_bytes':0,'peak_owned_rss_bytes':0,
                      'rss_scope':'viewer subprocess and descendants, sampled; excludes shared browser',
                      'lifecycle':'own service stops at run end; browser not closed','opened_attempts':0}
        self.metrics.update(log_budget_bytes=options.log_bytes if options.enabled else 0,log_written_bytes=0)
    @property
    def pid(self): return self.proc.pid if self.proc else None
    def start(self):
        if self.options.enabled:
            try:
                self.binding=validate_manifest(read(self.manifest_path))
                self.thread=threading.Thread(target=self._work,daemon=True); self.thread.start()
            except Exception as e: self.warn('preview disabled: '+str(e))
    def _manifest(self):
        value=read(self.manifest_path);validate_manifest(value,self.binding);return value
    def _rss(self):
        if self.log_full.is_set():raise RuntimeError('viewer log budget reached; stopped own preview, science continues')
        if self.capture_error:raise RuntimeError('viewer log capture failed: '+self.capture_error)
        rss=owned_rss(self.proc.pid)
        self.metrics['peak_owned_rss_bytes']=max(rss,self.metrics['peak_owned_rss_bytes'])
        if rss>self.options.max_rss_bytes: raise RuntimeError('viewer sampled owned RSS cap exceeded')
    def _capture(self,log):
        """One pipe reader, bounded chunks and writes. Never redirect child to a file."""
        try:
            remaining=self.options.log_bytes
            while not self.done.is_set() and remaining:
                data=self.proc.stdout.read1(min(8192,remaining))
                if not data:return
                data=data[:remaining]
                log.write(data);log.flush();remaining-=len(data)
                self.metrics['log_written_bytes']+=len(data)
            if not remaining:
                self.warn('preview disabled: viewer log budget reached; stopping own preview; science continues')
                self.log_full.set()
        except Exception as e:self.capture_error=str(e)
    def _work(self):
        start=time.monotonic(); log=None
        try:
            if not self.options.command: raise ValueError('preview.command required for protocol-v1 viewer; no automatic discovery')
            # Probe only; Popen still must bind itself. Never attach to an existing listener.
            with socket.socket() as s: s.bind(('127.0.0.1',self.options.port))
            log=(self.manifest_path.parent/'preview.log').open('xb')
            argv=[*self.options.command,'--manifest',str(self.manifest_path),'--port',str(self.options.port),'--instance',self.instance]
            self.proc=subprocess.Popen(argv,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,start_new_session=True)
            self.collector=threading.Thread(target=self._capture,args=(log,),daemon=True);self.collector.start()
            url=f'http://127.0.0.1:{self.options.port}/api/ready'; last='not ready'; stdout_checked=False
            while not self.done.is_set() and time.monotonic()-start < self.options.startup_s:
                if self.proc.poll() is not None: raise RuntimeError('viewer exited before ready')
                self._rss()
                try:
                    if not stdout_checked:
                        with (self.manifest_path.parent/'preview.log').open('rb') as f: line=f.readline(65537)
                        if len(line)>65536: raise ValueError('stdout ready too large')
                        if not line.endswith(b'\n'):
                            self.done.wait(.04); continue
                        check_service(json.loads(line),self._manifest(),self.instance,self.proc.pid,self.options.port)
                        stdout_checked=True
                    self.metrics['requests']+=1
                    # No proxy/environment mutation and no redirects to an unrelated server.
                    class NoRedirect(urllib.request.HTTPRedirectHandler):
                        def redirect_request(self,*args,**kwargs): return None
                    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect())
                    with opener.open(url,timeout=min(.2,max(.001,self.options.startup_s-(time.monotonic()-start)))) as response:
                        raw=response.read(65537)
                    self.metrics['response_bytes']+=len(raw)
                    if len(raw)>65536: raise ValueError('ready response too large')
                    ready=json.loads(raw)
                    target=check_ready(ready,self._manifest(),self.instance,self.proc.pid,self.options.port)
                    if self.options.open_browser:
                        self.metrics['opened_attempts']+=1
                        try:
                            if not self.opener(target): self.warn('browser open returned false; bound URL: '+target)
                        except Exception as e: self.warn('browser open failed: '+str(e)+'; bound URL: '+target)
                    break
                except (OSError,ValueError,KeyError) as e: last=str(e); self.done.wait(.04)
            else:
                if not self.done.is_set(): raise TimeoutError('viewer ready timeout: '+last)
            self.metrics['startup_s']=time.monotonic()-start
            while not self.done.wait(.1):
                if self.proc.poll() is not None: raise RuntimeError('viewer exited; science continues')
                self._rss();self._manifest()
        except Exception as e:
            if not self.log_full.is_set():self.warn('preview disabled: '+str(e))
        finally:
            self.metrics['startup_s']=self.metrics['startup_s'] or time.monotonic()-start
            try: stop(self.proc,include_orphans=True)
            except Exception as e: self.warn('preview cleanup failed: '+str(e))
            if self.collector:self.collector.join(timeout=.5)
            if self.proc and self.proc.stdout and (not self.collector or not self.collector.is_alive()):self.proc.stdout.close()
            if log: log.close()
    def close(self):
        self.done.set()
        if self.thread:
            try:
                self.thread.join(timeout=3)
                stop(self.proc)
            except Exception as e: self.warn('preview cleanup failed: '+str(e))
