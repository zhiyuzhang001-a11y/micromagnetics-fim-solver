# BORIS-referenced FiM validation

Independent, unofficial research code for a fixed two-sublattice conservative micromagnetic model. This project is not an official BORIS release and is not endorsed by its developers. It references BORIS v3.80, commit `6f55516f46f5b6b6ed92bb030d62abab87b4a2f0`.

The package contains a shared 125×125 FiM model, constrained RK4 dynamics and SDesc minimization, separate restricted validation sources, a synthetic fixture generator and compact historical results. It does not establish a real CoGd material model, a stable physical texture, compensation behavior or orbital-torque dynamics.

## Quick compatibility example

Requires C++17, pkg-config, FFTW3, Python 3 and NumPy. On macOS, install dependencies through your package manager, then from this directory:

```sh
python3 tools/build.py --out build
python3 tests/smoke.py --bins build --work smoke-output
```

The test creates synthetic states and executes only a few updates. It checks relocation, energy bookkeeping, RK4 restore, dynamic→static transfer, SDesc restore and independent final-field/residual reading. Passing this test does not reproduce the historical validation suite or prove convergence. Run outputs and compiled executables are not distributed.

See [installation](docs/INSTALL.md), [model and units](docs/MODEL_AND_UNITS.md), [dynamic→static workflow](docs/DYNAMIC_TO_STATIC.md), [numerical guidance](docs/NUMERICAL_GUIDE.md), [validation scope](docs/VALIDATION.md), [known failures](docs/KNOWN_FAILURES.md), [mirror limits](docs/MIRROR_TRUNCATION.md), [provenance](docs/PROVENANCE.md) and [non-GPU research](docs/NON_GPU_ACCELERATION_RESEARCH.md).

SDesc's internal stop checks A's pre-update residual only. Always examine both final A/B residuals externally; an internal stop is not joint acceptance. The tentative 1 A/m final-state criterion has no frozen persistence rule in this package.

Source is released under GPL version 3; see [LICENSE](LICENSE), [COPYING](COPYING), [NOTICE](NOTICE) and the [per-file map](docs/FILE_LICENSE_MAP.json). External libraries retain their own licenses. No SDK, external library binary, private OVF or original Git history is bundled.
