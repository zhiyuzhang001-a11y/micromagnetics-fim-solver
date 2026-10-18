"""Run in a new working directory with the installed micromagnetics environment."""
from pathlib import Path
from fimrun.micromagnetics import Grid, Sublattice, FiMMaterial, FiM, FiMAnisotropy, Uniform, Antiparallel, FiMSOT
from fimrun.notebook import NotebookSimulation

grid = Grid(cells=(3, 3, 1), cell_size=(4e-9, 4e-9, 3e-9))  # m
sub_A = Sublattice(Ms=3e5, alpha=0.01, gamma_H=2e5)
sub_B = Sublattice(Ms=6e5, alpha=0.01, gamma_H=2e5)
model = FiM(mesh=grid, material=FiMMaterial(A=sub_A, B=sub_B),
            energy=(FiMAnisotropy(K1_A=1e4, K1_B=2e4),))
initial = Antiparallel(Uniform((0., 0., 1.)))

output_dir = (Path.cwd() / 'results' / 'notebook_demo').resolve()
sim = NotebookSimulation(model=model, initial=initial, dt=1e-15,
    output_dir=output_dir, output_name='prepare', save_interval=1e-15,
    scalars=('time', 'mean_m'), magnetization=True, preview=False)
sim

sim.run(1e-15, output_name='prepare', save_interval=1e-15)

sim.relax(mxh=1e-5, residual=1.0, consecutive=1,
          output_name='static', save_every_steps=1, scalars=('time', 'residual', 'mxh'))

sim.run(1e-15, dt=1e-15, output_name='drive', save_interval=None,
        scalars=('time', 'mean_m', 'residual', 'mxh'))

sim.close()
