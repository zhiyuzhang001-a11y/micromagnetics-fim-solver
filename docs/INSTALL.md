# Installation and build limits

Verified packaging host: macOS arm64, Apple clang 21, Python 3.13.5,
NumPy 2.2.6, FFTW 3.3.10, MPFR 4.2.2 and GMP 6.3.0.
Select a Python environment in which `python3 -c "import numpy"` succeeds. The system Python on the packaging host lacked NumPy; the successful check used the existing NumPy environment.
Dependencies must be installed externally. No installer or download is run by the build helper.

`python3 tools/build.py --out build` discovers CXX or clang++/c++ and uses
pkg-config for FFTW. Flags: C++17, -O2, -pthread and LF_TWO_OWNER for the three core CLIs; no fast-math or explicit FFT threading. The default is the adopted two-owner local-field backend. `--serial-local --out build-serial` builds the C1 serial rollback explicitly. No runtime automatic switching occurs.
`--validation` also builds the restricted label and D0 targets; on macOS it
builds the separate Accelerate FM target. The builder has a cumulative timeout;
`--cap 60` bounds the build to 60 seconds. It writes compiler diagnostics to the
chosen output directory. Do not publish these host-dependent logs blindly.

Optional CMake: `cmake -S . -B build-cmake`, then `cmake --build build-cmake`.
CMake defaults `FIM_LOCAL_TWO_OWNER=ON` and links `Threads::Threads`; use `-DFIM_LOCAL_TWO_OWNER=OFF` for the serial C1 rollback.
Set `-DBUILD_VALIDATION_TARGETS=ON` to include separate targets. CMake was not
installed on the packaging host, so this path has not been executed here.
The Python builder is the verified route.

Linux and Windows builds are unverified. The FM target requires Apple frameworks.
The D0 reference retains its original macOS RSS accounting assumption; do not
claim Linux resource-guard equivalence. Binary data uses native-endian binary64,
not a portable archival serialization; tested host is little-endian arm64.
