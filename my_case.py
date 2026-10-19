"""Small public demo; imports do not start science. Run explicitly with --run."""
from pathlib import Path
import argparse
from fimrun.micromagnetics import Grid,Sublattice,FiMMaterial,FiM,Uniform,Antiparallel,Zeeman
from fimrun.notebook import NotebookSimulation

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--run',action='store_true');args=parser.parse_args()
    a=Sublattice(Ms=3e5,alpha=.01,gamma_H=2.21e5)
    model=FiM(mesh=Grid(cells=(3,3,1),cell_size=(4e-9,4e-9,3e-9)),material=FiMMaterial(A=a,B=a),energy=(Zeeman(H_ext=(100.,0.,0.)),))
    if not args.run:print('Synthetic 3x3x1 demo; use --run for two femtosecond steps.');return
    sim=NotebookSimulation(model=model,initial=Antiparallel(Uniform((0.,0.,1.))),output_dir=Path('demo-results'),preview=False)
    try:sim.run(name='demo',dt=1e-15,duration=2e-15,save_interval=None)
    finally:sim.close()
if __name__=='__main__':main()
