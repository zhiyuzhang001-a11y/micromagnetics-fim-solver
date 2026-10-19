# Legacy Case compatibility and daily migration

The old Case, Mesh (nm/fs/ps), Material, Field, Initial, Preparation and Drive retain their original behavior. Call `fimrun.describe_legacy(case)` to view defaults and actual expansion without fields. The preserved template is examples/script_api/legacy_case.py; its placeholder runtime paths still need setup. No old result, checkpoint, budget or scientific gate is rewritten.

| Legacy | New sequential API |
|---|---|
| Case workflow='relax' | Explicit FiM sim.relax(method='sdesc', stop=...) only; no hidden dynamic T=0 initializer |
| prepare_then_drive | sim.run(preparation duration); sim.relax(...); sim.set_solver(...); sim.set_current(...); sim.run(drive duration), each optional |
| drive requires PreparedState | Any legal explicit state can run; optional research qualification is a separate explicit analysis/check |
| Material implicit historical defaults | FMMaterial or explicit A/B Sublattice required |
| Mesh n/cell_nm | Grid cells/cell_size [m]; origin [m], named boundary/mirrors |
| dynamics dt_fs/T_ps | RK4 dt and run duration [s]; sampling separately named |
| Field omitted = -2mT | No Zeeman term means zero external field |
| Drive omitted has nonzero sample J | No FiMSOT means no current/torque |
| active=(exchange,onsite,dmi,anisotropy) | Explicit typed energy sequence, exact existing coefficient conventions; A and Anh stay grouped in FiMExchange |
| demag unconditionally runs | Explicit Demag() only; omission skips its model/FFT/kernel work |
| goal='none' still analyzes | Outputs.analysis=() means no topology/center/contours; analyze('structure') is explicit |
| fresh drive resets time/D/P | Ordinary sequential run inherits clock/D/P; parameter/static energy events separate jumps; explicit branch(clock='zero') is a new experiment |
| legacy native CP+sidecar | Original tools under original rules; not silently loaded as a new portable state/checkpoint |
| F/W/R/O and max_updates | Not migrated to daily interface or hidden defaults; retained in historical scripts and developer protocols only |

Desktop migration preserves the actual material/mesh/field/initial/dt/duration/current values from the read script, with explicit SI conversion. It preserves that file's old source as an immutable local backup, rather than replacing it with a generic example. Former default structure goal is not silently copied: new analysis is opt-in. Old legacy 30000-update/F/W/R/O values are intentionally not inherited. Existing Chinese result directory and all old outputs remain untouched; future results continue under the explicit English results parent. Automatic preview now reuses the task-4 3D arrows and solver-status interface, with a new explicitly versioned memory source adapter; the original legacy source mode still reads historical run.json artifacts.

The desktop check validates/configures and describes only; the Run shortcut executes the actual desktop script. Every run uses a unique result root. No science runs automatically during installation or check. Editing or removing a sequential call changes the experiment; no workflow string silently restores a removed phase.

Size/viewer revision preserves the actual effective model and all initial/material/field/current/dt/duration values. Desktop backup: task-2/size-viewer-revision/desktop.before.py (SHA690e542b...). The new sample uses size500x500x3nm with4x4x3nm cells, explicit stage descriptors and run_script; only CLI/plumbing and a prepared-state save move/change. No old result or launcher is overwritten; new results remain unique. Shared viewer modifications are reviewable as integration/task4/unified-viewer.patch with original app/identity backups and exact before/after bindings.
