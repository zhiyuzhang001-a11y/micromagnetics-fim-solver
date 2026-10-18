# Micromagnetics FiM solver

Independent, unofficial BORIS-referenced research code, GPL-3.0-only. This repository includes the sequential SI Python API, Notebook outputs, offline skyrmion measurements, CPU native sources and explicit packaging/recovery tools. It is not an official BORIS release. See [NOTICE](NOTICE), [licenses](LICENSES), [citation](CITATION.cff) and [source map](docs/FILE_LICENSE_MAP.json).

**Qualified installation scope: macOS 27 arm64, Python 3.12.14, NumPy 2.3.5.** Other OS/architectures and unknown future systems need separate qualification. Source publication does not include an installable binary or a complete offline Recovery bundle. Rebuilding native code creates a new binary identity that must be validated; it does not inherit strict-checkpoint compatibility.

## Start here

1. [Build and noneditable install](docs/INSTALL.md): dedicated Conda environment, exact same-platform dependency lock and explicit native build.
2. [Python and Notebook use](docs/START.md): the same public imports and SI parameters, new output directories, correct kernel selection.
3. [Offline recovery](RECOVERY.md): complete local archive requirements, existing-manager branch and system-shell bootstrap branch without external Python.
4. [Acceptance scope](docs/ACCEPTANCE_SUMMARY.md): what was independently checked and which GUI checks remain unverified.

Public interfaces are `fimrun.micromagnetics`, `fimrun.notebook`, and `fimrun.postprocess`. Imports do not install dependencies, compile code, generate a kernel, or start a simulation. The package owns immutable resources; writable caches live outside site-packages. Historical Case workflows remain a separate compatibility path and are not certified as installed workflows.

The adopted CPU backend remains C1 plus one persistent helper for local fields; FFTW is serial. RK4 remains the formal integrator. No DP54, demagnetizing-field extrapolation, GPU or new current model is enabled by this publication. A bounded 2 ps DP54 candidate had no performance benefit; this is not a claim that all adaptive methods are unhelpful.

The existing 750,000-byte canonical mathematical tensor is retained as an explicit runtime resource. Raw user OVF/state files, local study outputs, development histories, environments, native binaries, installation archives and caches are not published. Earlier validation documents remain historical records with their original scientific scope; current installation/use instructions are the links above.
