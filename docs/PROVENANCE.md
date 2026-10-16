# Provenance and packaging changes

FILE_LICENSE_MAP.json enumerates every public file and its selected license.
PROVENANCE.json maps copied files to original relative scientific paths and
before/after hashes, with explicit modifications. Source originals remain
untouched. Includes were relocated to a canonical model; dynamic/accepted_model
and static/model were byte-identical before canonicalization.
The new build has its own identity and is not the archived binary.

New adapters/scripts/docs are project packaging under GPL-3.0-only. The
independent_field.py function body is retained verbatim from the existing
independent field calculation; only its bindings/input route are relocated.
check_residual.py is a new bounded public reader, not a previously reviewed
universal acceptance driver. It cannot accept arbitrary material/config changes.
The earlier fixed-model package did not include BORIS/OOMMF asymptotic source,
OOMMF scalar extracts, upstream repositories, original Git history, personal
OVFs/scripts, PDFs, trajectory dumps or private project-control records.

The generated tensor dataset has SHA256
`db71f379e2bea728a475d9e0c6e5e1183c7830ee1ba91e6909f84c532ec012b6`.
Layout: 125×125×6 native-endian doubles, components xx yy zz xy xz yz,
dimensionless tensor N with H=-N*Mbar convolution, x fastest.
The file is numerical data, not a compiled executable. The historical canonical dataset is retained. The new user workflow adds a separate
parameterized generator, with explicit engineering-reference coverage.
The source/data selection is intentionally limited; omitted heavy reference
results cannot be recreated merely by running the packaging smoke.

## Current policy/reproducibility release

PROVENANCE.json retains original source hashes and historical public hashes,
while public_sha256 records current copied/extracted file bytes. Its current
release section maps policy, controller, fixture and pure observation additions.
C1 changes diagnostic allocation, not fields; normal run_policy is a new explicit
stopping/verification path and does not rewrite the retained legacy run contract.
The revised current reader has bounded independent verification evidence; it
remains restricted to the canonical model. No full archived-data audit bundle or
new physical-accuracy qualification is implied.

## Adopted CPU delivery

The current release metadata records the adopted two-owner `model.hpp` source and
project-authored `local_field_team.hpp`. The model is byte-identical to the locally
qualified source; the thread header changes only its introductory comment.
Dynamic, static, grid, Gilbert, FFT and stopping-policy expressions are unchanged.
Python/CMake builds default to this backend and expose an explicit serial C1
rollback. Historical origins and the previous release metadata remain recorded.
The sanitized CPU summary and packaging-check record contain no private paths or
raw trajectory archive. No rejected adaptive/approximate candidate implementation
is introduced by the build switches. See CPU_ACCELERATION.md.

## Local parameterized workflow v1

The new user workflow extends uniform single-layer geometry/materials through a
separate versioned entry. Legacy C defaults retain the common axis; the new entry
selects individual A/B axes. Native RK4/SD arithmetic follows the retained scheme;
new independent NumPy edge-energy assembly verifies actual parameterized output.
`src/user_kernel/DemagTFunc_Asympt.{h,cpp}` is the minimal BORIS v3.80 asymptotic
extract, retaining its M. J. Donahue/OOMMF credit. It is used only by the optional
new-geometry kernel builder. `hp.hpp` and `newell_mpfr.hpp` are project-authored
MPFR wrapper/Newell equation implementations adapted from the audited local
reference implementation. MPFR/GMP are external libraries, not redistributed.
`tools/kernel_reference.py` is the project-authored Decimal Newell reference,
retained independently of the MPFR implementation. No upstream full repository,
private OVF, PDF, original trajectory or local control record is included.
The new field tolerances and finite-mirror checks are engineering coverage,
not physical mesh/mirror convergence or a material-model certification.
