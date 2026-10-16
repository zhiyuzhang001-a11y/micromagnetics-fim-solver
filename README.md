# BORIS-referenced FiM validation

Independent, unofficial research code for a fixed two-sublattice conservative micromagnetic model. Not an official BORIS release. Physics conventions reference BORIS v3.80, commit `6f55516f46f5b6b6ed92bb030d62abab87b4a2f0`. GPL-3.0-only; see [NOTICE](NOTICE), [COPYING](COPYING) and the [file license map](docs/FILE_LICENSE_MAP.json).

## Build and short checks

The supported build now defaults to the adopted **C1 + two-owner CPU local-field backend** (main plus one persistent helper). FFTW remains serial; RK4 still evaluates all five fields per step. No DP54, demagnetization extrapolation or C3 reuse is enabled. This is a fixed-model backend, not an automatic solver choice. See [CPU delivery and limits](docs/CPU_ACCELERATION.md).

Requires C++17, pkg-config, FFTW3, Python 3 and NumPy. From this repository:

```sh
python3 tools/build.py --out build
python3 tests/smoke.py --bins build --work output/compatibility-smoke
python3 tests/static_stop_policy.py --static-binary build/fim_static
```

For the explicit serial C1 rollback, use a separate build directory:

```sh
python3 tools/build.py --serial-local --out build-serial
python3 tests/build_backend.py
# Optional bounded numeric packaging comparison: 6 processes, 28 full fields.
python3 tests/cpu_backend.py --serial-bins build-serial --two-owner-bins build --work output/cpu-backend
```

These bounded packaging checks do not replay the archived scientific suite. The optional high-checkpoint IO test requires `--high-checkpoint` pointing to a generated test fixture; it otherwise skips explicitly.

## Normal static entry

`tools/run_static.py` implements explicit `FIM_POST_PH_MAX_V1`: both sublattices' actual current maximum projected H, in A/m. A tolerance must be configured, overridden or inherited from a bound checkpoint sidecar. Only `configs/static_stop_current_case.json` requests 1 A/m for the canonical fixed FiM model; it is not an implicit tolerance for all simulations.

A small uniform synthetic example, using new output directories:

```sh
python3 tools/make_fixture.py output/uniform
python3 tools/run_static.py --binary build/fim_static \
  --config output/uniform/config.dat --kernel examples/kernel125-mirror10.f64 \
  --seed output/uniform/seed.f64 --policy-config configs/static_stop_current_case.json \
  --max-updates 0 --max-fields 1 --native-budget 1.5 --timeout 2 \
  --output output/uniform-static
```

Success requires saving/reloading the actual m/checkpoint, matching identities, and an independent field check. Native candidate success alone is unverified. Read `stop_reason`, native residuals and `independent_check` separately. Budget exhaustion, nonfinite values, IO or verification failures are not success. A raw seed starts fresh BB history; `--restore` preserves it. A checkpoint without a policy sidecar requires explicit `--adopt-legacy-checkpoint`.

Explicit resource ceilings support 30,000 updates / 180 native seconds; defaults remain 10,000 updates, 1.5 native seconds and 2 overall seconds. `--max-fields` bounds native calls; a successful independent check adds one full field. Legacy `fim_static ... run ...` retains its A-only pre-update schedule and 10,000-update cap. Dynamic termination remains physical time.

## Fixed representative workflow

The independently reviewed original-seed example actually completed 100 fs RK4 LLG to 500 ps (5,000 steps), then first qualified at 13,380 BB updates. Saved-state independent A/B residuals were **0.993908981643 / 0.993694428004 A/m**. Dynamic and static process walls were 29.719428 and 18.889745 s; their 48.609173 s sum is not a speedup or whole-project wall time.

A clean, portable reproduction entry generates the original fixed direction profile and uses five continuous 100 ps segments, followed by the explicit 1 A/m static entry:

```sh
python3 tools/run_representative.py --bins build --output output/representative --dry-run
# The following is a full workflow, not a short smoke check:
python3 tools/run_representative.py --bins build --output output/representative
```

Dry-run only describes control; it performs no numerical validation. See [workflow and reported results](docs/REPRESENTATIVE_WORKFLOW.md), [numerical interpretation](docs/NUMERICAL_GUIDE.md), [validation scope](docs/VALIDATION.md), [known failures](docs/KNOWN_FAILURES.md), [model and units](docs/MODEL_AND_UNITS.md), [installation](docs/INSTALL.md), [mirror limits](docs/MIRROR_TRUNCATION.md), [provenance](docs/PROVENANCE.md) and [non-GPU research status](docs/NON_GPU_ACCELERATION_RESEARCH.md).

The same-source adopted CPU backend also has archived four-chain dynamic-to-static qualification: serial B1/B2 48.630894/49.070129 s and two-owner C1/C2 44.779432/44.762753 s, conservative min(B)/max(C)=1.086010. Those hardware-specific timings are not a new publication benchmark; see the [sanitized evidence summary](results/cpu-acceleration-summary.json).

This fixed-case engineering qualification does not certify a local/global minimum, spatial or material accuracy, quantitative agreement with a user's BORIS installation, or driven applications. Historical failures remain historical failures. No private OVF, user script, archived trajectory, compiled binary or dependency library is bundled.
