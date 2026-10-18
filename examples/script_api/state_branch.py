# 物理态加载、明确分支和严格恢复分开演示；没有旧样本预算。
from pathlib import Path
import tempfile
import json
import sys
from fimrun.micromagnetics import Grid, FM, FMMaterial, Uniform, Simulation, RK4

model = FM(
    mesh=Grid(cells=(2, 2, 1), cell_size=(4e-9, 4e-9, 3e-9)),
    material=FMMaterial(Ms=8e5, alpha=.02, gamma_H=221088.4),
)
sim = Simulation(model=model, initial=Uniform((1., 0., 0.)), solver=RK4(dt=1e-15))
if '--check' in sys.argv:
    print(json.dumps(sim.describe(), indent=2))
    raise SystemExit(0)

with tempfile.TemporaryDirectory(prefix='micromagnetics-example-') as folder, sim:
    root = Path(folder)
    result = sim.run(duration=2e-15)
    if result.status != 'completed':
        print(result)
        raise SystemExit(130)
    sim.save_state(root / 'physical.state')
    sim.save_checkpoint(root / 'strict.checkpoint')
    with Simulation.load_state(root / 'physical.state') as loaded:
        with loaded.branch(name='new-field', clock='inherit') as child:
            child.set_field(B_ext=(0., 0., 2e-3))
            result = child.run(duration=1e-15)
            if result.status != 'completed':
                print(result)
                raise SystemExit(130)
            assert child.time > loaded.time
    with Simulation.resume_checkpoint(root / 'strict.checkpoint') as exact:
        result = exact.run(duration=1e-15)
        if result.status != 'completed':
            print(result)
            raise SystemExit(130)
        assert exact.restore_grade == 'strict_checkpoint'
    print('State, branch and strict RK4 continuation completed')
