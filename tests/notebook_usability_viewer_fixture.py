"""Synthetic accepted-state viewer fixture: no native engine, fields or user browser."""
import json,socket,sys,tempfile
from pathlib import Path
from unittest.mock import patch
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from fimrun.notebook import NotebookSimulation
from fimrun.micromagnetics import *
from fimrun.micromagnetics.native import EVALUATIONS
with tempfile.TemporaryDirectory() as temp:
    root=Path(temp).resolve()
    with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
    a=Sublattice(Ms=3e5,alpha=.01,gamma_H=2e5);b=Sublattice(Ms=6e5,alpha=.01,gamma_H=2e5)
    n=int(sys.argv[1]) if len(sys.argv)>1 else 5
    model=FiM(mesh=Grid(cells=(n,n,1),cell_size=(4e-9,4e-9,3e-9)),material=FiMMaterial(A=a,B=b))
    def create(initial):return NotebookSimulation(model=model,initial=Antiparallel(Uniform(initial)),dt=1e-15,output_dir=root,preview=True,preview_port=port)
    with patch('webbrowser.open',return_value=True) as browser:
        sim=create((0.,0.,1.));core=sim._session.sim
        H=np.zeros_like(core._m);H[0,...,0]=2.;H[1,...,0]=.5;core._field=H;core._energy=np.zeros(2)
        core.segments.append(dict(id='synthetic-static',index=0,kind='sdesc',status='converged',error=None))
        core._preview_stop={'tolerance':1.,'mxh':1e-6,'consecutive':1};core._publish_preview(force=True)
        print(json.dumps({'url':core._preview.url,'fields':dict(EVALUATIONS)}),flush=True)
        for line in sys.stdin:
            if line.strip()=='rebind':
                sim=create((1.,0.,0.));print(json.dumps({'run_id':sim.run_id,'opens':browser.call_count,'fields':dict(EVALUATIONS)}),flush=True)
            elif line.strip()=='metrics':print(json.dumps({'opens':browser.call_count,'fields':dict(EVALUATIONS)}),flush=True)
            elif line.strip()=='close':break
        sim.close()
