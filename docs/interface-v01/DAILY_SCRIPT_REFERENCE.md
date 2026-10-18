# Daily script: editable blocks and choices

Edit the actual desktop my_case.py. All lengths use m and times use s. The sample stays FiM and preserves its actual values; it is not a generic material or timestep recommendation. The explicit stages are preparation dynamics, static relaxation, prepared-state save, output/solver/current switches, driven dynamics, final state/checkpoint. run_script handles --check, full-list preflight, cancelled exit130 and resource cleanup; no stage is inferred or inserted.

| Block | User choices / required values | Defaults / off / limits |
|---|---|---|
| Task/path | task_name; run_directory(parent,name) creates a unique path value | No files until execution. Old result directories are not reused. |
| Grid | Grid(*, size=None, cells=None, cell_size, boundary='open', origin=(0,0,0), mirrors=(0,0)) | Exactly one size/cells. size,cell_size,origin [m]; integer-compatible extents only, arithmetic-roundoff tolerance8ULP, requested/effective sizes reported. nz=1; thickness=dz. A/B are not two layers. n<=256, aspect<=4, mirrors<=40; open needs zero mirrors. FM open only; FiM also periodic_xy. |
| Model/material | FM(mesh,material,energy) + FMMaterial; FiM + FiMMaterial(A=Sublattice(...),B=Sublattice(...)) | Actual constructors keyword-only. Ms [A/m]>0, alpha [unit1]>=0, gamma_H [m/(A s)]>0 all required. No material database/default; FiM equal_half_volume convention only. |
| Energy | FM: Exchange(A), UniaxialAnisotropy(K1,axis), Demag(), Zeeman(H_ext or B_ext). FiM: FiMExchange(A_A,A_B,Anh=0), OnsiteCoupling(Ah), DMI(D_A,D_B), FiMAnisotropy(K1_A,K1_B,K2_A/B=0,axis_A/B), Demag(), Zeeman | Omit a term to disable; energy=() means none. A/Anh [J/m], Ah/K [J/m3], D [J/m2], H_ext [A/m] or B_ext [T] exactly one. Axes default+z. Anh grouped with FiMExchange; nonzero needs periodic_xy and positive-definite coefficient form. FM DMI/SOT/static unsupported. |
| Initial | Uniform, Smooth, Skyrmion, Antiparallel, LegacyFixture, OVF, real unit-direction array | Required. FM one field; FiM explicit A/B or explicit Antiparallel(A). No implicit B, direct callable or silent array normalization. Examples below. |
| Solver/static | RK4(dt [s]); Evolve(duration [s]); Relax(stop=MaxTransverseField(tolerance [A/m],consecutive=1),method='sdesc') | No hidden preparation or stop threshold; duration exact step multiple. FiM static only, zero current explicitly required, no physical time advance. No user field/wall/RSS/output/update budgets. |
| Excitation | SetField(H_ext=... or B_ext=...); SetCurrent(FiMSOT(J,xi_A,xi_B,incident_direction=(0,0,1),field_like_A/B=0)) | FiMSOT keyword-only; constant in-plane J [A/m2], xi and field_like dimensionless. None disables current. No omitted nonzero field/current, no STT/AC/time function. |
| Scalars | Outputs(scalars=('time','mean_m','energy','dissipation','drive_work','residual'),every=...) selecting only wanted names | scalars=() off. every [s] is recording interval, not dt; None records each accepted step when scalars selected. Must divide by dt exactly. Fields labelled FM or A/B. |
| Snapshots | Outputs(snapshots=interval,snapshot_times=(stage-relative times,...),directory=...) | snapshots=None and snapshot_times=() off; explicit time events and interval must be on steps. No interpolation. Requires directory. Directory defaultsNone; if enabled, each stage also retains result/accepted.state even with snapshot time series off. |
| Analysis | Outputs(analysis=('structure',)) or explicit analyze('structure') | analysis=() defaultoff: no topology/center/radius/contours. Preview never silently turns this on. |
| Preview | Outputs(preview=True,preview_port=8766); explicit sim.preview() | DefaultFalse. One existing unified3D arrow/status UI, real FM/A/B labels; transient bounded16-frame/32MiB memory history. Independent of snapshots/scalars/directory; history expiry explicitly refreshes latest. No extra physical field evaluation, file history or fake static percentage. Whole-protocol lifecycle untilclose. |
| Saves/changes | SaveState(path,strict=False); strict=True checkpoint. SetSolver(RK4(...)); SetOutputs(Outputs(...)) | Explicit stages. Same accepted m/time inherited across dynamics; field/static energy jumps recorded. Strict continuation binds build/history/criterion; change experiment with branch. Existing output root immutable; old legacy checkpoints stay with original tools. |

Defaults and complete coefficient conventions remain in PARAMETERS.md and STATE_AND_CONTINUITY.md. parameters() reports constructors; sim.describe() reports actual effective settings and requested/effective size. No3D solving, spatial materials, thermal/GPU or arbitrary user functions are added. 3D arrows display three direction components of the single physical layer.

## Initial replacements (choose one, not all)

Exact signatures (annotations omitted):

```python
Uniform(direction, normalize=False)
Smooth(*, amplitude)
Skyrmion(*, center, radius, wall, helicity=0.0, polarity=-1)
Antiparallel(A)
LegacyFixture(name)
OVF(*, path, quantity)
```

Magnetization.uniform/smooth/skyrmion/antiparallel/legacy/ovf are aliases with the same signatures. center=(x,y), radius/wall [m], helicity [rad], polarity +/-1; Smooth abs(amplitude)<1. Historical LegacyFixture('canonical_legacy') requires the canonical125x125x1/4x4x3nm/origin0 FiM geometry and is not an equilibrium certificate.

Independent FiM alternatives:

```python
initial = {'A': Uniform((0., 0., 1.)), 'B': Uniform((.1, 0., -1.), normalize=True)}
# 或明确要求 B=-A。
initial = Antiparallel(Skyrmion(center=(200e-9, 300e-9), radius=25e-9, wall=8e-9))
# 或分别读取两份文件；不会自动生成第二子晶格。
initial = {'A': OVF(path='m_A.ovf', quantity='direction'),
           'B': OVF(path='m_B.ovf', quantity='direction')}
```

OVF accepts direction (unit1) or magnetization_Apm [A/m], validates grid/base/spacing and own Ms, and does not restore time/material. No resampling. Every raw field has shape(nz,ny,nx,3) with x fastest, real finite unit vectors m=M/Ms. Raw bool/string/complex/zero/nonunit arrays reject; normalize explicitly before passing if that is intended.

Function sampling is ordinary Python before Simulation, not a new callable initial-state API:

```python
import numpy as np

def sampled_direction(x, y, z):
    phase = 2*np.pi*x/500e-9
    return np.stack((.1*np.cos(phase), .1*np.sin(phase), np.full_like(x, np.sqrt(.99))), axis=-1)

grid = model.mesh
nx, ny, nz = grid.cells
x, y, z = [o+(np.arange(n)+.5)*h for o,n,h in zip(grid.origin,grid.cells,grid.cell_size)]
zz, yy, xx = np.meshgrid(z, y, x, indexing='ij')
a = sampled_direction(xx, yy, zz)
b = np.broadcast_to((0., 0., -1.), a.shape).copy()
initial = {'A': a, 'B': b}
```

No Python function/closure is stored in state; the sampled A/B arrays are the initial data. FM uses a single constructor/array/OVF instead of the A/B dictionary.

The CLI reserves a fresh experiment directory before executing stages, so SaveState(output_dir/'initial.state') may precede the first Evolve/Relax, including nested save folders. --check creates no directory. Existing experiment directories/files and repeated save destinations reject before stage execution. If a paused transient history selection has expired within the same run/instance/stage/configuration, the viewer reads the latest verified frame once, shows an expiry notice and stays paused. A changed identity does not trigger this history recovery; Follow latest remains an explicit action.

## Runner output ownership and save paths

For a planned recorded experiment root R, the whole stage list reserves these namespaces before any write:

| Scope | Runner-owned names | SaveState rule |
|---|---|---|
| Experiment | R directory and R/segments.json index | A user save cannot occupy R, an ancestor of R, the index, or a descendant of the index. |
| Segment directories | R/segment-{index:05d}; numeric names segment-[0-9]{5,} are reserved for segments | A user save cannot be the directory or create it before its own recorded Evolve/Relax. Unknown/future segment directories reject. Global indices include stages with disk output disabled. |
| Direct segment files | accepted.state, result.json, scalars.csv | These names and their descendants cannot be user save targets, even if scalar recording is currently off. |
| Direct segment snapshots | m-{step:012d}.npz; numeric pattern m-[0-9]{12,}.npz | These names and their descendants are reserved even if snapshots are currently off. |

The serializer also uses exclusive random temporary siblings named `<target>.<random>.tmp`, then replaces its own target and removes its temporary file. Their allocation uses mkstemp, which never claims or overwrites an already existing path; they are not stable automatic output targets. Structure analysis is metadata inside result.json, not another implicit file namespace.

All user targets are resolved before checking: relative paths, `..`, and existing parent symlinks are normalized; ownership comparisons conservatively use Unicode normalization and case folding for portable safety on macOS. Existing target files/directories or target symlinks, file-valued parents, and equal/ancestor/descendant overlaps between user saves reject. Canonical targets appear in --check save_targets and are the exact paths executed, so removed `..` components cannot create future segment directories as a side effect. Checks cover the entire sequence before the root is claimed or any earlier save is written. Existing roots still reject, including a competing root created after preflight.

Safe examples are R/initial.state, R/nested/initial.state, and, after segment-00000 has actually been established by its stage, R/segment-00000/user.state or R/segment-00000/custom/accepted.state. In the latter example accepted.state is inside a user-owned subdirectory and does not overlap the direct automatic file. Without any planned recorded stage there is no automatic experiment namespace; standalone saves still undergo existing-data and mutual-path checks. Cancellation continues to prevent all later stages and saves.
