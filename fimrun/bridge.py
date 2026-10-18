"""Lazy bridge to unchanged legacy modules; never constructs a Model on import."""
from pathlib import Path
import importlib
import sys

ROOT = Path(__file__).resolve().parents[1]
def legacy():
    if not (ROOT/'tools').is_dir():
        raise RuntimeError('Legacy Case execution requires its retained source environment; installed release supports the sequential API. No science was started.')
    # Internal module search only, not a cwd/environment/global application setting.
    tools = str(ROOT / 'tools')
    if tools not in sys.path:
        sys.path.insert(0, tools)
    return {name: importlib.import_module(name) for name in
            ('user_case', 'current_case', 'kernel_cache', 'user_costs',
             'run_user_workflow', 'run_current_workflow')}
