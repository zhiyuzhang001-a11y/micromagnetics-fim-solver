# Visible running outputs: 0.2.0rc3

Notebook stages now write into a visible `<name>-running-<suffix>/` directory at the configured sampling interval. `progress.json` records the lifecycle and hashes of fully written OVF frames. A/B frames are committed only after both files are complete. Successful publication keeps the existing flat CSV/OVF/state filenames and overwrite protections.

`pp.analyze(running_directory, ...)` freezes the committed frame inventory at call time, validates its immutable OVFs and checks their time, step, run and segment metadata. It does not depend on a final state or the mutable scalar CSV. A final state serialization failure therefore leaves saved frames available for analysis. Final frame failure still attempts to save the accepted state. Partial frame pairs are excluded; tampered committed frames are rejected.

## Local installed validation

The noneditable 0.2.0rc3 package was installed and checked on macOS 27 arm64 with Python 3.12.14 and NumPy 2.3.5. Runtime integrity, native library loading and dependency checks passed. Native payloads were reused byte-for-byte from the prior local installation; this output change does not change numerical equations.

- 48 installed regressions passed: 34 installation/postprocessing/fault checks and 14 Notebook lifecycle checks.
- A real 16x16x1 FiM trajectory included exchange, cross exchange, onsite coupling, DMI, anisotropy, periodic demag and constant SOT. Both rc2 and rc3 completed eight 1 fs steps and saved five A/B frame pairs. Final magnetization was bitwise identical; both used 41 field evaluations.
- Nine reads during the updated real trajectory successfully inspected and analyzed committed frames. The final state inventory also loaded through the existing frames_from_state interface.
- The same real trajectory with only final state serialization fault-injected preserved all five pairs in its visible directory. Postprocessing succeeded and final magnetization remained identical to the successful baseline. No actual kernel cache was removed.
- An independent temporary Jupyter kernel loaded rc3, completed a 3x3x1 two-step trajectory and read its three saved frame pairs. Existing user kernels and scientific data were not restarted or modified.

Two stale local test fixtures were corrected after reproducing their errors on unchanged rc2: the preview start stub must accept open_browser, and read-only progress refresh must not consume a synthetic convergence sequence. These fixture corrections change no solver behavior.

## Limits

These checks qualify installation and short small-grid output behavior, not arbitrary long production runs, large-grid performance or foreground VS Code rendering. A hard kill may leave status marked running. Disk exhaustion/power loss cannot guarantee in-progress file completeness; only hash-validated committed frames are analyzed. During successful final publication, paths move: retry concurrent reads using the final state after publication. The live output manifest is not a per-frame restart checkpoint. Existing Notebook kernels must be restarted explicitly before using changed installed sources; do not hot reload a live simulation.
