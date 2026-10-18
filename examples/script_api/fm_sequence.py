# 单场 FM：直接动力学、改场、连续运行和保存；数值仅用于演示。
from pathlib import Path
import json
import sys
import uuid
from fimrun.micromagnetics import (
    Grid, FM, FMMaterial, Exchange, Demag, Uniform, Simulation, RK4, Outputs,
)

# 模型与物理项
model = FM(
    mesh=Grid(cells=(4, 3, 1), cell_size=(4e-9, 4e-9, 3e-9)),
    material=FMMaterial(Ms=8e5, alpha=.02, gamma_H=221088.4),
    energy=(Exchange(A=13e-12), Demag()),
)

# 初态与求解器
root = Path(__file__).resolve().parents[2] / 'output' / ('fm-' + uuid.uuid4().hex[:8])
sim = Simulation(
    model=model,
    initial=Uniform((1., .05, .05), normalize=True),
    solver=RK4(dt=1e-15),
    outputs=Outputs(directory=root, scalars=('time', 'mean_m', 'energy'), every=1e-15),
)

# 预检仅描述配置，不创建输出或计算场。
if '--check' in sys.argv:
    print(json.dumps(sim.describe(), indent=2))
    raise SystemExit(0)

# 按实验顺序执行
with sim:
    result = sim.run(duration=2e-15)
    if result.status != 'completed':
        print(result)
        raise SystemExit(130)
    sim.set_field(B_ext=(0., 0., 2e-3))
    result = sim.run(duration=2e-15)
    if result.status != 'completed':
        print(result)
        raise SystemExit(130)
    sim.save_state(root / 'final.state')
    sim.export_magnetization(root / 'm.ovf')
    print(json.dumps(sim.describe(), indent=2))
