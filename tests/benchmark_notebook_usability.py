"""Bounded isolated output/cache comparison; not a scientific timestep qualification."""
import json,sys,tempfile,time,os
from pathlib import Path
import numpy as np
sys.path[:0]=[str(Path(__file__).resolve().parents[1]),str(Path(__file__).resolve().parent)]
from test_notebook_usability import model
from fimrun.notebook import NotebookSimulation
from fimrun.micromagnetics import Antiparallel,Uniform
from fimrun.micromagnetics.preview import LivePreview
from fimrun.micromagnetics.native import EVALUATIONS,Native
out=Path(sys.argv[1]).resolve();out.mkdir(parents=True,exist_ok=True)
original=Native.evaluate;attempts=0

def bounded(engine,m):
    global attempts
    if attempts>=150:raise RuntimeError('benchmark field budget exhausted')
    attempts+=1;return original(engine,m)
Native.evaluate=bounded
rows=[];reference=None
try:
 with tempfile.TemporaryDirectory() as temp:
  for name,every,mag,scalars,preview in [('off',None,False,(),False),('final',None,True,('time','mean_m'),False),('every1',1e-15,True,('time','mean_m'),False),('every2',2e-15,True,('time','mean_m'),False),('cached_preview',None,False,(),True)]:
   root=Path(temp).resolve()/name
   sim=NotebookSimulation(model=model(),initial=Antiparallel(Uniform((.6,0.,.8))),dt=1e-15,output_dir=root,magnetization=mag,scalars=scalars)
   core=sim._session.sim;view=LivePreview(core,18899) if preview else None
   if view:core._publish_preview=lambda **kwargs:view.publish(force=True,residual=kwargs.get('residual'))
   before=sum(EVALUATIONS.values());started=time.monotonic();sim.run(4e-15,every=every);wall=time.monotonic()-started
   data=(sim.m.tobytes(),sim.time,sim.dissipation.tobytes(),sim.drive_work.tobytes())
   if reference is None:reference=data
   assert data==reference,'output/cache options changed scientific state'
   cache_time=0.;bytes_sent=0
   if view:
    cache_start=time.monotonic()
    for stride in (1,2,4):
     query={k:[str(v)] for k,v in view.latest['identity'].items()};query['stride']=[str(stride)]
     packet,_=view.response('/api/frame',query);bytes_sent+=len(json.dumps(packet).encode())
    cache_time=time.monotonic()-cache_start
   rows.append(dict(name=name,wall_s=wall,fields=sum(EVALUATIONS.values())-before,output_bytes=sum(p.stat().st_size for p in root.rglob('*') if p.is_file()),io_s=sim.metrics()['notebook_output']['io_s'],cache_response_s=cache_time,cache_response_bytes=bytes_sent,preview_published_frames=view.metrics['published_frames'] if view else 0,scientific_state_exact=True))
   sim.close()
finally:
 receipt={'status':'passed' if len(rows)==5 else 'incomplete','scope':'single 3x3 FiM,4 steps,CPU; output and cached-preview engineering sample; no FFT active; no speed guarantee','rows':rows,'fields_attempted':attempts,'fields_completed':dict(EVALUATIONS)}
 (out/'benchmark.json').write_text(json.dumps(receipt,indent=2)+'\n');print(json.dumps(receipt))
