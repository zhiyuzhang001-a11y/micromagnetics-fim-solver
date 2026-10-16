# Adopted CPU backend and delivery limits

The supported Python and CMake builds default to **C1 plus two-owner local fields**.
C1 omits diagnostic module-field arrays that the combined evaluator never reads.
Main computes H_A and every energy/Ecross reduction in the reference order. One
persistent `std::thread` computes H_B, reading the same immutable coupled A/B
magnetization. No cell scatter is shared between writers. Worker work is drained
on a main exception, worker exceptions are returned, and destruction joins the
helper. This preserves the two-sublattice coupling; it does not split the physics.

FFTW uses the existing serial ESTIMATE plans and cached kernel spectra. No FFTW
thread initialization, nested pool, GPU, fast-math, reduced precision, C3 reuse,
adaptive integration or approximate field is enabled. RK4 still uses five full
fields per step. Legacy static scheduling stays legacy; the portable representative
workflow explicitly selects the current both-sublattice 1 A/m policy.

## Build, reproduce, and roll back

```sh
python3 tools/build.py --out build
python3 tools/run_representative.py --bins build --output output/representative --dry-run
# Full 500 ps + static computation; run only when that scope is intended:
python3 tools/run_representative.py --bins build --output output/representative

# Explicit C1 serial local-field rollback, with a separate output/build directory:
python3 tools/build.py --serial-local --out build-serial
python3 tools/run_representative.py --bins build-serial --output output/serial --dry-run
```

No historical host path or precompiled native binary is required. Python 3/NumPy,
C++17, pkg-config and FFTW must be provided externally. Normal build flags include
`-O2 -pthread -DLF_TWO_OWNER`; the rollback omits only the backend definition.
CMake defaults `FIM_LOCAL_TWO_OWNER=ON`; `OFF` chooses serial C1. CMake was not
installed on the packaging host and that route is not claimed executed. See
[installation](INSTALL.md). Linux/Windows and generic installations remain unverified.

Keep new output directories. The fixed workflow retains original energy and
cumulative loss across five real dynamic-file seams, then starts a fresh BB
history from the actual 500 ps state. Checkpoint continuation is different from
using a direction seed. Native static candidate status alone is not accepted:
the normal wrapper requires actual saved/reloaded state, policy identity and an
independent field check. Neither build mode changes that contract.

## Evidence and minimal packaging checks

The model and thread implementation are taken from the already qualified local
backend. `model.hpp` is identical to that adopted source; the thread header changes
only its public-facing introductory comment. Dynamic, static, Gilbert, grid,
FFT and stopping-policy expressions are unchanged from the public base.

Archived B1/C1/C2/B2 original-seed runs used 100 fs to 500 ps, then 13,380 static
updates to first jointly meet 1 A/m. Independent final A/B residuals were
0.993908981643/0.993694428004 A/m. The saved-result review compared 1,272 scientific
files and 153 source/binary/input bindings. Whole outer times were respectively
48.630894, 44.779432, 44.762753 and 49.070129 seconds; min(B)/max(C)=1.086010.
These are the archived same-source fixed-case measurements, not a new benchmark,
confidence bound or a performance promise for a new build or another host.

The publishable [summary](../results/cpu-acceleration-summary.json) deliberately
omits private audit paths, raw trajectories and native binaries. Full same-version
regression is reused, rather than rerun to create a new timing claim.

```sh
# Zero-field build selection and policy checks:
python3 tests/build_backend.py
python3 tests/static_stop_policy.py --static-binary build/fim_static

# Optional numerical packaging test: fixed smooth synthetic input, six processes,
# 28 full fields total; two RK4 steps and one static update per backend:
python3 tests/cpu_backend.py --serial-bins build-serial --two-owner-bins build --work output/cpu-backend
```

The last test compares actual saved fields, directions, history and checkpoint
bytes between serial and two-owner builds. The one-step static branch is expected
to end with `step_budget` / `not_success`; it is not a relaxation qualification.
It does not call an independent field provider or the full representative flow.
Preserve a failed test directory; the test never overwrites or retries it.
Current executed checks and explicit skips are listed in `CPU_PACKAGING_CHECKS.json`.
The archived two-step TSan and local exception/drain tests are limited evidence,
not proof that every future call is race-free or that long-term memory is bounded.

## Rejected candidates and scientific limits

Only sanitized dispositions are shipped for C2 buffer reuse, C3 accepted-endpoint
reuse, FFTW2, DP54 and quartic demag extrapolation. Their code and enable switches
are absent from the core delivery. In particular, a candidate's short-window
science pass does not imply complete restore, tightened-tolerance or long-window
qualification. The demag screen reduced convolutions but its roughly one-second
timing intervals overlapped; no reliable gain was established. Separate prediction
and guard timers were not collected, so no quantitative cause is assigned.
See [research and dispositions](NON_GPU_ACCELERATION_RESEARCH.md).

The requested current static criterion is a single saved-state maximum projected
field for both sublattices. It is not the historical failed 0.6 A/m + energy +
20-accept contract. It does not certify an energy minimum, mesh/mirror convergence,
real material accuracy, agreement with an unknown BORIS installation, or driven
motion. GPU/current/torque work remains outside this delivery.

## Sources and licensing

This is independent unofficial GPL-3.0-only research code. Retain [NOTICE](../NOTICE),
[COPYING](../COPYING), the [file license map](FILE_LICENSE_MAP.json), and external
license notices. BORIS conventions are pinned to v3.80 commit
`6f55516f46f5b6b6ed92bb030d62abab87b4a2f0`; the rational SD/BB adaptation keeps its
upstream attribution. The CPU ownership implementation is project-authored.
References, including the BORIS paper and the demag-extrapolation paper, are in
[REFERENCES.bib](REFERENCES.bib). The extrapolation citation acknowledges research;
it does not claim that approximate method is adopted here.

The release whitelist contains project source, portable public fixtures/configs,
small sanitized summaries, tests and documentation. No private OVF, manual PDF,
chat, credential, personal filesystem path, dependency library, binary build,
cache or large trajectory archive is part of the commit. Local staging does not
mean that the public remote has already changed.
