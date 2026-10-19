"""Small tutorial; run in a new working directory with the installed environment."""
from pathlib import Path
import fimrun.micromagnetics as mm
from fimrun.notebook import NotebookSimulation


grid = mm.Grid(cells=(3, 3, 1), cell_size=(4e-9, 4e-9, 3e-9))  # m
sub_A = mm.Sublattice(Ms=3e5, alpha=0.01, gamma_H=2e5)
sub_B = mm.Sublattice(Ms=6e5, alpha=0.01, gamma_H=2e5)
model = mm.FiM(mesh=grid, material=mm.FiMMaterial(A=sub_A, B=sub_B),
            energy=(mm.FiMAnisotropy(K1_A=1e4, K1_B=2e4),))
initial = mm.Antiparallel(mm.Uniform((0., 0., 1.)))


output_dir = (Path.cwd() / 'results' / 'new_notebook_demo').resolve()
sim = NotebookSimulation(model=model, initial=initial, output_dir=output_dir)
sim


sim.relax(name='static', mxh=1e-5, residual=1.0, save_step=1)


sim.set_current(mm.FiMSOT(J=(1e11, 0., 0.), xi_A=0.1, xi_B=-0.1,
    incident_direction=(0., 0., 1.), field_like_A=0., field_like_B=0.))


sim.run(name='drive', dt=1e-15, duration=1e-15, save_interval=1e-15)


sim.save('final.state')
sim.export_ovf('current')


sim.close()
