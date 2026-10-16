"""GPL-3.0-only. Fixed original-seed 100 fs / 500 ps FiM workflow.

No private input, archived checkpoint, plotting library or internal ledger import.
Dry-run describes control only; it does not validate numerical results.
"""
from pathlib import Path
import argparse
import csv
import hashlib
import json
import os
import subprocess
import sys
import time
import numpy as np
from make_representative_fixture import make
from periodic_structure import observe
import independent_field as independent

ROOT = Path(__file__).resolve().parents[1]
INTERVALS = [(0, 100), (100, 200), (200, 300), (300, 400), (400, 500)]
ORIGINAL_E = -1.1988970967055624e-14
EXT = [0., 0., -1591.5494309189535]
CONFIG_SHA = '79d5d89eb84119dbd305f2c427bbeb4ef175bdb8f54cfa3a2d97093d43af6371'
KERNEL_SHA = 'db71f379e2bea728a475d9e0c6e5e1183c7830ee1ba91e6909f84c532ec012b6'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(path, value):
    Path(path).write_text(json.dumps(value, indent=2, allow_nan=False) + '\n')


def read_m(path):
    return np.fromfile(path, dtype='<f8').reshape(2, 1, 125, 125, 3)


def read_H(out, tag):
    return np.stack([np.fromfile(out / (tag + '_H_' + sub + '.bin'), dtype='<f8')
                     .reshape(1, 125, 125, 3) for sub in ['A', 'B']])


def residual(m, h):
    return np.max(np.linalg.norm(h - m * np.sum(m * h, axis=-1, keepdims=True),
                                 axis=-1), axis=(1, 2, 3)).tolist()


def dynamic_command(binary, config, kernel, out, start, end, previous, loss):
    return [str(binary), str(config), str(kernel), str(out), '100',
            str(previous / 'final.bin') if previous else '-', str(start), str(end),
            repr(ORIGINAL_E), repr(loss)]


def static_command(binary, config, kernel, out, seed):
    return [sys.executable, str(ROOT / 'tools/run_static.py'), '--binary', str(binary),
            '--config', str(config), '--kernel', str(kernel), '--seed', str(seed),
            '--policy-config', str(ROOT / 'configs/static_stop_current_case.json'),
            '--max-updates', '30000', '--max-fields', '30001',
            '--native-budget', '180', '--timeout', '210', '--output', str(out)]


def run(args):
    start_clock = time.monotonic()
    out = args.output.resolve(); bins = args.bins.resolve()
    config = out / 'fixture/config.dat'; kernel = ROOT / 'examples/kernel125-mirror10.f64'
    if out.exists():
        raise ValueError('output must be new; completed segments are never overwritten or retried')
    description = {'dt_fs': 100, 'T_ps': 500, 'dynamic_steps': 5000,
                   'intervals_ps': INTERVALS, 'original_energy_J': ORIGINAL_E,
                   'initial_loss_J': 0, 'continuation_loss': 'previous summary cumulative_rk_dissipated_J',
                   'static_updates_cap': 30000, 'static_native_s': 180, 'static_wrapper_s': 210,
                   'overall_timeout_s': 600, 'requested_Apm': 1,
                   'dry_run': args.dry_run}
    if args.dry_run:
        description['dynamic_commands'] = [dynamic_command(
            bins / 'fim_dynamic', config, kernel, out / 'dynamic' / f'{a}_{b}', a, b,
            out / 'dynamic' / f'{a-100}_{a}' if a else None,
            0. if not a else 'PREVIOUS_CUMULATIVE_LOSS') for a, b in INTERVALS]
        description['static_command'] = static_command(bins / 'fim_static', config, kernel,
                                                       out / 'static', out / 'dynamic/400_500/final.bin')
        return description
    out.mkdir(parents=True)
    result = {'status': 'running', 'real_fields': 0, 'processes': [], **description}
    def checkpoint():
        result['wall_s'] = time.monotonic() - start_clock
        write(out / 'workflow.json', result)
    def remaining():
        value = 600 - (time.monotonic() - start_clock)
        if value <= 0:
            raise TimeoutError('overall workflow timeout')
        return value
    def invoke(label, command, cap, destination):
        # Both independent deadlines and a controller deadline apply. The external
        # subprocess timeout bounds every native call, including incomplete failures.
        t = time.monotonic()
        try:
            p = subprocess.run(command, capture_output=True, text=True,
                               timeout=min(cap, remaining()),
                               env={**os.environ, 'PYTHONDONTWRITEBYTECODE': '1'})
        except subprocess.TimeoutExpired:
            result['field_count_complete'] = False
            result['processes'].append({'label': label, 'wall_s': time.monotonic()-t,
                                        'status': 'external_timeout'})
            checkpoint()
            raise
        row = {'label': label, 'returncode': p.returncode,
               'wall_s': time.monotonic()-t, 'wall_includes_native_internal_IO': True}
        result['processes'].append(row)
        (out / (label + '.stdout')).write_text(p.stdout)
        (out / (label + '.stderr')).write_text(p.stderr)
        if p.returncode:
            # Preserve native outputs and count known completed work on failure.
            report = destination / 'run_result.json'
            if report.exists():
                saved = json.loads(report.read_text())
                n = saved.get('real_native_fields')
                result['field_count_complete'] = n is not None
                result['real_fields'] += (n or 0) + saved.get('real_independent_fields', 0)
            else:
                result['field_count_complete'] = False
            raise RuntimeError(label + ' failed; no retry')
        remaining()
        return row
    def independent_saved(label, m, saved_h):
        remaining()
        if not np.isfinite(m).all() or not np.isfinite(saved_h).all():
            raise ValueError('nonfinite saved seam')
        result['real_fields'] += 1  # Count attempted independent full-field work.
        t = time.monotonic(); h = independent.fields(m)
        error = float(np.max(np.linalg.norm(h-saved_h, axis=-1)) /
                      max(1., float(np.max(np.linalg.norm(h, axis=-1)))))
        record = {'field_relative_error': error, 'residual_A_B_Apm': residual(m, h),
                  'wall_s': time.monotonic()-t, 'real_fields': 1}
        result[label] = record
        if not np.isfinite(h).all() or error > 1e-10:
            raise ValueError('independent saved-field mismatch')
        remaining()
    try:
        make(out / 'fixture')
        if sha(config) != CONFIG_SHA or sha(kernel) != KERNEL_SHA:
            raise ValueError('fixed fixture/kernel differs from qualified identity')
        independent.configure(kernel, config=config, external_H_Apm=EXT)
        result['configuration_sha256'] = sha(config); result['kernel_sha256'] = sha(kernel)
        previous = None; loss = 0.; segments = []
        for begin, end in INTERVALS:
            dest = out / 'dynamic' / f'{begin}_{end}'
            row = invoke(f'dynamic_{begin}_{end}', dynamic_command(
                bins / 'fim_dynamic', config, kernel, dest, begin, end, previous, loss), 60, dest)
            summary = json.loads((dest / 'summary.json').read_text())
            result['real_fields'] += summary['field_calls']
            if summary['accepted_steps'] != 1000 or summary['field_calls'] != 5001 or abs(summary['reached_time_ps']-end) > 1e-10:
                raise ValueError('wrong dynamic work/time')
            if summary['energy_original_J'] != ORIGINAL_E or summary['loss_before_J'] != loss:
                raise ValueError('energy/loss provenance mismatch')
            if previous:
                for old, new in [('final.bin', 'step_0.bin'), ('final_H_A.bin', 'initial_H_A.bin'),
                                 ('final_H_B.bin', 'initial_H_B.bin')]:
                    if (previous / old).read_bytes() != (dest / new).read_bytes():
                        raise ValueError('dynamic seam bytes differ')
            else:
                if (out / 'fixture/seed.f64').read_bytes() != (dest / 'step_0.bin').read_bytes() or summary['energy_start_J'] != ORIGINAL_E:
                    raise ValueError('initial state/energy differs')
                independent_saved('initial_independent', read_m(dest / 'step_0.bin'), read_H(dest, 'initial'))
            m = read_m(dest / 'final.bin'); h = read_H(dest, 'final')
            if not np.isfinite(m).all() or not np.isfinite(h).all() or np.max(abs(np.linalg.norm(m, axis=-1)-1)) > 1e-12:
                raise ValueError('nonfinite/nonunit saved dynamic state')
            obs = [observe(m[i, 0], i) for i in [0, 1]]
            if not all(v['valid_single'] for v in obs):
                raise ValueError('invalid dynamic texture')
            segments.append({'end_ps': end, 'state_sha256': sha(dest / 'final.bin'),
                             'residual_A_B_Apm': residual(m, h), 'observations': obs,
                             'summary': summary})
            result['dynamic_segments'] = segments
            loss = summary['cumulative_rk_dissipated_J']; previous = dest
            checkpoint(); print(json.dumps({'time_ps': end, 'process_wall_s': row['wall_s']}), flush=True)
        independent_saved('dynamic_static_seam_independent', m, h)
        seed = previous / 'final.bin'; seed_sha = sha(seed)
        invoke('static', static_command(bins / 'fim_static', config, kernel, out / 'static', seed),
               210, out / 'static')
        saved = json.loads((out / 'static/run_result.json').read_text())
        result['real_fields'] += saved['real_native_fields'] + saved['real_independent_fields']
        request = json.loads((out / 'static/request.json').read_text())
        if sha(seed) != seed_sha or request['input_sha256'] != seed_sha:
            raise ValueError('static seed identity mismatch')
        with (out / 'static/native/history.csv').open() as f:
            first = next(csv.DictReader(f))
        if int(first['local_update']) != 0 or int(first['global_update']) != 0 or [float(first['post_A_Apm']), float(first['post_B_Apm'])] != residual(m, h):
            raise ValueError('static initial history differs from actual dynamic seam')
        if saved['status'] != 'success' or saved['independent_check']['status'] != 'passed':
            raise ValueError('static saved-state qualification failed')
        final = read_m(out / 'static/native/final.bin')
        obs = [observe(final[i, 0], i) for i in [0, 1]]
        if not all(v['valid_single'] for v in obs):
            raise ValueError('invalid final texture')
        result.update(status='success', static_result=saved, final_observations=obs,
                      static_initial_full_H_dump_available=False,
                      static_seam_evidence='same input/config/kernel/external field, shared model, matching native initial residuals and independent seam full field',
                      final_m_sha256=sha(out / 'static/native/final.bin'),
                      checkpoint_sha256=sha(out / 'static/native/checkpoint.bin'),
                      field_count_complete=True,
                      independent_initial_check_extra_to_archived_baseline=True)
        remaining(); checkpoint(); remaining()
        return result
    except Exception as error:
        result.update(status='failed', failure_type=type(error).__name__, failure_reason=str(error))
        checkpoint()
        raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bins', type=Path, default=ROOT / 'build')
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--dry-run', action='store_true')
    try:
        print(json.dumps(run(parser.parse_args()), indent=2, allow_nan=False))
    except Exception as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(2)
