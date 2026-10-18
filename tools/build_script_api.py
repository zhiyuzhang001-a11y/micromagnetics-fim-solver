"""Build local native bindings explicitly; no scientific calculation or installation."""
from pathlib import Path
import subprocess
import sys
import hashlib
import json

ROOT = Path(__file__).resolve().parents[1]


def build():
    if sys.platform != 'darwin':
        raise RuntimeError('the first FM/FiM script release is qualified on macOS only')
    out = ROOT / 'build-script-api'
    out.mkdir(exist_ok=True)
    flags = subprocess.check_output(['pkg-config', '--cflags', '--libs', 'fftw3'], text=True).split()
    for name in ('fm', 'fim'):
        command = ['clang++', '-std=c++17', '-O2', '-dynamiclib', '-pthread', '-DLF_TWO_OWNER',
                   str(ROOT / 'src/script_api' / (name + '.cpp')), '-o', str(out / ('lib' + name + '.dylib'))]
        command += ['-framework', 'Accelerate'] if name == 'fm' else flags
        subprocess.run(command, check=True)
    kernel_flags = subprocess.check_output(['pkg-config', '--cflags', '--libs', 'mpfr', 'gmp'], text=True).split()
    subprocess.run(['clang++', '-std=c++17', '-O2', str(ROOT / 'src/script_api/kernel_builder.cpp'), '-o', str(out / 'kernel_builder'), *kernel_flags], check=True)
    receipt = {'schema': 'script-api-build-v1', 'platform': sys.platform,
               'source': {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                          for base in ('src', 'validation/fm') for p in (ROOT / base).rglob('*') if p.is_file()},
               'binaries': {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in out.glob('*.dylib')}}
    (out / 'build.json').write_text(json.dumps(receipt, indent=2) + '\n')
    print(out)


if __name__ == '__main__':
    build()
