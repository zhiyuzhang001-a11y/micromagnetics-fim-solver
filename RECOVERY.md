# Complete local offline recovery

Qualified scope: macOS 27 arm64, system /bin/sh, /bin/bash, /usr/bin/openssl (tested LibreSSL3.3.6), basic OS tools/frameworks. The bootstrap branch does not require system/Xcode/Homebrew Python or an existing Conda installation. This public source repository itself is **not** a complete offline recovery archive.

While preparing a release, retain all exact Conda package archives named by requirements/conda-osx-arm64-explicit.txt, the prepared platform wheel/sdist and source, each package's metadata/licenses/notices, dependency/native build identities, and the actual self-contained installer. The tested installer is Miniconda3-py312_25.9.1-3-MacOSX-arm64.sh, [official origin](https://repo.anaconda.com/miniconda/), SHA256 `67108a40cca0ae1a59b74672341d94ed6641430e10371616426c31c2014e19b9`. Preserve its terms and embedded dependency licenses. No redistribution of these archives is performed here.

A complete archive uses these names:

```text
Recovery/
  bootstrap.sh                 # copy tools/bootstrap_recovery.sh
  check-install.sh             # copy tools/check_install.sh
  recover.py                   # copy tools/recover_release.py
  RECOVERY.md
  bootstrap/Miniconda3-py312_25.9.1-3-MacOSX-arm64.sh
  conda/                       # all exact actual archives
  CONDA_ARCHIVES.json           # copy requirements/conda-archives-manifest.json
  wheel/                       # one prepared platform wheel
  source/                      # matching source and sdist
  licenses/                    # installer, project and dependency notices/terms
  SHA256SUMS
  SHA256_MANIFEST.json          # relative file -> actual SHA256; excludes itself
```

Verify actual archives against their original package SHA256 values before creating the release manifest. A second verified independent copy is required; copies on the same physical computer are not off-device disaster backups. Do not include secrets/user outputs. A manifest records integrity, not an independent signature of trust.

## B: no usable Python or Conda

From the verified complete archive, choose unused absolute target/work paths; WORK must not contain spaces:

```sh
/bin/sh ./bootstrap.sh /tmp/micromagnetics-restored /tmp/micromagnetics-restore-work micromagnetics-restored
```

System OpenSSL checks the actual installer against the pinned official SHA before it runs. Only after that installer's own Python exists does it parse and verify every archived file and invoke recover.py. It then restores all exact local packages offline, installs the local wheel without dependency solving, checks dependencies, registers a prefix-local kernel and performs zero-field native diagnostics. Existing target/work directories are refused. BOOTSTRAP.json and restore/RESTORED.json record the actual interpreter and archive provenance. Installation success is not a new scientific qualification.

## A: an existing tested Conda manager is usable

```sh
/path/to/conda/bin/python -I ./recover.py --branch A --manager /path/to/conda --prefix /tmp/micromagnetics-restored-a --work /tmp/micromagnetics-restore-work-a --kernel micromagnetics-restored-a
```

The tested explicit transaction adapter accepts Conda25.9.0/25.9.1 and refuses other manager versions. Both branches use separate empty Conda/pip/fimrun caches and an owned configuration, no dependency solve or network download. Never update the original base or silently replace a kernel. A fresh native rebuild or Python implementation has a new identity: old strict checkpoints remain rejected; physical restoration is an explicit different grade.

For optional diagnosis, use `/bin/sh ./check-install.sh /absolute/environment/prefix kernel-name`. Its default prefix is HOME/miniconda3/envs/micromagnetics; pass your actual location when different. Missing interpreters produce recovery instructions before doctor is attempted. No .command daily launcher or Notebook install cell is needed.

The local acceptance demonstrated branch B with external system/Xcode Python, original Conda, old source paths and network denied. Independent review inspected the actual isolation logs/entry bytes and independently tested shell negative cases; it did not claim a second independent OS-isolated rebuild. See [acceptance](docs/ACCEPTANCE_SUMMARY.md) for GUI limitations. Unknown future systems require new qualification.
