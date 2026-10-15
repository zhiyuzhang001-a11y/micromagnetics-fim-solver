# Interpreting numerical output

An exit code zero means a constrained CLI finished its own control path.
It is not scientific acceptance. Retain the status, complete input identity,
step/time semantics, actual final state and both sublattice residuals.

For static results, report each final maximum projected H in A/m. Scaling both
by 600000, as in the old combined diagnostic, is not a both-sublattice 1 A/m gate.
Own-Ms relative values are diagnostics. The tentative engineering target is
max(r_A,r_B)≤1 A/m; a persistence rule has not been frozen. A first crossing does
not prove sustained convergence. The older scientific condition required both
≤0.6 A/m and |stable_delta_E|/energy_scale≤1e-8 for 20 consecutive updates;
that condition was not met in the historical main static runs.

Check finite/unit state, field identity, energy bookkeeping, stage refresh,
raw norm and endpoint correction, actual restoration and observer definitions.
Independent field agreement at one state does not bound time integration,
mesh discretization, finite mirrors or model error. Dynamic runs use physical
observation/time convergence; static residual thresholds are not dynamic stops.

A synthetic uniform fixture is deliberately inexpensive and cannot validate a
nonuniform skyrmion. The smooth fixture exercises nonzero fields/energies and
short restoration, but is also only a packaging compatibility check.
The package's native snapshot format has no embedded endianness or full config
signature. Preserve external hashes and metadata; mismatched inputs must not be
silently interpreted as a valid continuation.

External `external_acceptance_passed` requires field agreement AND history agreement AND both final residuals≤1 A/m. The CLI returns 1 for NOT_ACCEPTED, including inconsistent fields/history. ACCEPTED_ONCE is only this limited one-state engineering check, never sustained scientific convergence. A normal native stop can remain NOT_ACCEPTED.
