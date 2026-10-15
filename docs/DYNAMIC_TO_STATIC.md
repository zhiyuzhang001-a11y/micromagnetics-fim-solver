# Dynamic to static handoff

`fim_dynamic INPUT KERNEL NEW_OUTPUT DT_FS RESTORE START_PS END_PS E_ORIGINAL_J LOSS_BEFORE_J`

DT_FS must be exactly 12.5, 25, 100, 200 or 500. CLI acceptance is not an accuracy
endorsement. The main permits at most 100 ps per segment and global end 500 ps,
with existing native 60 s / 2 GiB guards. Output directories must be new.
The RK4 stages use refreshed full fields, no intermediate projection, followed
by endpoint projection and a fifth field. It records physical time and RK loss.

For a new synthetic seed, run `tools/make_fixture.py NEW_FIXTURE`, then
`fim_inspect CONFIG KERNEL NEW_INSPECTION`. Read `initial_energy.json:total_J`
and use that exact value for E_ORIGINAL_J. Initial LOSS_BEFORE_J is zero because
no integration preceded the new seed. For every continuation, pass the preceding
`final.bin`, its reached time, the original E, and its cumulative RK loss.
Do not restart accumulated loss at a segment boundary. `tests/smoke.py` provides
an executable bounded example and checks split versus continuous state/loss.

`fim_static CONFIG KERNEL SEED OUT MODE RESTORE_OR_DASH NATIVE_BUDGET_S`

MODE is `run`, `test`, `unit` or the restricted `resume_test`. For a fresh
minimization use dynamic `final.bin` as SEED, mode run and restore `-`.
The seed bytes are unit directions in the same A/B order and grid; the config
must retain the canonical material/geometry. No swap, normalization, translation
or private OVF substitution occurs in this transfer. Check static `initial.bin`
against dynamic `final.bin`, and corresponding seven energies/fields.

Static `aux_s` is optimizer step-size accumulation, not physical LLG time.
The static source does not store the prior physical-time provenance in its
checkpoint. Preserve the dynamic summary/hash separately in a workflow manifest.
Static restart uses its own `checkpoint.bin`, including prev/Gprev, updates,
reset count, step size and auxiliary time; a dynamic state is a fresh prime,
not restoration of nonexistent BB history. `resume_test` is a restricted test
that reads sibling final_H_A/B; it is not a general continuation driver.

SDesc keeps 1 fs initial/minimum and 1 ns maximum auxiliary steps, a 10000-update
cap and existing stagnation exits. Its internal successful schedule exit samples
A's pre-update residual/Ms_A≤5e-5, then saves the post-update state. It does not
require B or the final state to satisfy any external threshold.

After a completed static run:

```sh
python3 tools/check_residual.py OUTPUT examples/kernel125-mirror10.f64 CONFIG
```

This recomputes the full field independently with NumPy, reports A/B max
|H-(m·H)m| in A/m and cross-product diagnostics, compares saved H and final
history residuals, and reports the tentative joint≤1 A/m single-observation flag.
The wrapper does not automatically continue a failed joint test, alter internal
stopping, or claim sustained convergence. Read `field_consistent_1e_minus10`
and `history_consistent_1e_minus6_Apm` before interpreting the threshold flag.
The field expression was reused from an existing independent calculation;
the newly packaged reader itself has only the bounded packaging checks here.
No previously reviewed general-purpose external acceptance wrapper was found.

External `external_acceptance_passed` requires field agreement AND history agreement AND both final residuals≤1 A/m. The CLI returns 1 for NOT_ACCEPTED, including inconsistent fields/history. ACCEPTED_ONCE is only this limited one-state engineering check, never sustained scientific convergence. A normal native stop can remain NOT_ACCEPTED.
