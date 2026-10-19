"""Report real unittest outcomes and field counters, including failures and skips."""
from pathlib import Path
import argparse,sys,json,unittest
from unittest.mock import patch
p=argparse.ArgumentParser();p.add_argument('module');p.add_argument('--out',required=True);p.add_argument('--zero',action='store_true');p.add_argument('--installed',action='store_true');a=p.parse_args()
root=Path(__file__).resolve().parents[2]
if not a.installed:sys.path.insert(0,str(root))
sys.path.insert(0,str(root/'tests'))
from fimrun.micromagnetics.native import Native,EVALUATIONS
from fimrun.runtime import PACKAGE_ROOT
if a.installed:assert PACKAGE_ROOT.is_relative_to(Path(sys.prefix)),PACKAGE_ROOT
suite=unittest.defaultTestLoader.loadTestsFromName(a.module)
if a.zero:
 with patch.object(Native,'__init__',side_effect=AssertionError('zero CI forbids Native')),patch.object(Native,'evaluate',side_effect=AssertionError('zero CI forbids fields')):
  result=unittest.TextTestRunner(verbosity=2).run(suite)
else:result=unittest.TextTestRunner(verbosity=2).run(suite)
report=dict(module=a.module,passed=result.wasSuccessful(),tests=result.testsRun,failures=[dict(test=str(t),trace=trace) for t,trace in result.failures],errors=[dict(test=str(t),trace=trace) for t,trace in result.errors],skipped=[dict(test=str(t),reason=reason) for t,reason in result.skipped],fields=dict(EVALUATIONS),package=str(PACKAGE_ROOT),zero_guard=a.zero)
if a.zero:assert sum(EVALUATIONS.values())==0
Path(a.out).write_text(json.dumps(report,indent=2)+'\n');raise SystemExit(not result.wasSuccessful())
