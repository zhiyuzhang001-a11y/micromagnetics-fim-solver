# Public parameters, SI units and model capabilities

Notebook API 1.2 uses the same model/initial constructors, with distinct stage-output and dual-stop semantics documented in [NOTEBOOK_OUTPUTS.md](NOTEBOOK_OUTPUTS.md). Tables below describing Simulation/Outputs remain the core/legacy API.

Import new operations from `fimrun.micromagnetics`. `fimrun.Mesh/Case` retain the old API. Run `parameters()` for exact constructor signatures and required/default fields; `sim.describe()` reports actual effective settings without starting fields, outputs or preview. Keyword-only dataclasses provide IDE completion and reject unknown names. No arbitrary functions, spatial materials, unregistered Python closures or model inference.

## Geometry, model and material

| Constructor | Fields / units / defaults | Conditions and mutation |
|---|---|---|
| Grid | exactly one of size: 3 positive sample lengths [m] or cells: 3 integer counts; cell_size: 3 positive lengths [m] required; origin=(0,0,0) [m]; boundary='open'; mirrors=(0,0) | Single nz=1. Implemented n 1..256, aspect <=4, mirrors 0..40; these are geometry/implementation support domains, not physics laws. Open requires zero mirrors; periodic_xy requires nx,ny>=3. No region masks/holes in this release: every cell is magnetic. New experiment for grid/boundary/model conversion. |
| FM | mesh:Grid, material:FMMaterial required; energy=() | Exactly one direction field and full-volume energy. Open only. |
| FiM | mesh:Grid, material:FiMMaterial required; energy=() | Two independent fields, open or periodic_xy. |
| FMMaterial / Sublattice | Ms [A/m], alpha [dimensionless], gamma_H [m/(A s)], all required | Ms/gamma>0, alpha>=0, finite; gamma_H is Gilbert H convention, not rad/(T s). Constants only. |
| FiMMaterial | A:Sublattice, B:Sublattice required; convention='equal_half_volume' | No implicit B. No alternative volume fractions. Material changes require branch(model=...). |

`M=Ms*m` for FM. FiM uses `Mbar=(Ms_A*m_A+Ms_B*m_B)/2`; local self energies and dissipation/work use half-volume weights. See CONTRACT.md and the unchanged MODEL_AND_UNITS.md convention. m is dimensionless, physical cell volume is the product of cell_size. No default material or legacy field is supplied.

## Explicit energy and torque terms

Omitted terms do not participate. Duplicate/inapplicable terms are rejected. Use a new model on a branch to change terms/material; `set_field` is the supported same-experiment field switch. The local kernel computes field and fused energy together; disabling energy curve output suppresses recording, not the field's shared bookkeeping needed for physical state/energy-switch accounting.

| Constructor | Parameters | Models / equations / dependencies |
|---|---|---|
| Exchange | A>=0 [J/m], required | FM: bond energy V*A*|delta m|²/h²; H bond=2A*delta m/(mu0*Ms*h²). |
| FiMExchange | A_A,A_B>=0 [J/m] required; Anh=0 [J/m] | FiM: each self bond V/2*A_i*|delta m_i|²/h²; cross .5*V*Anh*dot(delta m_A,delta m_B)/h². H self factor2A_i and cross Anh over own mu0*Ms_i*h². Nonzero Anh requires periodic_xy and abs(Anh)<2*sqrt(A_A*A_B). This term groups A and Anh execution. |
| OnsiteCoupling | Ah [J/m³] required, signed | FiM: E=-2*Ah*V*dot(m_A,m_B); H_i=4*Ah*m_other/(mu0*Ms_i). Negative favors antiparallel with this convention. |
| DMI | D_A,D_B [J/m²] required, signed | FiM only. Positive-neighbor XY bond E_i=.5*V*D_i*(m_i[d]*neighbor.z-m_i.z*neighbor[d])/h_d, fields are the existing stencil derivative with own Ms. No FM DMI. |
| UniaxialAnisotropy | K1 [J/m³] required; axis=(0,0,1) | FM: E=V*K1*(1-u²), H=2*K1*u*axis/(mu0*Ms). Nonzero axis normalized explicitly in configuration. No FM K2. |
| FiMAnisotropy | K1_A,K1_B required; K2_A=K2_B=0 [J/m³]; axis_A=axis_B=(0,0,1) | FiM: E_i=V/2*(K1_i*s+K2_i*s²), s=1-u_i²; H_i=2*u_i*(K1_i+2*K2_i*s)*axis_i/(mu0*Ms_i). |
| Demag | no arguments | Existing finite-volume Newell/asymptotic tensor, FFT CPU; FM uses its existing Accelerate single-field convolution, FiM uses existing serial FFTW shared Mbar. Open/finite-image periodic support as above. No allocation/generation/FFT when omitted. Kernels retain original reference gates (tensor error<=1e-10, drift/reciprocity<=1e-12); engineering checks are not continuum or infinite-PBC certificates. |
| Zeeman | exactly one H_ext [A/m] or B_ext [T], required | FM/FiM: external B_ext=mu0*H_ext. Omitted means zero field. set_field(...) inserts/replaces term, records same-m energy jump. No arbitrary time function. |
| FiMSOT | J=(Jx,Jy,0) [A/m²], xi_A,xi_B required; incident_direction=(0,0,1), field_like_A=field_like_B=0 | FiM only, uniform conventional current, q=incident_direction cross J. Existing effective field=-C/gamma_H*(m cross q+r*q), C=xi*(muB/e)/(Ms*cell_thickness); existing Gilbert RHS and work. No electrical transport/STT/AC/pulse. None disables; zero J/xi or q skips SOT contribution/work. `with_current_density(J=...)` returns a validated replacement. |

## Initial magnetization

Initial state is required; not providing it is an error. All arrays have shape `(nz,ny,nx,3)` per field, x fastest, finite nonzero unit directions. `sim.m` returns a copy of shape `(1,nz,ny,nx,3)` FM or `(2,nz,ny,nx,3)` FiM. FiM accepts exactly `{'A': ..., 'B': ...}` or explicit Antiparallel. No net-magnetization reconstruction.

| Constructor | Fields | Meaning |
|---|---|---|
| Uniform | direction required; normalize=False | Explicit normalization opt-in; otherwise unit error<=1e-12 required. |
| Smooth | amplitude required, abs<1 | Existing cosine XY profile about +z. |
| Skyrmion | center=(x,y) [m], radius>0 [m], wall>0 [m] required; helicity=0 [rad], polarity=-1 | Existing tanh radial single-texture formula; polarity +/-1. Only these fields are accepted. |
| Antiparallel | A constructor/array required | Explicitly build B=-A, only FiM. |
| LegacyFixture | name required | Only 'canonical_legacy', canonical125/4x4x3nm/origin0; material is still explicit. Historical fixture, not generic equilibrium or material qualification. |
| OVF | path, quantity required | quantity='direction' or 'magnetization_Apm'; existing strict rectangular single-segment OVF2 Text/Binary4/Binary8. Grid/base/spacing must match, no interpolation. Ms units/magnitudes validated for magnetization_Apm. Loading is fresh m only, not state/time/material. |

The equivalent factory names are `Magnetization.uniform/smooth/skyrmion/antiparallel/legacy/ovf`.

## Solver, operations and outputs

| Object / method | Parameters and defaults | Contract |
|---|---|---|
| RK4 | dt>0 [s], required | Fixed-step Gilbert LLG, normalized accepted endpoints; no adaptive/thermal solvers. |
| Simulation | model,initial,solver required; outputs=None | Constructor validates/configures, does not evaluate fields, create output or open preview. |
| run | duration>=0 [s], required | Explicit operation, no implicit static/preparation. Integer dt multiple; records physical start/end, inherits accepted m/time/D/P. No experiment-derived resource caps. |
| MaxTransverseField | tolerance>0 [A/m], required; consecutive=1 | Maximum norm of H-(m.H)m over all cells and all FiM sublattices, tested on complete accepted updates. |
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
