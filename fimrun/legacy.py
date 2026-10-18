"""Describe the old Case without changing any of its historical numerical behavior."""
from dataclasses import asdict
from .api import Case


def describe_legacy(case):
    if not isinstance(case, Case):
        raise TypeError('describe_legacy expects the compatibility Case')
    operations = []
    if case.workflow != 'drive':
        operations += [{'operation': 'legacy_dynamic_initialization', 'duration_ps': 0. if case.workflow == 'relax' else case.preparation.dynamics.T_ps},
                       {'operation': 'legacy_static', 'required': True, 'tolerance_Apm': case.preparation.tol_Apm}]
    if case.workflow != 'relax':
        operations += [{'operation': 'fresh_drive', 'clock': 'zero', 'D_P': 'zero', 'qualified_static_source_required': True}]
    return {'interface': 'legacy Case compatibility', 'configuration': asdict(case), 'operations': operations,
            'new_interface': 'fimrun.micromagnetics.Simulation',
            'legacy_defaults_retained': True, 'legacy_budgets_retained_only_here': True,
            'legacy_goal_none_still_analyzes': True}
