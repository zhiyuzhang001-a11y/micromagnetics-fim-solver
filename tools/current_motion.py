"""Accepted-state motion, requiring a continuous single texture over the whole window."""
import csv
from pathlib import Path
import numpy as np


def rows(path):
    return list(csv.DictReader(Path(path).open()))


def motion(path, case):
    records = rows(path)
    J = np.array(case['drive']['Jc_Apm2'][:2])
    current = np.linalg.norm(J)
    result = {
        'fit_window_ps': [float(records[0]['time_ps']), float(records[-1]['time_ps'])],
        'current_direction': None if current == 0 else (J / current).tolist(),
        'current_axes_status': 'not_applicable' if current == 0 else 'defined',
        'sublattices': [], 'research_qualification': 'not_checked',
        'grid_mirror_convergence': 'not_checked',
    }
    curves, times = [], []
    for i in [0, 1]:
        rr = [r for r in records if int(r['sub']) == i]
        xy = np.array([[float(r['x_nm']), float(r['y_nm'])] for r in rr])
        time = np.array([float(r['time_ps']) for r in rr]) * 1e-12
        valid = bool(
            np.isfinite(xy).all() and np.isfinite(time).all()
            and np.all(np.diff(time) > 0)
            and all(int(r['valid_single']) and int(r['continuous'])
                    and not int(r['singular']) for r in rr)
        )
        v = fit = delta = budget = None
        if valid:
            delta = xy[-1] - xy[0]
            if current > 0 and len(rr) > 1:
                coef = np.polyfit(time - time[0], (xy - xy[0]) * 1e-9, 1)
                v = coef[0]
                fit = float(np.max(np.linalg.norm(
                    (time - time[0])[:, None] * coef[0] + coef[1]
                    - (xy - xy[0]) * 1e-9, axis=1)))
            radius = float(rr[0]['radius_nm'])
            budget = .01 * radius if np.isfinite(radius) and radius > 0 else None
        resolved = bool(current > 0 and valid and budget is not None
                        and np.linalg.norm(delta) > 10 * budget and v is not None)
        vp = vt = hall = None
        if resolved:
            e = J / current
            vp = float(v @ e)
            vt = float(v @ np.array([-e[1], e[0]]))
            hall = float(np.degrees(np.arctan2(vt, vp)))
        result['sublattices'].append({
            'center_valid': valid,
            'drift_nm': None if delta is None else delta.tolist(),
            'fit_velocity_vector_mps': None if v is None else v.tolist(),
            'velocity_vector_mps': v.tolist() if resolved else None,
            'fit_max_residual_m': fit, 'center_error_budget_nm': budget,
            'directional_status': ('not_applicable' if current == 0 else
                                   'invalid' if not valid else
                                   'resolved' if resolved else 'unresolved'),
            'v_parallel_mps': vp, 'v_perp_mps': vt, 'Hall_deg': hall,
            'last_valid_single': bool(int(rr[-1]['valid_single'])),
        })
        curves.append(xy if valid else None)
        times.append(time)
    common_valid = bool(all(x is not None for x in curves)
                        and np.array_equal(times[0], times[1]))
    if common_valid:
        result['relative_displacement_nm'] = (
            (curves[0][-1] - curves[1][-1]) - (curves[0][0] - curves[1][0])).tolist()
        result['common_displacement_nm'] = (
            .5 * ((curves[0][-1] + curves[1][-1])
                  - (curves[0][0] + curves[1][0]))).tolist()
    else:
        result['relative_displacement_nm'] = result['common_displacement_nm'] = None
    vectors = [x['fit_velocity_vector_mps'] for x in result['sublattices']]
    common = (None if not common_valid or any(v is None for v in vectors)
              else .5 * (np.array(vectors[0]) + vectors[1]))
    budgets = [x['center_error_budget_nm'] for x in result['sublattices']]
    # Worst-case propagated center error of (R_A+R_B)/2; do not cancel uncertainties.
    common_budget = (None if not common_valid or any(b is None for b in budgets)
                     else .5 * sum(budgets))
    resolved_common = bool(
        current > 0 and common is not None and common_budget is not None
        and np.linalg.norm(result['common_displacement_nm']) > 10 * common_budget)
    result.update(
        common_center_valid=common_valid,
        common_center_error_budget_nm=common_budget,
        common_fit_velocity_vector_mps=None if common is None else common.tolist(),
        common_directional_status=('not_applicable' if current == 0 else
                                   'invalid' if not common_valid else
                                   'resolved' if resolved_common else 'unresolved'),
        common_velocity_vector_mps=common.tolist() if resolved_common else None,
        common_v_parallel_mps=None, common_v_perp_mps=None, common_Hall_deg=None)
    if resolved_common:
        e = J / current
        vp = float(common @ e)
        vt = float(common @ np.array([-e[1], e[0]]))
        result.update(common_v_parallel_mps=vp, common_v_perp_mps=vt,
                      common_Hall_deg=float(np.degrees(np.arctan2(vt, vp))))
    return result
