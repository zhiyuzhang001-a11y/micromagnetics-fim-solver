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
The chosen package does not include unused BORIS/OOMMF asymptotic source,
OOMMF scalar extracts, upstream repositories, original Git history, personal
OVFs/scripts, PDFs, trajectory dumps or private project-control records.

The generated tensor dataset has SHA256
`db71f379e2bea728a475d9e0c6e5e1183c7830ee1ba91e6909f84c532ec012b6`.
Layout: 125×125×6 native-endian doubles, components xx yy zz xy xz yz,
dimensionless tensor N with H=-N*Mbar convolution, x fastest.
The file is numerical data, not a compiled executable. Kernel generation is
historical evidence, not a public rerunnable target in this release.
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
