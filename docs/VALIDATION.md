# Validation matrix and reproducibility

The current `tests/smoke.py` can rerun: canonical model evaluation; smooth
RK4 1+1 versus 2 update restoration; real E/loss transfer; dynamic final state
to SDesc test seed; 5→10 SDesc history restoration; a quick uniform dynamic→static
run; a real A-only native stop with B failing external acceptance; saved field versus independent NumPy full field; A/B final residual versus
history; corrupted saved-field/history rejection; and no-argument CLI rejection. These are
new packaging checks, not a replay of archived trajectories.

Separate source targets included but not scientifically rerun in packaging:

- `label_prefix`: swapped material labels, fixed 12.5 fs and 16+16 updates only.
  Historical 33-state inverse-permutation difference was zero. Inputs/history
  from that historical experiment are not bundled, and no public full-label
  reproduction harness is claimed.
- `fm_d1ns`: macOS Accelerate/vDSP SP4 D1NS scope, fixed original guards and
  explicit checkpoint-import rules. The long reference trajectories, official
  benchmark data and their reproduction harness are not bundled. Source build
  and usage rejection can be checked; historical FM accuracy is reported only.
- `d0_reference`: fixed-eight 192-bit Gaussian reference, cached certified
  32-node roots/weights, 32 panels, T=16 and analytic tail/error enclosures.
  A user can separately run `d0_reference formal-point
  validation/d0/nodes/roots.txt 0 0 0 NEW.tsv` for one reference point.
  Packaging builds this target but does not rerun its integral. The 48-component
  archived production/reference comparison is in results; production kernel
  generation for these two FM shapes is not bundled. This is not the FiM kernel
  or complete-table certification. Cache construction/proof software is not
  included; the exact qualified node data is preserved by hash.

Historical results are explicitly separate from runnable packaging checks:

- Fine/coarse k=(1,1), 51.2 ps FiM modal qualification: 12.5 and 25 fs passed
  its limited engineering comparison; its linear-reference error bound was not
  a rigorous interval/infinite-PBC certificate.
- Historical main SDesc stopped at 8687 updates via A-pre schedule sampling;
  post A/B residuals were about 17.4222/17.0025 A/m. Both≤1 was false.
- A separate fixed-checkpoint continuation first crossed both≤1 at global
  13380 (about 0.99391/0.99369 A/m); no persistence acceptance was established.
  Its checkpoint-specific entry is intentionally not presented as general code.
- D0's archived 8×6 comparisons all passed reference radius≤1e-12 and worst
  endpoint production error≤1e-10. Maximum radius 2.0816681711721685e-17;
  maximum endpoint error 4.347824180426361e-17. See JSON values, not this rounded text.

See KNOWN_FAILURES and MIRROR_TRUNCATION for retained failures and open limits.
No historical test is silently reclassified as rerun or all-goals completion.

## Current explicit static policy and original-seed full workflow

The normal entry now independently verifies actual saved both-sublattice current residuals under explicit FIM_POST_PH_MAX_V1. The fixed original-seed100fs/500ps chain followed by13380BB updates passed the current1A/m engineering stop. See [portable workflow, exact scope and reported timings](REPRESENTATIVE_WORKFLOW.md). Pure structure code and original-direction fixture generation are included; archived raw trajectories/audit records are not.

Publication reuses that reviewed source/input-matched numerical evidence and runs only bounded packaging/policy checks. Dry-run/mock control checks are not a rerun of500ps or scientific validation. The public reproduction adds an independent initial-field check to the archived verification boundary. Legacy run and its archived verdicts remain intact; neither the old0.6+energy+20failures nor persistent/physical limitations are reclassified.

## 2026-10-16 bounded local current campaign closure

The fixed125²/M10 full time matrix passed; finite M10/20/40 velocity/Hall/radius/center targets passed while deformation failed. The independently prepared250²/M10 early screen failed radius/deformation sensitivity targets. Fine0–2ps temporal checks do not certify50/400ps time convergence; fine motion signal was unresolved. See [scope, protocol differences and startup](LOCAL_DELIVERY_STATUS.md) and [machine-readable summary](../results/current-sot-campaign-summary.json). No continuum/material qualification is claimed.
