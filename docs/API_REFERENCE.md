# API reference — candidate v1

This reference describes the source candidate. The accepted installed wheel remains unchanged. All new physics inputs use SI; [parameter units/choices/support](interface-v01/PARAMETERS.md), [Notebook API1.4 outputs/defaults](interface-v01/NOTEBOOK_OUTPUTS.md), [state semantics](interface-v01/STATE_AND_CONTINUITY.md), and [formula/code map](MATHEMATICS.md) are normative companions. Legacy Case is separate and retains historical defaults.

## Offline result facade

`analyze(source, *, stage=None, segment=None, calibration=None, assume_temporal_sampling=False, ab_reference=None, velocity_window_s=None) -> Analysis`

| Parameter | Default, choices, units, failure |
|---|---|
| source | Required state str/Path or concrete list of frame dicts; not rows/directories/globs. Frame keys A/B/state/csv/packet/mapping retain the low-level contract |
| stage | None; explicit rk4/sdesc only. Ambiguous groups require selection; no match/unknown selector raises ValueError |
| segment | None or nonempty exact id; facts must establish selection uniquely |
| calibration | None means frozen calibration_v1.json; path or validated mapping; thresholds unchanged |
| assume_temporal_sampling | False; real bool. True asserts actual displacement under half-box, not automatically certified |
| ab_reference | None or 'antiparallel'; does not automatically infer material reference |
| velocity_window_s | None or two finite increasing seconds; explicit linear window fit |

State input validates the entire inventory, then requires every frame to have independent OVF or unique bound CSV evidence of the last segment, stage and run. Historical different-stage, same-stage earlier segment, unknown binding and conflicting facts reject the whole request even with an explicit latest selector. No automatic overrides, history reconstruction or sorting. Explicit frame selection preserves relative order. `source_indices` maps to original source positions; `input_index` indexes the selected analysis.

`Analysis.rows` is a recursively read-only snapshot. Methods do not reread or reanalyze. There is no supported public constructor.

| Method | Return, defaults and side effects |
|---|---|
| show() | IPython.display.HTML; state/validity/reasons, default table and center/radius/shape/helicity SVGs; no writes |
| table(*, metrics=None, sublattice='both') | HTML; default metrics center/radius/shape/helicity; SI values, flags/reasons and source index |
| plot(metric, *, sublattice='both', output=None) | SVG; optional new SVG path writes exclusively. Lengths nm, time ps, velocity m/s, phase rad; units separated by panel |
| to_csv(path) | Path; exclusive full SI audit CSV plus source_index; independent of display selection |

Metrics: center, topology_center, radius, shape, axis, helicity, topology, relative, velocity. Sublattice: A/B/both; relative requires both. Invalid selector/combination raises ValueError. Valid metric with no valid samples yields an explicit empty/invalid view, never zeros. Empty submission and zero-valid completed analysis differ. Missing dynamic clocks yield source-index scatter, no time interpolation/velocity. Static uses iteration, not physical time. FileExistsError for existing exports; ValueError if output aliases an input. No implicit renaming/overwrite. See [detailed source and error contract](interface-v01/SKYRMION_POSTPROCESSING.md).

## Existing low-level postprocessing (compatible)

| Function | Parameters/defaults, return and restriction |
|---|---|
| analyze_ovf(frames, output, *, calibration=None, assume_temporal_sampling=False, ab_reference=None, velocity_window_s=None) | list of dict rows; creates an exclusive CSV; options as above. Existing per-frame exception boundary retained |
| frames_from_state(path) | list of frame dicts; complete flat inventory required. Existing helper enumerates stages; resolver uses last state segment. Does not itself implement arbitrary historical segment selection |
| read_ovf(path, *, Ms=None, legacy=None) | dict of m/cells/h/origin/fields/normalization/hash. Unit directions need no Ms; A/m needs own positive Ms. Legacy missing quantity/origin/declared binary32-roundoff only through explicit evidence mapping |
| summary_svg(rows) | single-stage SVG string, no write. Original behavior unchanged; missing rk4 time can leave scalar panels empty. New facade supplies index-scatter view |
| generate_demo(output) | rows; creates new directory with five pairs, inputs.json and analysis.csv. Existing path rejected; not a frame-returning API |
| calibrate() | development calibration result; never run implicitly and never replace the frozen calibration for convenience |

Global calibration/options/container errors abort requests; not every error becomes a row. Once submitted, enumerable per-frame errors within the original capture boundary keep reason_codes/NaN. Bad archives, IO and unexpected program errors retain exceptions. Source changes after selection reject instead of silently changing scope.

## Simulation parameter and inheritance guide

Constructors below list required/default fields and exact source signatures. Units and supported combinations are the linked parameter table above, not guessed from Python type alone. All Ms>0 [A/m], alpha>=0 [1], gamma_H>0 [m/(A s)], geometry lengths [m], time [s], fields H [A/m] or B [T], currents [A/m²], energies [J]; coefficient units A/Anh [J/m], Ah/K [J/m³], D [J/m²]. Initial directions are dimensionless; phases [rad]. Selectors/paths/booleans have no physical unit. Model-specific unsupported combinations raise validation errors rather than being ignored.

Core Simulation.run takes keyword duration; NotebookSimulation.run accepts duration by keyword or position. Core relax requires method and stop; Notebook1.4 relax requires mxh and defaults residual=1 A/m/consecutive=1. Never mix their signatures. Output UNSET means preserve/inherit the current stage setting, not Python None. save_interval/every alias is dynamic seconds; save_step is static accepted iterations; save_every_steps/every are compatibility aliases. Conflicting aliases reject. Legacy results/name constructor and old positional relax retain separate semantics; use output_dir for the new interface.

Notebook constructor replaces only an idle same-name instance by default, preserving protected outputs. Reusing an output name invokes the existing explicit overwrite interaction, not silent append. State restore cannot load over an active instance; strict compatibility checks remain unchanged. The simplified no-dt constructor opens the same initial-state viewer by default; the old dt constructor keeps preview=False by default. Preview starts a loopback service; none of the postprocessing methods do so.


## fimrun/micromagnetics/model.py

### Grid

[Definition](../fimrun/micromagnetics/model.py#L32).

| Field | Type | Default / required |
|---|---|---|
| cells | `tuple[int, int, int]` | `None; exactly one of size/cells` |
| size | `Vec3` | `None; exactly one of size/cells` |
| cell_size | `Vec3` | `required` |
| boundary | `Literal['open', 'periodic_xy']` | `'open'` |
| origin | `Vec3` | `(0.0, 0.0, 0.0)` |
| mirrors | `tuple[int, int]` | `(0, 0)` |

```python
Grid.__init__(self, *, cell_size: Vec3, size: Vec3 | None=None, cells: tuple[int, int, int] | None=None, boundary: Literal['open', 'periodic_xy']='open', origin: Vec3=(0.0, 0.0, 0.0), mirrors: tuple[int, int]=(0, 0))
```

```python
Grid.size(self)
```
Decorators: `property`.

```python
Grid.requested_size(self)
```
Decorators: `property`.

```python
Grid.shape(self)
```
Decorators: `property`.

### Sublattice

[Definition](../fimrun/micromagnetics/model.py#L106).

| Field | Type | Default / required |
|---|---|---|
| Ms | `float` | `required` |
| alpha | `float` | `required` |
| gamma_H | `float` | `required` |

### FMMaterial

[Definition](../fimrun/micromagnetics/model.py#L120).

Bases: `Sublattice`. Inherited public members remain available; overridden methods below take precedence.

### FiMMaterial

[Definition](../fimrun/micromagnetics/model.py#L125).

| Field | Type | Default / required |
|---|---|---|
| A | `Sublattice` | `required` |
| B | `Sublattice` | `required` |
| convention | `Literal['equal_half_volume']` | `'equal_half_volume'` |

### Exchange

[Definition](../fimrun/micromagnetics/model.py#L138).

| Field | Type | Default / required |
|---|---|---|
| A | `float` | `required` |

### FiMExchange

[Definition](../fimrun/micromagnetics/model.py#L146).

| Field | Type | Default / required |
|---|---|---|
| A_A | `float` | `required` |
| A_B | `float` | `required` |
| Anh | `float` | `0.0` |

### OnsiteCoupling

[Definition](../fimrun/micromagnetics/model.py#L160).

| Field | Type | Default / required |
|---|---|---|
| Ah | `float` | `required` |

### DMI

[Definition](../fimrun/micromagnetics/model.py#L168).

| Field | Type | Default / required |
|---|---|---|
| D_A | `float` | `required` |
| D_B | `float` | `required` |

### UniaxialAnisotropy

[Definition](../fimrun/micromagnetics/model.py#L178).

| Field | Type | Default / required |
|---|---|---|
| K1 | `float` | `required` |
| axis | `Vec3` | `(0.0, 0.0, 1.0)` |

### FiMAnisotropy

[Definition](../fimrun/micromagnetics/model.py#L188).

| Field | Type | Default / required |
|---|---|---|
| K1_A | `float` | `required` |
| K1_B | `float` | `required` |
| K2_A | `float` | `0.0` |
| K2_B | `float` | `0.0` |
| axis_A | `Vec3` | `(0.0, 0.0, 1.0)` |
| axis_B | `Vec3` | `(0.0, 0.0, 1.0)` |

### Demag

[Definition](../fimrun/micromagnetics/model.py#L204).

### Zeeman

[Definition](../fimrun/micromagnetics/model.py#L209).

| Field | Type | Default / required |
|---|---|---|
| H_ext | `Vec3 \| None` | `None` |
| B_ext | `Vec3 \| None` | `None` |

```python
Zeeman.H(self)
```
Decorators: `property`.

### FiMSOT

[Definition](../fimrun/micromagnetics/model.py#L225).

| Field | Type | Default / required |
|---|---|---|
| J | `Vec3` | `required` |
| xi_A | `float` | `required` |
| xi_B | `float` | `required` |
| incident_direction | `Vec3` | `(0.0, 0.0, 1.0)` |
| field_like_A | `float` | `0.0` |
| field_like_B | `float` | `0.0` |

```python
FiMSOT.with_current_density(self, *, J)
```

### FM

[Definition](../fimrun/micromagnetics/model.py#L246).

| Field | Type | Default / required |
|---|---|---|
| mesh | `Grid` | `required` |
| material | `FMMaterial` | `required` |
| energy | `tuple` | `()` |

```python
FM.labels(self)
```
Decorators: `property`.

### FiM

[Definition](../fimrun/micromagnetics/model.py#L264).

| Field | Type | Default / required |
|---|---|---|
| mesh | `Grid` | `required` |
| material | `FiMMaterial` | `required` |
| energy | `tuple` | `()` |

```python
FiM.labels(self)
```
Decorators: `property`.

## fimrun/micromagnetics/initial.py

### Uniform

[Definition](../fimrun/micromagnetics/initial.py#L10).

| Field | Type | Default / required |
|---|---|---|
| direction | `tuple` | `required` |
| normalize | `bool` | `False` |

```python
Uniform.generate(self, grid)
```

### Smooth

[Definition](../fimrun/micromagnetics/initial.py#L25).

| Field | Type | Default / required |
|---|---|---|
| amplitude | `float` | `required` |

```python
Smooth.generate(self, grid)
```

### Skyrmion

[Definition](../fimrun/micromagnetics/initial.py#L39).

| Field | Type | Default / required |
|---|---|---|
| center | `tuple` | `required` |
| radius | `float` | `required` |
| wall | `float` | `required` |
| helicity | `float` | `0.0` |
| polarity | `int` | `-1` |

```python
Skyrmion.generate(self, grid)
```

### Antiparallel

[Definition](../fimrun/micromagnetics/initial.py#L65).

| Field | Type | Default / required |
|---|---|---|
| A | `object` | `required` |

### LegacyFixture

[Definition](../fimrun/micromagnetics/initial.py#L70).

| Field | Type | Default / required |
|---|---|---|
| name | `str` | `required` |

### OVF

[Definition](../fimrun/micromagnetics/initial.py#L75).

| Field | Type | Default / required |
|---|---|---|
| path | `str` | `required` |
| quantity | `str` | `required` |

```python
OVF.generate(self, grid, Ms)
```

### Magnetization

[Definition](../fimrun/micromagnetics/initial.py#L87).

Alias/factory: `uniform = Uniform`.

Alias/factory: `smooth = Smooth`.

Alias/factory: `skyrmion = Skyrmion`.

Alias/factory: `antiparallel = Antiparallel`.

Alias/factory: `legacy = LegacyFixture`.

Alias/factory: `ovf = OVF`.

## fimrun/micromagnetics/simulation.py

### RK4

[Definition](../fimrun/micromagnetics/simulation.py#L20).

| Field | Type | Default / required |
|---|---|---|
| dt | `float` | `required` |

### MaxTransverseField

[Definition](../fimrun/micromagnetics/simulation.py#L49).

| Field | Type | Default / required |
|---|---|---|
| tolerance | `float` | `required` |
| consecutive | `int` | `1` |

### Outputs

[Definition](../fimrun/micromagnetics/simulation.py#L74).

| Field | Type | Default / required |
|---|---|---|
| directory | `str \| Path \| None` | `None` |
| scalars | `tuple[str, ...]` | `()` |
| every | `float \| None` | `None` |
| snapshots | `float \| None` | `None` |
| snapshot_times | `tuple[float, ...]` | `()` |
| analysis | `tuple[str, ...]` | `()` |
| preview | `bool` | `False` |
| preview_port | `int` | `8766` |

### RunResult

[Definition](../fimrun/micromagnetics/simulation.py#L104).

| Field | Type | Default / required |
|---|---|---|
| status | `str` | `required` |
| t_start | `float` | `required` |
| t_end | `float` | `required` |
| steps | `int` | `required` |
| residual_Apm | `tuple \| None` | `required` |
| error | `str \| None` | `required` |
| segment_id | `str` | `required` |

### Simulation

[Definition](../fimrun/micromagnetics/simulation.py#L125) · [Constructor](../fimrun/micromagnetics/simulation.py#L126).

```python
Simulation.__init__(self, *, model: FM | FiM, initial, solver: RK4 | None=None, outputs: Outputs | None=None)
```

Omitting `solver`, or passing `None`, leaves the physical dynamic step unconfigured (`sim.solver.dt is None`). This supports the existing FiM static relaxation without inventing a dynamic `dt`; FM static relaxation remains unsupported. Before core `run(duration=...)`, configure `sim.set_solver(RK4(dt=...))`. Physical-time output intervals also require a configured dynamic step. `set_solver` still accepts `RK4`, not `None`. The Notebook facade supplies the per-call dynamic `dt` through `run(name=..., dt=..., duration=...)`.

```python
Simulation.time(self)
```
Decorators: `property`.

```python
Simulation.model(self)
```
Decorators: `property`.

```python
Simulation.solver(self)
```
Decorators: `property`.

```python
Simulation.m(self)
```
Decorators: `property`.

```python
Simulation.outputs(self)
```
Decorators: `property`.

```python
Simulation.current(self)
```
Decorators: `property`.

```python
Simulation.labels(self)
```
Decorators: `property`.

```python
Simulation.check(self, *, duration=None)
```

```python
Simulation.describe(self)
```

Alias/factory: `parameters = describe`.

```python
Simulation.metrics(self)
```

```python
Simulation.run(self, *, duration: float)
```

```python
Simulation.relax(self, *, method, stop: MaxTransverseField)
```

```python
Simulation.set_field(self, *, H_ext=None, B_ext=None)
```

```python
Simulation.set_outputs(self, outputs: Outputs)
```

```python
Simulation.set_solver(self, solver: RK4)
```

```python
Simulation.set_current(self, current: FiMSOT | None)
```

```python
Simulation.branch(self, *, name, clock='inherit', model=None, outputs=None)
```

```python
Simulation.initialize(self, initial)
```

```python
Simulation.analyze(self, name='structure')
```

```python
Simulation.execute(self, stages)
```

```python
Simulation.save_state(self, path)
```

```python
Simulation.save_checkpoint(self, path)
```

```python
Simulation.load_state(cls, path, *, outputs=None)
```
Decorators: `classmethod`.

```python
Simulation.resume_checkpoint(cls, path, *, outputs=None)
```
Decorators: `classmethod`.

```python
Simulation.export_magnetization(self, paths)
```

```python
Simulation.preview(self)
```

```python
Simulation.close(self)
```

## fimrun/micromagnetics/stages.py

### Evolve

[Definition](../fimrun/micromagnetics/stages.py#L9).

| Field | Type | Default / required |
|---|---|---|
| duration | `float` | `required` |

```python
Evolve.execute(self, sim)
```

### Relax

[Definition](../fimrun/micromagnetics/stages.py#L17).

| Field | Type | Default / required |
|---|---|---|
| stop | `MaxTransverseField` | `required` |
| method | `str` | `'sdesc'` |

```python
Relax.execute(self, sim)
```

### SetField

[Definition](../fimrun/micromagnetics/stages.py#L26).

| Field | Type | Default / required |
|---|---|---|
| H_ext | `tuple \| None` | `None` |
| B_ext | `tuple \| None` | `None` |

```python
SetField.execute(self, sim)
```

### SetCurrent

[Definition](../fimrun/micromagnetics/stages.py#L35).

| Field | Type | Default / required |
|---|---|---|
| current | `FiMSOT \| None` | `required` |

```python
SetCurrent.execute(self, sim)
```

### SetSolver

[Definition](../fimrun/micromagnetics/stages.py#L43).

| Field | Type | Default / required |
|---|---|---|
| solver | `RK4` | `required` |

```python
SetSolver.execute(self, sim)
```

### SetOutputs

[Definition](../fimrun/micromagnetics/stages.py#L51).

| Field | Type | Default / required |
|---|---|---|
| outputs | `Outputs` | `required` |

```python
SetOutputs.execute(self, sim)
```

### SaveState

[Definition](../fimrun/micromagnetics/stages.py#L59).

| Field | Type | Default / required |
|---|---|---|
| path | `str \| Path` | `required` |
| strict | `bool` | `False` |

```python
SaveState.execute(self, sim)
```

## fimrun/micromagnetics/script.py

### check_stages

[Definition](../fimrun/micromagnetics/script.py#L60).

```python
check_stages(sim, stages)
```

### run_script

[Definition](../fimrun/micromagnetics/script.py#L112).

```python
run_script(*, model, initial, solver, outputs=None, stages, argv=None)
```

### run_directory

[Definition](../fimrun/micromagnetics/script.py#L142).

```python
run_directory(parent, name)
```

## fimrun/micromagnetics/persistence.py

### read_segments

[Definition](../fimrun/micromagnetics/persistence.py#L311).

```python
read_segments(directory)
```

## fimrun/micromagnetics/reference.py

### parameters

[Definition](../fimrun/micromagnetics/reference.py#L7).

```python
parameters()
```

## fimrun/notebook.py

### module_identity

[Definition](../fimrun/notebook.py#L20).

```python
module_identity(core_dir)
```

### summary

[Definition](../fimrun/notebook.py#L47).

```python
summary(result: RunResult)
```

### configuration_summary

[Definition](../fimrun/notebook.py#L65).

```python
configuration_summary(model, active=None)
```

### NotebookSession

[Definition](../fimrun/notebook.py#L72).

```python
NotebookSession.__init__(self, sim, directory)
```

```python
NotebookSession.preview(self, sim)
```

```python
NotebookSession.start(cls, *, model, initial, solver, parent, name='experiment', output_settings=None, previous=None)
```
Decorators: `classmethod`.

```python
NotebookSession.load(cls, path, *, parent, name='restored', checkpoint=False, previous=None)
```
Decorators: `classmethod`.

```python
NotebookSession.outputs(self, **settings)
```

```python
NotebookSession.save(self, name, *, checkpoint=False)
```

```python
NotebookSession.info(self)
```

```python
NotebookSession.close(self)
```

### NotebookResult

[Definition](../fimrun/notebook.py#L219).

```python
NotebookResult.__init__(self, value)
```

### NotebookSimulation — current API1.4

[Definition](../fimrun/notebook.py#L512).

Bases: `_LegacyNotebookSimulation`. Inherited public members remain available; overridden methods below take precedence.

```python
NotebookSimulation.__init__(self, *, model, initial, dt=notebook_flat.UNSET, output_dir=notebook_flat.UNSET, output_name='experiment', save_interval=notebook_flat.UNSET, every=notebook_flat.UNSET, scalars=notebook_flat.UNSET, magnetization=True, preview=notebook_flat.UNSET, preview_port=8766, replace=True, **legacy)
```

```python
NotebookSimulation.run(self, duration, *, dt=None, name=notebook_flat.UNSET, output_name=notebook_flat.UNSET, save_interval=notebook_flat.UNSET, every=notebook_flat.UNSET, scalars=notebook_flat.UNSET, magnetization=notebook_flat.UNSET)
```

```python
NotebookSimulation.relax(self, *args, mxh=notebook_flat.UNSET, residual=1.0, consecutive=1, name=notebook_flat.UNSET, output_name=notebook_flat.UNSET, save_step=notebook_flat.UNSET, save_every_steps=notebook_flat.UNSET, every=notebook_flat.UNSET, scalars=notebook_flat.UNSET, magnetization=notebook_flat.UNSET, **legacy)
```

```python
NotebookSimulation.load(cls, path, *, output_dir=notebook_flat.UNSET, name=notebook_flat.UNSET, output_name=notebook_flat.UNSET, checkpoint=False, **legacy)
```
Decorators: `classmethod`.

```python
NotebookSimulation.output_dir(self)
```
Decorators: `property`.

```python
NotebookSimulation.output_name(self)
```
Decorators: `property`.

```python
NotebookSimulation.metrics(self)
```

### Inherited public members from the compatibility parent

[Parent definition](../fimrun/notebook.py#L243). Only inherited members are shown below; legacy results/name and positional-tolerance constructors are not the current API. Use the current API1.4 signatures above.

```python
NotebookSimulation.set_current(self, current)
```
Set supported FiMSOT, or explicitly disable it with None.

```python
NotebookSimulation.set_field(self, *, H_ext=None, B_ext=None)
```
H_ext [A/m] or B_ext [T], following the core Zeeman convention.

```python
NotebookSimulation.preview(self)
```
Show the same unified3D viewer without a field evaluation.

```python
NotebookSimulation.save(self, name, *, checkpoint=False)
```
Save a new filename under this experiment's states directory.

```python
NotebookSimulation.export_ovf(self, name='magnetization')
```
Export a new A/B OVF2 Text packet of unit directions; no evaluation.

```python
NotebookSimulation.close(self)
```
Close resources and release this active name; safe to call twice.

```python
NotebookSimulation.closed(self)
```
Decorators: `property`.

```python
NotebookSimulation.m(self)
```
Decorators: `property`.

```python
NotebookSimulation.time(self)
```
Decorators: `property`.

```python
NotebookSimulation.snapshot_format(self)
```
Decorators: `property`.

```python
NotebookSimulation.dt(self)
```
Decorators: `property`.

```python
NotebookSimulation.dissipation(self)
```
Decorators: `property`.

```python
NotebookSimulation.drive_work(self)
```
Decorators: `property`.

```python
NotebookSimulation.run_id(self)
```
Decorators: `property`.

```python
NotebookSimulation.directory(self)
```
Decorators: `property`.

## Inherited Notebook API1.4 members

The final NotebookSimulation derives from the earlier facade class retained as `_LegacyNotebookSimulation` in the same source. Both definitions above are indexed. Final run/relax/load/metrics/output properties override the parent; inherited set_current, set_field, preview, save, export_ovf, close, closed/m/time/snapshot_format/dt/dissipation/drive_work/run_id/directory remain public. NotebookResult delegates RunResult attributes through read-only access. Context-manager/destructor methods are lifecycle implementation, not additional science operations.

## Compatibility and unsupported features

Legacy `fimrun.Case`/Material/Mesh/Field/Initial/Dynamics/Preparation/Drive/PreparedState/Runtime/Budget/Output/Preview remain in fimrun/api.py. They are compatibility objects with old units/defaults; use [migration](interface-v01/MIGRATION.md), not this new SI interface to infer their semantics. FM minimization/DMI/SOT, multilayer/3D, spatial callbacks, thermal/STT, transport, arbitrary time functions and multiple tracked skyrmions remain unsupported. Explicit params/defaults never certify physical convergence.

## Public orchestration function semantics

| Function | Parameters / return / error contract |
|---|---|
| read_segments(directory) | Existing core segmented output directory; validates segments.json identity and file hashes, returns run_id/parent/rows/events. Does not advance a simulation or join unverified lineages. Bad schema/hash/run identity raises ValueError; missing/invalid IO retains its exception. Flat Notebook state pairing uses the separate postprocess contract. |
| check_stages(sim, stages) | Existing configured Simulation and explicit tuple/list of inert stage descriptors; returns valid/managed_fields=0/managed_Model_calls=0 plus normalized save targets and plan. Validates duration, model support and ownership before execution; may load native dependencies through check, but does not evaluate a model. Unsupported/overlapping targets raise TypeError/ValueError/FileExistsError as applicable. |
| run_script(*, model, initial, solver, outputs=None, stages, argv=None) | Explicit model/initial/RK4, optional Outputs, required stages, optional CLI argument list (None uses process argv). --check prints preflight and returns0; execution returns0 when completed/converged or130 for cancelled/incomplete results. Real validation, IO and numeric failures propagate. Execution performs scientific operations; this is not a zero-field display helper. |
| run_directory(parent, name) | Parent path and one nonempty name component; returns a timestamp/uuid-suffixed Path without creating it. Invalid component raises ValueError. A new name does not itself reserve/create a directory. |

Each single SVG includes immutable run/stage/segment/selection facts, sampling/window/calibration, phase convention and valid counts/short reasons. Unknown facts are explicitly unknown. Helicity remains each sublattice's own reference; relative phase uses B-pi only when the recorded antiparallel declaration and existing validity gates permit it. Standalone exported SVG needs no adjacent Notebook table for these definitions.

## Notebook API1.4 output and energy contract

Use `NotebookSimulation(model=model, initial=initial, output_dir=...)`; no dynamic dt exists until `run(name=..., dt=..., duration=...)`. `relax(name=..., mxh=..., residual=..., save_step=...)` has no fixed iteration limit. New sessions default to seven existing scalar kinds and A/B OVF, with initial viewer. Passing the legacy constructor dt retains old defaults, explicit selections and frequencies unchanged. See [sampling, aliases, seven energy columns and compatibility](interface-v01/NOTEBOOK_OUTPUTS.md).


## 进度与报告修订

见 [进度、同名sim安全恢复及真实结果分析](interface-v01/PROGRESS_AND_REPORTS.md)。`sim.restore(path, output_dir=..., backup=...)`在验证目标并保存当前接受态后安全交接；失败保留旧对象。`Analysis.plot`新增`trajectory=False`与`corrected=False`显示选项，默认保留原始角度；center默认分段位移。`Analysis.table(limit=...)`可限制预览行数，完整CSV不裁剪。
