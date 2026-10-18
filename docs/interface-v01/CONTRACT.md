# Frozen implementation contract

The accepted v0.1 baseline governs this branch. Units for new operations are SI. Public code and strings are English; Chinese may occur in comments. Legacy Case is retained with its legacy Mesh and sample defaults; the new API uses Grid so an old import of Mesh cannot silently change meaning.

FM uses validation/fm/fm.hpp:31,62: one direction array, full-volume local energy, M=Ms*m, existing open-boundary Accelerate demag, exchange/K1/Zeeman and LLG only. DMI/SOT and FM minimization are rejected in this release. FM's frozen benchmark CLI is not the new entry.

FiM uses src/user_native.cpp:5, src/local_field_team.hpp:14 and src/current_sot.hpp:7: two independent direction arrays, equal_half_volume convention, Mbar=(Ms_A*m_A+Ms_B*m_B)/2. FiMExchange groups A_A/A_B/Anh, OnsiteCoupling controls Ah, DMI controls D_A/D_B, anisotropy uses K1/K2 and separate axes. Open boundaries require Anh=0; periodic XY and finite image counts retain existing discretization. All magnetic Ms are strictly positive. No missing B, implicit inversion, interpolation or spatial functions.

The native field evaluators remain the scientific engines. New bindings bypass benchmark CLI locks without removing or rewriting historical entry gates. Disabled demag must not instantiate its FFT/kernel object. Absent local modules must not enter their contribution branch. Opt-in analysis and preview have independent dispatch. No GPU, thermal, STT, AC, transport, 3D or arbitrary time-dependent callbacks.

Dynamics is fixed RK4 with integer-step duration/sampling. Consecutive operations retain directions, physical clock and applicable D/P. Parameter switches evaluate old/new energy at identical m and record an event; static relaxation does not advance physical time or fabricate dynamical dissipation. Material/energy edits require a branch. Grid/model changes require a new simulation.

Physical state is versioned self-describing data, not pickle; includes model, independent fields, clock, D/P/baseline, protocol position, event provenance and portable kernel content or validated reconstructible dependencies. Strict checkpoints additionally bind the exact engine/kernel/dt/algorithm and required history. RK4 has no cross-step k history; SDesc BB does. Ordinary state load rebuilds solver private history and reports that grade; strict restore never falls back. Checkpoint support is published only for combinations that pass split/whole tests.

Output is per-segment with parent/provenance links; no append/overwrite of previous science. Read/merge retains parameter-switch boundary events. No daily field-count/time/RSS/output caps from previous qualification runs, including hidden defaults. Cancellation and real OS/numerical failures retain last accepted state and return an explicit status. Test watchdogs remain outside production operations.

Source context: ../MODEL_AND_UNITS.md; ../../src/user_native.cpp; ../../src/current_native.cpp; ../../validation/fm/fm.hpp; ../../tools/user_fields.py; ../../tools/ovf.py; ../../fimrun/qualification.py. Full audit: task-2/interface_readonly_review_20261017/FM_STATE_AND_INTERFACE_REVIEW_DRAFT.md.
