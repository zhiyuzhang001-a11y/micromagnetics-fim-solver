#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-only
# Recovery-only entry: system shell/OpenSSL first, archived Python afterwards.
set -eu
fail() { printf '%s\n' "$*" >&2; exit 2; }
[ "$#" -eq 3 ] || fail 'Usage: /bin/sh bootstrap.sh ABSOLUTE_PREFIX ABSOLUTE_UNUSED_WORK KERNEL_NAME'
prefix=$1
work=$2
kernel=$3
case "$prefix" in /*) ;; *) fail 'PREFIX must be absolute.' ;; esac
case "$work" in /*) ;; *) fail 'WORK must be absolute.' ;; esac
case "$work" in *' '*) fail 'The archived installer requires a work path without spaces.' ;; esac
case "$kernel" in ''|*[!a-zA-Z0-9._-]*) fail 'Use a kernel name containing only letters, digits, dot, underscore or hyphen.' ;; esac
[ ! -e "$prefix" ] && [ ! -L "$prefix" ] || fail 'Refusing existing target prefix.'
[ ! -e "$work" ] && [ ! -L "$work" ] || fail 'Refusing existing work directory.'
[ -x /usr/bin/openssl ] || fail 'System /usr/bin/openssl is required to verify the archived bootstrap installer. See RECOVERY.md.'
[ "$(/usr/bin/uname -m)" = arm64 ] || fail 'This recovery release is qualified for macOS 27 arm64 only.'
case "$(/usr/bin/sw_vers -productVersion)" in 27.*) ;; *) fail 'This recovery release is qualified for macOS 27 arm64 only.' ;; esac
release_dir=$(CDPATH= cd "$(/usr/bin/dirname "$0")" && pwd -P)
installer="$release_dir/bootstrap/Miniconda3-py312_25.9.1-3-MacOSX-arm64.sh"
expected=67108a40cca0ae1a59b74672341d94ed6641430e10371616426c31c2014e19b9
[ -f "$installer" ] || fail "Archived installer is missing: $installer. Restore the verified Recovery copy."
actual=$(/usr/bin/openssl dgst -sha256 -r "$installer")
actual=${actual%% *}
[ "$actual" = "$expected" ] || fail 'Archived installer SHA256 mismatch; no bootstrap or target installation was started. Restore the verified Recovery copy.'
printf '%s\n' "Verified archived arm64 installer: $actual"
# Preserve HOME and the user's configuration files; isolate this process only.
PATH=/usr/bin:/bin:/usr/sbin:/sbin
export PATH
unset PYTHONHOME PYTHONPATH PYTHONUSERBASE PYTHONSTARTUP PYTHONEXECUTABLE VIRTUAL_ENV
unset CONDA_EXE CONDA_PREFIX CONDA_DEFAULT_ENV CONDA_SHLVL CONDA_PYTHON_EXE CONDA_NO_PLUGINS MAMBA_ROOT_PREFIX
CONDA_OFFLINE=true
PYTHONNOUSERSITE=1
PYTHONDONTWRITEBYTECODE=1
export CONDA_OFFLINE PYTHONNOUSERSITE PYTHONDONTWRITEBYTECODE
/bin/mkdir "$work"
manager="$work/bootstrap"
printf '%s\n' 'Bootstrapping solely from the verified archived installer; external Python and existing Conda are not used.'
/bin/bash "$installer" -b -m -p "$manager"
# Only the verified installer's own Python may parse/verify the release manifest.
"$manager/bin/python" -I -c '
from pathlib import Path
import hashlib,json,sys
release=Path(sys.argv[1]).resolve();work=Path(sys.argv[2]).resolve()
assert Path(sys.prefix).resolve()==work/"bootstrap", "Unexpected bootstrap interpreter"
manifest=json.loads((release/"SHA256_MANIFEST.json").read_text())
for rel,digest in manifest.items():
    path=(release/rel).resolve()
    if not path.is_relative_to(release) or not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest()!=digest:
        raise SystemExit("Recovery archive SHA256 mismatch: "+rel)
receipt={"status":"verified_with_archived_python","entry":"system shell + system OpenSSL -> archived installer -> archived Python","installer_sha256":sys.argv[3],"python":sys.executable,"base_prefix":sys.base_prefix,"stdlib_json":json.__file__,"verified_files":len(manifest),"fields":0}
(work/"BOOTSTRAP.json").write_text(json.dumps(receipt,indent=2)+"\n")
print(json.dumps(receipt))
' "$release_dir" "$work" "$expected"
exec "$manager/bin/python" -I "$release_dir/recover.py" --branch B --bootstrap-prefix "$manager" --prefix "$prefix" --work "$work/restore" --kernel "$kernel"
