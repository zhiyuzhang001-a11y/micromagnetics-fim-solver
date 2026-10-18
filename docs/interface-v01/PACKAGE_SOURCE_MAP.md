# Installed source and license map

The seven private `_support` modules preserve the corresponding tools bodies, with package-relative imports and resource roots. tools retains thin compatibility entry points. `fimrun.postprocess.demo` contains the former examples generator. Physics implementation remains in src and validation/fm, copied byte-for-byte into `_runtime` with GPL-3.0-only, COPYING, NOTICE and LICENSES. Native builds use C++17/O2, C1/two-owner CPU and serial FFTW. No fast-math.

Viewer assets and LICENSE.three retain their original MIT attribution. Calibration JSON and canonical tensor remain byte-for-byte frozen. Conda supplies FFTW/MPFR/GMP and runtime dependencies; their exact archives, metadata and licenses belong to the Recovery release, not the wheel. Apple frameworks remain OS prerequisites. Source/actual payload hashes and build commands are included in the platform wheel. See RECOVERY.md and the release acceptance receipts for qualification limits.
