# Micromagnetics: simulation and offline measurements

Independent, unofficial BORIS-referenced FM/FiM research code. GPL-3.0-only; see [NOTICE](NOTICE), [COPYING](COPYING) and [source/license map](docs/interface-v01/PACKAGE_SOURCE_MAP.md). This source candidate adds offline result presentation and documentation; it has not replaced the accepted installed package or Recovery archives.

Use the dedicated Python/micromagnetics environment. Do not modify `sys.path`, hot-reload a running simulation, or install packages inside a tutorial. [Installation](docs/INSTALL.md) and [offline recovery](RECOVERY.md) retain their separate procedures.

| Start here | Purpose |
|---|---|
| [Simulation Notebook](examples/notebook_single_sim.ipynb) | One simulation; inspect, optionally relax, add a current and evolve, then save |
| [Offline postprocessing Notebook](examples/notebook_skyrmion_postprocess.ipynb) | A runnable five-frame analytic example; analyze, show, select a plot, export |
| [Mathematics and units](docs/MATHEMATICS.md) | LaTeX definitions with code/parameter/result-column correspondence |
| [API reference](docs/API_REFERENCE.md) | Classes, inherited methods, defaults, choices and limits |

```python
import fimrun.postprocess as pp
result = pp.analyze(explicit_frames)
result.show()
```

`explicit_frames` is an explicit list of A/B file declarations. A state path is accepted only when the complete inventory can be independently bound to its last segment; historical/mixed/ambiguous states are rejected. No time, PBC, Ms or antiparallel reference is guessed. Invalid quantities remain NaN with reasons; static iterations are not physical time or velocity. Analysis writes nothing until an explicit export.

macOS 27 arm64 is the qualified installed platform. Current support is single-layer: FM exchange/K1/Zeeman/open demag and dynamics; FiM has independent A/B, supported local terms, finite-image demag, static and constant effective SOT. No FM minimization/DMI/SOT, thermal/STT/transport, multi-object tracking or arbitrary time callbacks. Calibration is an empirical domain, not a universal error guarantee.

[Parameters](docs/interface-v01/PARAMETERS.md), [output/repetition](docs/interface-v01/NOTEBOOK_OUTPUTS.md), [state continuity](docs/interface-v01/STATE_AND_CONTINUITY.md), [postprocessing source contract](docs/interface-v01/SKYRMION_POSTPROCESSING.md). Historical fixed-case results and failures remain in [numerical interpretation](docs/NUMERICAL_GUIDE.md), [validation](docs/VALIDATION.md), [known failures](docs/KNOWN_FAILURES.md), [representative workflow](docs/REPRESENTATIVE_WORKFLOW.md), [current SOT](docs/CURRENT_SOT_WORKFLOW.md) and [mirror limits](docs/MIRROR_TRUNCATION.md). They do not qualify arbitrary user cases.

Developer candidate checks are offline and separate from installation. See [candidate validation](docs/CANDIDATE_VALIDATION.md). New VS Code/GitHub rendering and installed-delivery qualification must be recorded separately; no historical screenshot or MIME test implies a new visual PASS.

## Current sequential interface and verification

The reviewed363ba83 interaction fixes include same-process idle preview handoff/retry, default equal-scale Δx–Δy center trajectories, and focused Enter/Esc overwrite confirmation with press/release protection. Ordinary state restore and per-stage outputs retain their documented contracts.

GitHub-hosted verification and its explicit coverage limits are documented in [docs/CI.md](docs/CI.md). No self-hosted runner, workstation data or recovery environment is required.
