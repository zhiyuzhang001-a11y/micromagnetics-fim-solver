"""Create only a synthetic initial physical state, without constructing Native."""
from pathlib import Path
import sys
from unittest.mock import patch
from fimrun.notebook import NotebookSimulation
from fimrun.micromagnetics import *
from fimrun.micromagnetics.native import Native,EVALUATIONS
from fimrun.runtime import PACKAGE_ROOT,doctor
assert PACKAGE_ROOT.is_relative_to(Path(sys.prefix))
path=Path(sys.argv[1]);a=Sublattice(Ms=3e5,alpha=.01,gamma_H=2.21e5)
with patch.object(Native,'__init__',side_effect=AssertionError('no Native')):
 sim=NotebookSimulation(model=FiM(mesh=Grid(cells=(2,2,1),cell_size=(4e-9,4e-9,3e-9)),material=FiMMaterial(A=a,B=a),energy=()),initial=Antiparallel(Uniform((0,0,1))),output_dir=path.parent/'fixture',preview=False)
 sim.save(path.name);(path.parent/'fixture'/path.name).rename(path);sim.close()
assert sum(EVALUATIONS.values())==0
print(doctor(native=True))
