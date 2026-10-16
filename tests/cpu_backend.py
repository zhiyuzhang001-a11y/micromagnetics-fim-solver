"""Six-process, 28-full-field packaging comparison; never a long-run benchmark."""
from pathlib import Path
import argparse
import hashlib
import json
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from make_fixture import make


def run(serial_bins, two_owner_bins, work, cap=20):
    start = time.monotonic()
    work = Path(work).resolve()
    work.mkdir(parents=True, exist_ok=False)
    make(work / 'fixture', 'smooth')
    config = work / 'fixture/config.dat'
    kernel = ROOT / 'examples/kernel125-mirror10.f64'
    calls = []

    def invoke(bins, label, target, arguments, expected):
        remaining = min(4., cap - (time.monotonic() - start))
        if remaining <= 0:
            raise TimeoutError('cumulative packaging-test budget')
        before = time.monotonic()
        result = subprocess.run([str(Path(bins).resolve() / target), *map(str, arguments)],
                                capture_output=True, text=True, timeout=remaining)
        calls.append({'backend': label, 'target': target, 'returncode': result.returncode,
                      'wall_s': time.monotonic() - before})
        (work / 'calls.json').write_text(json.dumps(calls, indent=2) + '\n')
        (work / (label + '-' + target + '.stderr')).write_text(result.stderr)
        assert result.returncode == expected, (label, target, result.stderr)

    for label, bins in [('serial', serial_bins), ('two-owner', two_owner_bins)]:
        out = work / label
        out.mkdir()
        invoke(bins, label, 'fim_inspect', [config, kernel, out / 'inspect'], 0)
        energy = json.loads((out / 'inspect/initial_energy.json').read_text())['total_J']
        invoke(bins, label, 'fim_dynamic',
               [config, kernel, out / 'dynamic', '12.5', '-', 0, .025, energy, 0], 0)
        dynamic = json.loads((out / 'dynamic/summary.json').read_text())
        assert dynamic['accepted_steps'] == 2 and dynamic['field_calls'] == 11
        # Deliberately tiny tolerance forces one real update and then step_budget.
        # This is an expected not_success branch, not a relaxation qualification.
        invoke(bins, label, 'fim_static',
               [config, kernel, out / 'dynamic/final.bin', out / 'static',
                'run_policy', '-', 3., 1e-20, 1, 2, 0, 0, -1591.5494309189535], 2)
        static = json.loads((out / 'static/native_policy_result.json').read_text())
        assert static['stop_reason'] == 'step_budget' and static['status'] == 'not_success'
        assert static['local_updates'] == 1 and static['field_calls'] == 2

    compared = []
    for stage in ['inspect', 'dynamic', 'static']:
        a, b = work / 'serial' / stage, work / 'two-owner' / stage
        names = sorted(p.name for p in a.iterdir()
                       if p.suffix in ['.bin', '.csv'] or p.name.endswith('_energy.json'))
        assert names
        for name in names:
            content = (a / name).read_bytes()
            assert content == (b / name).read_bytes(), stage + '/' + name
            compared.append({'file': stage + '/' + name,
                             'sha256': hashlib.sha256(content).hexdigest()})
    report = {'passed': True, 'scope': 'packaging-only fixed smooth synthetic fixture',
              'numeric_processes': 6, 'Models': 6, 'full_fields': 28,
              'RK4_updates_per_backend': 2, 'static_updates_per_backend': 1,
              'static_expected_not_success': True, 'scientific_outputs_byte_exact': compared,
              'independent_field_batch': 'not part of this test',
              'long_workflow': 'not rerun; archived same-source qualification is separate',
              'wall_s': time.monotonic() - start, 'calls': calls}
    (work / 'result.json').write_text(json.dumps(report, indent=2) + '\n')
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--serial-bins', type=Path, required=True)
    parser.add_argument('--two-owner-bins', type=Path, required=True)
    parser.add_argument('--work', type=Path, required=True)
    parser.add_argument('--cap', type=float, default=20)
    args = parser.parse_args()
    print(json.dumps(run(args.serial_bins, args.two_owner_bins, args.work, args.cap), indent=2))
