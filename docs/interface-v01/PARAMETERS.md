# Public parameters, SI units and model capabilities

Notebook API 1.3 uses the same model/initial constructors, with distinct stage-output and dual-stop semantics documented in [NOTEBOOK_OUTPUTS.md](NOTEBOOK_OUTPUTS.md). Tables below describing Simulation/Outputs remain the core/legacy API.

Import new operations from `fimrun.micromagnetics`. `fimrun.Mesh/Case` retain the old API. Run `parameters()` for exact constructor signatures and required/default fields; `sim.describe()` reports actual effective settings without starting fields, outputs or preview. Keyword-only dataclasses provide IDE completion and reject unknown names. No arbitrary functions, spatial materials, unregistered Python closures or model inference.

## Geometry, model and material

| Constructor | Fields / units / defaults | Conditions and mutation |
|---|---|---|
| Grid | exactly one of size: 3 positive sample lengths [m] or cells: 3 integer counts; cell_size: 3 positive lengths [m] required; origin=(0,0,0) [m]; boundary='open'; mirrors=(0,0) | Single nz=1. XY counts use native index/FFT/displacement capacity and allocation preflight, with no fixed 256-axis cap; see [capacity](../GRID_CAPACITY.md). Aspect <=4 and mirrors 0..40 remain engineering qualification domains, not physics laws. Open requires zero mirrors; periodic_xy requires nx,ny>=3. No region masks/holes in this release: every cell is magnetic. New experiment for grid/boundary/model conversion. |
| FM | mesh:Grid, material:FMMaterial required; energy=() | Exactly one direction field and full-volume energy. Open only. |
| FiM | mesh:Grid, material:FiMMaterial required; energy=() | Two independent fields, open or periodic_xy. |
| FMMaterial / Sublattice | Ms [A/m], alpha [dimensionless], gamma_H [m/(A s)], all required | Ms/gamma>0, alpha>=0, finite; gamma_H is Gilbert H convention, not rad/(T s). Constants only. |
| FiMMaterial | A:Sublattice, B:Sublattice required; convention='equal_half_volume' | No implicit B. No alternative volume fractions. Material changes require branch(model=...). |

$\mathbf M=M_s\mathbf m$ for FM. FiM uses $\overline{\mathbf M}=(M_{s,A}\mathbf m_A+M_{s,B}\mathbf m_B)/2$; local self energies and dissipation/work use half-volume weights. See CONTRACT.md and the unchanged MODEL_AND_UNITS.md convention. m is dimensionless, physical cell volume is the product of cell_size. No default material or legacy field is supplied.

## Explicit energy and torque terms

Omitted terms do not participate. Duplicate/inapplicable terms are rejected. Use a new model on a branch to change terms/material; `set_field` is the supported same-experiment field switch. The local kernel computes field and fused energy together; disabling energy curve output suppresses recording, not the field's shared bookkeeping needed for physical state/energy-switch accounting.

| Constructor | Parameters | Models / equations / dependencies |
|---|---|---|
| Exchange | A>=0 [J/m], required | FM: bond energy $VA\lVert\Delta\mathbf m\rVert^2/h^2$; H bond=$2A\Delta\mathbf m/(\mu_0 M_s h^2)$. |
| FiMExchange | A_A,A_B>=0 [J/m] required; Anh=0 [J/m] | FiM: each self bond $VA_i\lVert\Delta\mathbf m_i\rVert^2/(2h^2)$; cross $VA_{nh}\Delta\mathbf m_A\cdot\Delta\mathbf m_B/(2h^2)$. field coefficients $2A_i$ and $A_{nh}$ divided by own $\mu_0M_{s,i}h^2$. Nonzero Anh requires periodic_xy and $\lvert A_{nh}\rvert<2\sqrt{A_AA_B}$. This term groups A and Anh execution. |
| OnsiteCoupling | Ah [J/m³] required, signed | FiM: $E=-2A_hV\mathbf m_A\cdot\mathbf m_B$; $\mathbf H_i=4A_h\mathbf m_{\rm other}/(\mu_0M_{s,i})$. Negative favors antiparallel with this convention. |
| DMI | D_A,D_B [J/m²] required, signed | FiM only. Positive-neighbor XY bond $E_i=VD_i(m_{i,d}m'_{i,z}-m_{i,z}m'_{i,d})/(2h_d)$, fields are the existing stencil derivative with own Ms. No FM DMI. |
| UniaxialAnisotropy | K1 [J/m³] required; axis=(0,0,1) | FM: $E=VK_1(1-u^2)$, $\mathbf H=2K_1u\mathbf a/(\mu_0M_s)$. Nonzero axis normalized explicitly in configuration. No FM K2. |
| FiMAnisotropy | K1_A,K1_B required; K2_A=K2_B=0 [J/m³]; axis_A=axis_B=(0,0,1) | FiM: $E_i=V(K_{1,i}s+K_{2,i}s^2)/2$, $s=1-u_i^2$; $\mathbf H_i=2u_i(K_{1,i}+2K_{2,i}s)\mathbf a_i/(\mu_0M_{s,i})$. |
| Demag | no arguments | Existing finite-volume Newell/asymptotic tensor, FFT CPU; FM uses its existing Accelerate single-field convolution, FiM uses existing serial FFTW shared Mbar. Open/finite-image periodic support as above. No allocation/generation/FFT when omitted. Kernels retain original reference gates (tensor error $\le10^{-10}$, drift/reciprocity $\le10^{-12}$); engineering checks are not continuum or infinite-PBC certificates. |
| Zeeman | exactly one H_ext [A/m] or B_ext [T], required | FM/FiM: external $\mathbf B_{\rm ext}=\mu_0\mathbf H_{\rm ext}$. Omitted means zero field. set_field(...) inserts/replaces term, records same-m energy jump. No arbitrary time function. |
| FiMSOT | J=(Jx,Jy,0) [A/m²], xi_A,xi_B required; incident_direction=(0,0,1), field_like_A=field_like_B=0 | FiM only, uniform conventional current, $\mathbf q=\mathbf d\times\mathbf J$ with `d=incident_direction`. Existing effective field $\mathbf H_{\rm drive}=-(C/\gamma_H)(\mathbf m\times\mathbf q+r\mathbf q)$, $C=\xi(\mu_B/e)/(M_st)$, with `t=cell_thickness`; existing Gilbert RHS and work. No electrical transport/STT/AC/pulse. None disables; zero J/xi or q skips SOT contribution/work. `with_current_density(J=...)` returns a validated replacement. |

## Initial magnetization

Initial state is required; not providing it is an error. All arrays have shape `(nz,ny,nx,3)` per field, x fastest, finite nonzero unit directions. `sim.m` returns a copy of shape `(1,nz,ny,nx,3)` FM or `(2,nz,ny,nx,3)` FiM. FiM accepts exactly `{'A': ..., 'B': ...}` or explicit Antiparallel. No net-magnetization reconstruction.

| Constructor | Fields | Meaning |
|---|---|---|
| Uniform | direction required; normalize=False | Explicit normalization opt-in; otherwise unit error $\le10^{-12}$ required. |
| Smooth | amplitude required, abs<1 | Existing cosine XY profile about +z. |
| Skyrmion | center=(x,y) [m], radius>0 [m], wall>0 [m] required; helicity=0 [rad], polarity=-1 | Existing tanh radial single-texture formula; polarity +/-1. Only these fields are accepted. |
| Antiparallel | A constructor/array required | Explicitly build $\mathbf m_B=-\mathbf m_A$, only FiM. |
| LegacyFixture | name required | Only 'canonical_legacy', canonical125/4x4x3nm/origin0; material is still explicit. Historical fixture, not generic equilibrium or material qualification. |
| OVF | path, quantity required | quantity='direction' or 'magnetization_Apm'; existing strict rectangular single-segment OVF2 Text/Binary4/Binary8. Grid/base/spacing must match, no interpolation. Ms units/magnitudes validated for magnetization_Apm. Loading is fresh m only, not state/time/material. |

The equivalent factory names are `Magnetization.uniform/smooth/skyrmion/antiparallel/legacy/ovf`.

## Solver, operations and outputs

| Object / method | Parameters and defaults | Contract |
|---|---|---|
| RK4 | dt>0 [s], required | Fixed-step Gilbert LLG, normalized accepted endpoints; no adaptive/thermal solvers. |
| Simulation | model,initial,solver required; outputs=None | Constructor validates/configures, does not evaluate fields, create output or open preview. |
| run | duration>=0 [s], required | Explicit operation, no implicit static/preparation. Integer dt multiple; records physical start/end, inherits accepted m/time/D/P. No experiment-derived resource caps. |
| MaxTransverseField | tolerance>0 [A/m], required; consecutive=1 | Maximum norm of $\mathbf H-(\mathbf m\cdot\mathbf H)\mathbf m$ over all cells and all FiM sublattices, tested on complete accepted updates. |
| relax | method='sdesc' explicitly passed; stop required | FiM native SDesc/BB only, no initial dynamic stage; no physical time advance or invented dynamical loss. No arbitrary max-update budget. FM static explicitly unsupported. Cancel to stop an unattainable request; finite developer watchdogs only exist in tests. |
| set_field | exactly one H_ext/B_ext | Boundary only; same m, same physical time; records DeltaE_switch separately, rebuilds field/cache as needed. |
| set_current | FiMSOT or None | Boundary only; no m/time reset, no hidden material or current; strict-restored objects require branch before change. |
| analyze | name='structure' | Explicit opt-in topology/center/contours/radius; no extra field evaluation. No structure analysis by default. |
| Outputs | directory=None; scalars=(); every=None; snapshots=None; analysis=(); preview=False; preview_port=8766 | No default files/time-series. scalars: time/mean_m/energy/dissipation/drive_work/residual/mxh. mxh is dimensionless transverse H/own Ms. every/snapshots are positive SI durations exactly divisible by dt. every=None means each accepted step when scalars requested. snapshots requires a file directory to write. analysis accepts only ('structure',). Preview is independent, read-only loopback; conflict warns and science continues. |
| Evolve / Relax / SetField / SetCurrent | same operation arguments | Inert descriptors; `sim.execute(stages)` explicitly executes in that order. |

Samples include requested and actual accepted times; no interpolation or hidden rounding. Initial/final rows retain boundary identity and may repeat a timestamp; read_segments() retains them and all switch events. Scalars are explicitly A/B-labelled for FiM. snapshots save m, labels and time; output interval is not solver dt. Reports distinguish completed/converged/cancelled/failed; IO and numeric failures raise their real exceptions after recording what can be retained. User cancellation returns cancelled with last valid state. `with Simulation(...) as sim` closes its native resources and preview.

Outputs.snapshot_times=() adds explicitly requested stage-relative snapshot times [s]; each must be on a fixed dt step and inside that run duration. They coexist with interval snapshots and preserve old explicit endpoint/event intent without introducing event clipping. Static operations write only requested final snapshots/scalars at unchanged physical time; no pseudo-time is labelled as experiment time. set_solver(RK4(dt=...)) explicitly changes dt at an ordinary stage boundary and validates the current sampling plan; strict-restored trajectories must branch before doing so.

`set_outputs(Outputs(...))` validates a new sampling plan at a stage boundary. An established file root cannot silently move; choose a branch for another destination. When file output is enabled, each operation retains a final accepted.state recovery record independently of snapshot time series. `directory=None` writes no files. In-memory magnetization arrays must have real numeric dtypes; string, bool and complex arrays are rejected without coercing them into physical directions. Uniform.normalize must be a real bool.

`sim.check(duration=...)` can also validate a planned duration and snapshot event domain without any field/model execution or output creation; loading the shared library checks its installed dependencies only. `sim.preview()` explicitly displays a loaded/current physical state without advancing dynamics or requesting fields/analysis. Use close() to stop its own service.

MaxTransverseField.consecutive counts distinct accepted states; the initial state is evaluated once. Cancellation or failure before a new candidate is accepted cannot add a second count. Strict static checkpoints bind both this stopping position and the exact tolerance/consecutive criterion; changing it requires a branch. Ordinary new criteria reset only their consecutive count.

Daily size/stages/unified viewer revision: see DAILY_SCRIPT_REFERENCE.md. Grid.size is the effective cells*cell_size; requested_size is provenance only and excluded from physics equality/kernel identity. Nonmultiple physical sizes reject rather than silently changing geometry; arithmetic-roundoff differences are described. The old cells constructor and physical state decoding remain compatible. SetSolver, SetOutputs and SaveState are explicit inert stage descriptors; run_script validates the complete list before execution and propagates cancellation exit130. Preview uses the packaged common viewer with 2D/3D, labelled axes, cached residual/mxh, and a versioned transient source. Raw direction history is bounded to16 packets/32MiB plus at most2 display-response caches; this is not a total process RSS guarantee.

## Mathematical notation and exact signatures

Use the [formula/code map](../MATHEMATICS.md) for rendered definitions and [complete API signature reference](../API_REFERENCE.md) for public constructors, inherited methods, aliases and defaults. Tables above retain the core API distinction; the Notebook API1.3 output aliases are listed separately.

## Notebook1.4简洁入口

构造model/initial/output_dir即显示初态，无动态dt。run(name,dt,duration)参数用关键字；relax(name,mxh,residual,save_step)按接受态双门收敛、无固定迭代上限。完整默认/旧接口兼容/频率继承和能量列见[当前输出合同](NOTEBOOK_OUTPUTS.md)。
