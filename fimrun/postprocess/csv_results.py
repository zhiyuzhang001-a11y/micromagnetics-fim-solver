"""Reload exported analysis measurements without opening their original sources."""
import csv
import hashlib
import io
import json
import math
from pathlib import Path

from .analysis import Analysis, _TOKEN


def load_csv(path, *, stage=None, segment=None):
    """Read an Analysis.to_csv export; no OVF reads, analysis or solver calls.

    Saved source bindings are retained as historical evidence, not reverified.
    The CSV itself is read once and its content hash accompanies the result.
    """
    if stage not in (None, 'rk4', 'sdesc'):
        raise ValueError('stage must be rk4, sdesc or None')
    if segment is not None and (not isinstance(segment, str) or not segment):
        raise ValueError('segment must be a nonempty exact id or None')
    path = Path(path).expanduser().resolve()
    raw = path.read_bytes()
    reader = csv.DictReader(io.StringIO(raw.decode('utf-8-sig')), strict=True)
    columns = reader.fieldnames
    required = {'source_index', 'input_index', 'source_bindings', 'reason_codes',
                'time_s', 'valid_pair', 'valid_tracking', 'valid_velocity'}
    empty_columns = {'source_index', 'AB_radius_difference_m', 'AB_chi_difference_rad',
                     'A_area_vx_mps', 'A_area_vy_mps', 'B_area_vx_mps', 'B_area_vy_mps'}
    if not columns or len(columns) != len(set(columns)) or not (required <= set(columns) or empty_columns <= set(columns)):
        raise ValueError('Expected a complete analysis CSV exported by Analysis.to_csv; not a scalar CSV')
    rows, indices, paths = [], [], {str(path)}
    text_suffixes = ('_sha256', '_reason', '_convention', '_legacy_missing_header')
    integers = {'source_index', 'input_index', 'accepted_index', 'iteration', 'tracking_part'}
    for number, saved in enumerate(reader, 2):
        if not required <= set(columns):
            raise ValueError('Missing analysis columns for nonempty CSV')
        if None in saved or any(value is None for value in saved.values()):
            raise ValueError(f'CSV row {number}: wrong number of columns')
        row = dict(saved)
        try:
            binding = json.loads(row['source_bindings'])
            if not isinstance(binding, dict) or binding.get('schema') != 'source-bindings-v1' or not isinstance(binding.get('sources'), dict):
                raise ValueError('invalid source_bindings')
            # Protect historical input paths even when those files are now offline.
            for source in binding['sources'].values():
                if isinstance(source, dict) and isinstance(source.get('path'), str):
                    paths.add(str(Path(source['path']).expanduser().resolve()))
            for key, value in saved.items():
                boolean = key.startswith('valid_') or '_valid_' in key
                numeric = key in integers or key == 'time_s' or (
                    key.startswith(('A_', 'B_', 'AB_')) and not key.endswith(text_suffixes))
                if boolean:
                    if value not in ('True', 'False', 'nan', ''):
                        raise ValueError('invalid boolean in '+key)
                    row[key] = value == 'True'
                elif numeric:
                    value = float(value) if value else math.nan
                    if math.isinf(value):
                        raise ValueError('infinite value in '+key)
                    if key in integers and math.isfinite(value):
                        if value < 0 or not value.is_integer():
                            raise ValueError('invalid index in '+key)
                        value = int(value)
                    row[key] = value
            index = row.pop('source_index')
            if not isinstance(index, int):
                raise ValueError('invalid source_index')
        except (ValueError, TypeError) as error:
            raise ValueError(f'CSV row {number}: {error}') from error
        if stage is not None and row.get('stage') != stage:
            continue
        if segment is not None and row.get('segment_id') != segment:
            continue
        rows.append(row)
        indices.append(index)
    if (stage is not None or segment is not None) and not rows:
        raise ValueError('Selection has no matching rows')
    for key, selector in [('stage', stage), ('segment_id', segment)]:
        known = {row[key] for row in rows if row.get(key) not in (None, '', 'nan')}
        if selector is None and len(known) > 1:
            raise ValueError('Ambiguous '+key+'; select one exact value')
    result = Analysis(_TOKEN, rows, indices, paths, [c for c in columns if c != 'source_index'])
    result._csv_source = {'path': str(path), 'sha256': hashlib.sha256(raw).hexdigest(),
                          'original_sources_reverified': False}
    return result
