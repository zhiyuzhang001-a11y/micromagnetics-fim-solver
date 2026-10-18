"""Protocol-only mock: reads synthetic manifests, never loads a native Model."""
import argparse
from http.server import BaseHTTPRequestHandler,HTTPServer
import json
import os
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from fimrun.protocol import read,validate_manifest,sha,config_hash

def ready(args):
    v=read(args.manifest); b=validate_manifest(v); s=b['allowed_stages'][v['phase']]; c=b['cases'][s['case_id']]
    p=Path(b['run_root'])/c['resolved_case']; exists=p.exists()
    if exists:
        actual=read(p)
        if config_hash(actual)!=c['config_sha256'] or actual['identity']!=c['case_identity']: raise ValueError('case tamper')
    return dict(schema='boris-viewer-ready-v1',version=1,run_id=b['run_id'],binding_sha256=v['binding_sha256'],
                run_root=b['run_root'],allowed_stages=b['allowed_stages'],instance=args.instance,pid=os.getpid(),
                url=f'http://127.0.0.1:{args.port}',binding_state='bound',revision=v['revision'],state=v['state'],
                stage_id=v['phase'],stage_epoch=v['stage_epoch'],case_id=s['case_id'],case_identity=c['case_identity'],
                config_sha256=c['config_sha256'],resolved_case_sha256=sha(p) if exists else None,
                case_state='verified' if exists else 'pending',data_state='waiting_for_native' if exists else 'waiting_for_case')

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--manifest',required=True);parser.add_argument('--port',type=int,required=True);parser.add_argument('--instance',required=True)
    args=parser.parse_args()
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args): pass
        def do_GET(self):
            if self.path!='/api/ready': self.send_error(404);return
            raw=json.dumps(ready(args)).encode();self.send_response(200);self.send_header('Content-Type','application/json');self.send_header('Cache-Control','no-store');self.end_headers();self.wfile.write(raw)
    server=HTTPServer(('127.0.0.1',args.port),Handler)
    print(json.dumps(ready(args)),flush=True)
    server.serve_forever()
