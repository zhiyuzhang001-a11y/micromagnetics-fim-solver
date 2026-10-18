# 双场 FiM：非共线初态、静态寻稳、改场和分段电流；数值仅用于演示。
from pathlib import Path
import json
import sys
import uuid
from fimrun.micromagnetics import (
    Grid, FiM, FiMMaterial, Sublattice, FiMExchange, FiMAnisotropy,
    Uniform, Simulation, RK4, Outputs, MaxTransverseField, FiMSOT,
)

# 模型与物理项；未列退磁、DMI或结构分析，因此不计算。
model = FiM(
    mesh=Grid(cells=(3, 3, 1), cell_size=(4e-9, 4e-9, 3e-9)),
    material=FiMMaterial(
        A=Sublattice(Ms=3e5, alpha=.01, gamma_H=221276.1569),
        B=Sublattice(Ms=6e5, alpha=.02, gamma_H=221276.1569),
    ),
    energy=(FiMExchange(A_A=5e-12, A_B=5e-12), FiMAnisotropy(K1_A=1e4, K1_B=2e4)),
)

# 初态、求解器与输出
root = Path(__file__).resolve().parents[2] / 'output' / ('fim-' + uuid.uuid4().hex[:8])
sim = Simulation(
    model=model,
    initial={'A': Uniform((.1, .02, 1.), normalize=True), 'B': Uniform((.02, -.1, -1.), normalize=True)},
    solver=RK4(dt=1e-15),
    outputs=Outputs(directory=root, scalars=('time', 'mean_m', 'energy'), every=1e-15),
)
if '--check' in sys.argv:
    print(json.dumps(sim.describe(), indent=2))
    raise SystemExit(0)

# 独立操作；删除不需要的调用即可，不会补回隐藏阶段。
with sim:
    result = sim.relax(method='sdesc', stop=MaxTransverseField(1.))
    if result.status != 'converged':
        print(result)
        raise SystemExit(130)
    sim.set_field(B_ext=(0., 0., -2e-3))
    sot = FiMSOT(J=(1e11, 0., 0.), xi_A=.1, xi_B=.1)
    sim.set_current(sot)
    result = sim.run(duration=2e-15)
    if result.status != 'completed':
        print(result)
        raise SystemExit(130)
    sim.set_current(None)
    result = sim.run(duration=2e-15)
    if result.status != 'completed':
        print(result)
        raise SystemExit(130)
    sim.save_state(root / 'final.state')
    sim.save_checkpoint(root / 'final.checkpoint')
    sim.export_magnetization({'A': root / 'm_A.ovf', 'B': root / 'm_B.ovf'})
    print(json.dumps(sim.describe(), indent=2))
