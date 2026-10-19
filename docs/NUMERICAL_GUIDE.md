# Interpreting numerical output

> **Historical fixed-tool evidence.** Commands, limits and results below describe the archived entry, not the current installed Notebook API. Start with the [current simulation Notebook](../examples/notebook_single_sim.ipynb), [API reference](API_REFERENCE.md) and [current mathematics](MATHEMATICS.md). Historical values and verdicts are retained.

An exit code zero only means a CLI finished its control path. Read the requested policy, actual saved state, both sublattice residuals, identities and independent verification before interpreting success.

The historical CLI `FIM_POST_PH_MAX_V1` entry compares each sublattice's actual current maximum $\lVert\mathbf H-(\mathbf m\cdot\mathbf H)\mathbf m\rVert$ in A/m. The supplied fixed-case configuration requests 1 A/m explicitly. No continuous-20, intermediate monotonicity or energy stop is added. A qualifying initial state can use zero updates. A saved checkpoint/m roundtrip and an independent full field must pass before the coordinating entry reports success; native candidate status alone is unverified. Sidecars bind policy and actual file identities. Failure output retains available saved-state hashes.

The current-case representative first qualified after 13,380 real BB updates: independent A/B residuals $(0.993908981643,0.993694428004)\,\mathrm{A/m}$. This is a one-state engineering stop, not persistent equilibrium or an application error bound. The historical both residuals $\le0.6\,\mathrm{A/m}$ plus the historical energy test $\le10^{-8}$ plus 20 consecutive accepted states verdict remains unchanged. The earlier explicit0.55 test fixture only covered a control-flow branch; it is not the representative tolerance.

Legacy `run` retains A-only pre-update $R_A/300000\le5\times10^{-5}$. `check_residual.py` retains the separate compatibility reader (`check` aliases `check_legacy`): field agreement, history agreement and both final residuals $\le1\,\mathrm{A/m}$ are required for its external flag. A normal legacy native stop can remain externally unaccepted. Do not feed new-policy output to the legacy-history reader; use `run_static.py`'s saved independent result.

See [representative workflow](REPRESENTATIVE_WORKFLOW.md) for original-seed generation, five-segment loss/state transfer, both-sublattice verification and the pure periodic structure definitions. The native static entry does not dump initial full H. Its seam evidence uses identical m/config/kernel/external H, shared field evaluator code, matching native initial residuals and an independently checked dynamic seam field. Final saved static H/m/CP verification does use actual files.

Explicit historical CLI ceilings are 30,000 updates and 180 native seconds; defaults remain10,000/1.5s with2s wrapper timeout. The representative explicitly requests30000/180/210. Resource exits never imply success. Model precision, RK4 stages, BB stepping, legacy limits and physical parameters were not changed by these ceilings.

Independent field agreement does not bound time integration, mesh, finite mirrors or model error. Dynamics run to a physical observation time; static residuals are not dynamic stops. Static auxiliary time is optimizer bookkeeping, not LLG time. Per-file field counts and stage timings must distinguish native fields, independent fields, setup, IO and outer coordination; overlapping inclusive measurements must not be added twice.

See the [current LaTeX formula/code map](MATHEMATICS.md) for notation. Historical numbers, criteria and limitations in this document retain their original scope.
