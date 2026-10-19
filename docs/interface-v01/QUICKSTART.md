# Sequential Python micromagnetics

Use the desktop `微磁模拟/my_case.py` for daily work after migration. New code imports `fimrun.micromagnetics`; legacy `fimrun.Case` remains separate. New inputs use SI: m, s, A/m, J. B_ext is T. No default material, legacy -2mT field, nonzero current, initial texture, static/preparation phase, topology analysis or experiment-derived budget is inserted.

Build native bindings once with the installed Python/compiler/libraries:

```sh
/path/to/project/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 tools/build_script_api.py
```

This release is macOS CPU only, using the existing Accelerate FM and FFTW/two-owner FiM operators. No dependency installer or background build is invoked by a user calculation.

```python
from fimrun.micromagnetics import (
    Grid, FM, FMMaterial, Exchange, Uniform, Simulation, RK4, Outputs,
)

model = FM(
    mesh=Grid(size=(16e-9, 12e-9, 3e-9), cell_size=(4e-9, 4e-9, 3e-9)),
    material=FMMaterial(Ms=8e5, alpha=.02, gamma_H=221088.4),
    energy=(Exchange(A=13e-12),),
)

with Simulation(
    model=model,
    initial=Uniform((1., .05, .05), normalize=True),
    solver=RK4(dt=1e-15),
    outputs=Outputs(),
) as sim:
    print(sim.check())
    result = sim.run(duration=2e-15)
    if result.status != 'completed':
        raise SystemExit(130)
    sim.set_field(B_ext=(0., 0., 2e-3))
    result = sim.run(duration=2e-15)
    if result.status != 'completed':
        raise SystemExit(130)
    sim.save_state('after_field.state')
```

Example values/time windows are interface demonstrations, not calibrated material data or accuracy advice. A legal nonequilibrium state may directly run. Only call relax if desired; FM static is explicitly unsupported, FiM uses named SDesc/BB and explicit MaxTransverseField. A/B inputs are independent unless Antiparallel is explicitly selected. No Ms_B=0 FM shortcut.

Runnable finite examples: `examples/script_api/fm_sequence.py`, `fim_sequence.py`, `state_branch.py`. Use the verified Python with project root on PYTHONPATH. They demonstrate actual one-field demag, independent two-field static/current phases, OVF/state/checkpoint and branch. All have --check that starts no field/model/viewer and makes no output directory. The separate legacy_case.py is an archived compatibility template needing its original paths; it is not a new-interface runnable example.

Consult PARAMETERS.md for every constructor field/default/units, STATE_AND_CONTINUITY.md for state/strict/branch/segments, and MIGRATION.md for legacy differences. Use `parameters()` for IDE-friendly constructor discovery and `sim.describe()` for actual configuration. List only desired energy terms. Outputs.analysis=() and preview=False genuinely skip those operations; no snapshots are saved unless requested. Outputs.scalars=() means no scalar time series. The native field's fused energy/D/P bookkeeping is needed for physical-state and switch accounting and is distinct from optional curves.

No daily field-count, wall-time, update-count, RSS or output-byte caps are inherited from old qualification scripts, in public parameters or behind the scenes. Request a physical duration or a static stop. Ctrl+C returns cancelled with last accepted state; genuine numerical and OS errors are reported, not converted into successful/physical conclusions. Static targets may be unreachable; stop explicitly rather than infer convergence from a resource cutoff. Finite test watchdogs live only in developer tests.

To inspect an already saved physical state without evolving it, load it and call `sim.preview()` explicitly; no native Model/field or topology analysis is started by preview itself. The viewer lives until sim.close()/context exit. The new API and historical runs now use the same task-4 three-dimensional arrow/status interface through separate explicitly versioned source adapters. New preview works without persistent snapshots; bounded memory history is labelled honestly. No standalone2D preview entry remains.

Sequential scripts must inspect each run/relax result before the next operation: require completed for dynamics or converged for static; on cancellation exit130 and keep the retained accepted state. execute(stages) already stops at a noncontinuable result. All three runnable examples and the desktop script follow this rule.

For the compact daily script, use run_script with an explicit ordered stages tuple. The actual desktop sample exposes Evolve → Relax → SaveState(prepared) → SetOutputs/SetSolver/SetCurrent → Evolve → SaveState(final/checkpoint); CLI and cancellation/cleanup live in the library. DAILY_SCRIPT_REFERENCE.md lists editable blocks, exact choices and initial-state replacement examples.
