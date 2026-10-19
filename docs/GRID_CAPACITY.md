# XY grid capacity

The sequential API no longer restricts XY axes to 256 or the cell count to
65,536. For example, a 500 × 500 × 3 nm sample with 1 × 1 × 3 nm cells is
500 × 500 × 1. A 1000 × 1000 × 1 geometry also passes arithmetic validation;
constructing a model additionally requires enough available memory.

The previous constants first appeared in the parameterized single-layer
workflow, commit `c16efa07f8b34388bcdbed017daf4921c17381e1` (2026-10-16), and
were carried into the sequential interface at `cd989c9`. The retained parameter
documentation calls them implementation support domains, not physics laws.
Neither that commit nor the reviewed plan states a mathematical FFT limit of
256 or derives that number from a measured resource budget. This history does
not establish the author's original motivation more precisely.

## Checks

- Counts must be positive integers and `size/cell_size` must be an integer to
  floating-point roundoff. `Nz=1` remains required by the physical implementation.
- Before native multiplication, wide arithmetic checks cell products, real and
  complex FFT products, and the largest mirror/wrapped displacement against the
  signed 32-bit indices actually used by the backend. FM additionally checks its
  power-of-two Accelerate padding and open-kernel coefficient indexing.
- Allocation preflight estimates working arrays and compares with a snapshot of
  free plus inactive Darwin pages. `FIMRUN_MEMORY_BUDGET_BYTES`, when set to a
  positive integer, can lower this budget. It cannot override native index
  capacity or raise the detected available-memory amount.
- The estimate reserves 32 vector-array slots for integration/static/native and
  state copies, plus kernel/FFT arrays. It is a conservative working-array
  estimate, not a rigorous process RSS bound or memory reservation. Other apps
  can consume memory after a check. Allocation failures still report normally.
- Kernel generation checks temporary disk capacity. Existing per-job resource
  controls in the legacy workflow remain effective.

Physical discretization, FFT, tensor equations, MPFR precision, tensor summation
order, field addition order, and numerical acceptance gates are unchanged.
The current FiM script binding uses Neumaier compensation for scalar local-energy
reductions: at 500², naive repeated onsite-energy addition exceeded the existing
independent energy gate. This changes scalar rounding, not any physical term or
field/RHS. The historical CLI reductions retain their previous arithmetic. The old kernel-generator map
stored unique displacements without reuse; it is removed. Periodic generation
still evaluates `Nx*Ny*(2*Mx+1)*(2*My+1)` tensors, so a finer grid increases CPU
work even though retained builder arrays grow only with FFT size.

## Scope and compatibility

Single-layer geometry, open/complete XY periodic boundaries, the existing cell
aspect-ratio qualification domain, and finite-mirror support remain unchanged.
More cells do not establish spatial convergence or timestep stability.

Kernel keys include generator provenance and binary identity. New noncanonical
kernels use a new key; old caches are not silently relabeled. Physical-state
restoration recognizes the pinned previous generator source only when tensor
equation hashes still agree and the existing checksum and qualification checks
pass. Strict checkpoints continue to require the same implementation and native
binaries. No automatic cross-grid interpolation is introduced.

OVF and state shapes remain explicit. OVF parsing uses a memory preflight rather
than the old fixed64MiB rejection; state restoration checks uncompressed payload
size plus model capacity before reading array entries. Live preview has separate display limits:
16 MiB per raw packet, 65,536 pixels per sublattice in 2D, and 20,000 arrows per
sublattice in 3D. A 500² FiM raw packet fits; use stride 4 or coarser for 3D.
The 2D heatmap limit is unchanged. Display rejection does not invalidate a
completed simulation. Larger raw packets may have preview unavailable while
science and file output continue.

Local release0.2.0rc2 is installed into the existing micromagnetics environment.
Use a fresh Python process/kernel to activate the update. Existing user kernels,
notebooks and simulation data are left unchanged; do not hot-reload an active
Simulation. Strict checkpoints remain implementation-specific.
