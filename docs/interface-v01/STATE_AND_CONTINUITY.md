# State, checkpoint and segment contract

## Restore levels

| Operation | Restores | Does not promise |
|---|---|---|
| OVF import/export | Labelled FM single direction field, or independent FiM A/B; exact grid/units | No clock, material, excitation, D/P, equilibrium or solver history |
| save_state/load_state | Registered model/terms/material/units/convention, grid, m, physical clock, D/P, energy origin/switch changes, current, completed segment protocol/events, output sampling settings, portable qualified kernel bytes/provenance when constructed | No Python stack/closure/next line, no preservation of BB private history, no cross-version numerical identity |
| save_checkpoint/resume_checkpoint | Above plus native/Python/runtime fingerprint and required solver private history; SDesc prev/gradient/controls/consecutive count, stop criterion and accepted-residual check position | No parameter changes, cross-platform or cross-version bitwise guarantee |

State archives use schema `micromagnetics-state-v1`, manifest checksum and per-array/payload checksums; little-endian f64 npy, allow_pickle=False. No arbitrary object deserialization. Writes use a temporary file, flush/fsync and atomic replacement. Failed writes retain the previous valid file. Unknown schema, missing arrays, damaged binding, model/label mismatch, unqualified kernels or wrong strict fingerprint fail explicitly. No automatic downgrade from checkpoint to fresh. A physical state can deliberately be loaded from a strict checkpoint via load_state; this is an explicit lower-grade operation.

Native libraries and installed program/dependencies must be available on the qualified macOS CPU platform. State loads check the actual shared-library loadability. Kernel content and qualification are embedded, not merely an old absolute path: the raw qualified tensor, generator/equation/binary provenance and native representation are checked before use. FM's OPENv2 representation must equal conversion of that raw tensor. FFT plans/spectra and current fields are reconstructed. A state saved before demag initialization has no constructed kernel; its explicit grid/model source is enough to generate and independently verify the existing tensor on first use. This is reconstruction, not a hidden scientific trajectory or an accuracy/convergence certificate.

When saved output files were enabled, a load with no output override selects a **new** unique `restored-<UUID>` directory beside the loaded state, retaining its sampling configuration; no directory is created until execution. It never reopens/overwrites the original directory. Passing Outputs(...) explicitly selects a destination or disables files. Stored completed segments remain in restore provenance; the Python execution stack is not resumed automatically.

## Qualified strict combinations in this local release

| Model / algorithm | Guarantee demonstrated by finite developer cases |
|---|---|
| FM / fixed RK4 | Whole vs split checkpoint directions, D/P and physical time exactly equal on same build/platform |
| FiM / fixed RK4, no current | Same, independent noncollinear A/B |
| FiM / fixed RK4, explicit constant SOT | Same including accumulated drive work |
| FiM / SDesc BB | Nontrivial interrupted static trajectory vs uninterrupted final m, gradient and all BB controls exactly equal |
| FM static, adaptive solvers, thermal/GPU | Unsupported; explicit error, no claim |

Tests are bounded evidence, not universal arbitrary-material stability or continuum accuracy. Current strict identity conservatively includes native libraries, equation/binding files, Python implementation, architecture/OS/byte order and NumPy version; a mismatch fails. No existing historical CP is reinterpreted as this new archive. Native legacy CP+sidecar formats remain readable only through their original tools, under their original compatibility checks.

RK4 is one-step: no k1-k4 or nonexistent FSAL state is required at completed boundaries. SDesc history genuinely is required, is preserved only for strict saves, and is rebuilt on ordinary state loading. Strict objects reject field/current/solver changes; create an ordinary branch when changing the experiment.

## Clocks, parameter switches and branches

run(duration=...) adds an integer number of dt steps to physical time and inherits accepted m and applicable D/P. set_solver(RK4(dt=...)) is an explicit ordinary boundary operation, records the change and resets invalid BB history; it never changes time. No arbitrary final short step or rounding. Static iterations/auxiliary step scale are not physical time and do not add dynamical dissipation.

set_field evaluates E_old(m) and E_new(m) at identical m; the event records DeltaE_switch. Static relaxation records DeltaE_static separately. The applicable diagnostic is `E-E_origin+D-P-sum(parameter/static energy changes)`, not an unadjusted constant-model balance across a jump. Current switches do not add conservative energy; their subsequent work uses existing FiM power integration. Static energy changes commit once even if observation or report writing fails.

branch(name=..., clock='inherit'|'zero', model=..., outputs=...) copies independent m and creates a new experiment ID/parent record; parent is not modified. An unchanged model with inherited clock inherits D/P/baseline. A zero clock or changed material/terms starts new cumulative/baseline accounting explicitly; inherited physical time can be kept. Same grid/model kind required; no automatic remeshing/boundary/model conversion. Current is inherited because it is an explicit experimental setting; zero clock is a new experiment convention, not just relabelling plots.

## Segments and results

Every operation has its own segment ID/index, current/model summary, physical start/end and completed/converged/cancelled/failed status. Output directories use fresh `segment-00000` etc, with `segments.json` parent/protocol/events. No old CSV or frame append. read_segments(directory) returns samples with segment/boundary identity plus all parameter events; duplicate boundary times are retained. Gaps/overlaps are marked rather than silently repaired; no automatic full-history velocity fit is claimed.

execute(stages) stops immediately on cancellation/noncontinuable status. No remaining field/current/method call occurs; explicit subsequent user operations remain possible. Cancellation keeps the last accepted state. Numeric/system/IO errors raise real exceptions after retaining the accepted state/status that can be retained. A result marked completed means only requested physical time was reached; converged means the explicit static stop was met. Equilibrium/structure qualification is never inferred from a successful process exit.

The physical clock also stores an exact rational sum of the supplied binary64 dt values. The displayed float is derived from that clock, so changing to a half step does not introduce accumulation drift; state/checkpoint preserves both representations and verifies agreement. This is time bookkeeping, not a change to native RK4 arithmetic or a precision guarantee for the trajectory.

When a file output root is enabled, each attempted operation saves its last accepted physical state to its own segment/accepted.state as well as status/metadata; turning off snapshot time series does not disable this final recovery record. No files are written for directory=None. Output errors may prevent a new record, but atomic writes retain any prior valid record. set_outputs(Outputs(...)) changes sampling/analysis at an ordinary boundary; an already-created experiment root is immutable, and another root requires a branch.

SDesc consecutive convergence counts distinct accepted states, including the initial state once. An interrupted or failed next update leaves that accepted state marked as already counted. Same-process continuation and strict restore therefore cannot count it again. Strict continuation must use the saved tolerance/consecutive criterion; ordinary changes reset the criterion count/check marker while retaining applicable BB history. The finite consecutive>1 cancel/failure/restart regression compares exact m, prev, gradient, controls and stopping update count.

Size-input provenance is saved separately from the normalized physical model and validated against it on load. Old cells-based physical states still decode; changing between equivalent size/cells spelling does not change model equality, kernel keys or inherited branch D/P baseline. Old-code strict fingerprints continue to reject rather than downgrade. New transient preview packets/history are display data and are not a solver checkpoint or persistent trajectory.

Physical clock, static iterations and energy/work conventions are distinguished in the [mathematical guide](../MATHEMATICS.md); no formula formatting change relaxes strict implementation identities.
