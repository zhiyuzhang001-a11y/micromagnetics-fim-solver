"""Cloud runner only: execute public tests, preserve every failure/skip report."""
from pathlib import Path
import argparse,subprocess,sys,json,os
root=Path(__file__).resolve().parents[2];out=root/'ci-results';out.mkdir(exist_ok=True)
p=argparse.ArgumentParser();p.add_argument('mode',choices=('quick','mac-zero','full'));a=p.parse_args()
quick=['test_three_issues','test_axis_wrap_revision','test_progress_revision','test_notebook_v14','test_notebook_simple.ZeroSimple','test_notebook_save_names','test_notebook_output_identity','test_postprocess_analysis','test_postprocess_review','test_postprocess_failures','test_postprocess_tutorial','test_viewer_ui_contract','test_postprocess_documentation']
mac_zero=['test_three_issues','test_progress_revision','test_notebook_v14','test_notebook_simple.ZeroSimple','test_notebook_save_names','test_notebook_output_identity']
quick=[m for m in quick if m not in mac_zero]
modules=(quick if a.mode=='quick' else mac_zero) if a.mode!='full' else [x.stem for x in sorted((root/'tests').glob('test_*.py')) if x.stem!='test_installed_package']+['static_stop_policy']
reports=[]
for module in modules:
 target=out/(module.replace('.','_')+'.json');command=[sys.executable,'-I',str(root/'tools/ci/test_process.py'),module,'--out',str(target)]
 if a.mode!='full':command+=['--zero']
 with (out/(module+'.log')).open('w') as f:
  try:r=subprocess.run(command,cwd=root,stdout=f,stderr=subprocess.STDOUT,timeout=300);code=r.returncode
  except subprocess.TimeoutExpired:code=124
 report=json.loads(target.read_text()) if target.exists() else dict(module=module,passed=False,tests=0,errors=[dict(reason='process failed/timed out; inspect log',exit=code)],failures=[],skipped=[])
 reports.append(report);print(module,'PASS' if report['passed'] else 'FAIL',report['tests'],flush=True)
if a.mode=='full':
 scripts=[['tests/build_backend.py'],['tests/current_contract.py'],['tests/smoke.py','--bins','build','--work','ci-results/smoke'],['tests/cpu_backend.py','--serial-bins','build-serial','--two-owner-bins','build','--work','ci-results/cpu'],['tests/current_sot.py','--out','ci-results/sot-scalar','--mode','scalar'],['tests/user_workflow.py','--out','ci-results/user-contract','--bins','build','--mode','contract'],['tests/user_workflow.py','--out','ci-results/user-small','--bins','build','--serial-bins','build-serial','--mode','small'],['tests/user_workflow.py','--out','ci-results/user-interrupted','--bins','build','--mode','interrupted'],['tests/check_postprocess_calibration.py','ci-results/calibration'],['tests/check_postprocess_rectangular.py','ci-results/rectangular.json']]
 for i,args in enumerate(scripts):
  with (out/f'script-{i}.log').open('w') as f:
   try:code=subprocess.run([sys.executable,*args],cwd=root,stdout=f,stderr=subprocess.STDOUT,timeout=300).returncode
   except subprocess.TimeoutExpired:code=124
  reports.append(dict(module=' '.join(args),passed=code==0,exit=code,tests=None,skipped=[]));print(args[0],code,flush=True)
summary=dict(mode=a.mode,passed=all(r['passed'] for r in reports),unit_tests=sum(r.get('tests') or 0 for r in reports),skipped=[s for r in reports for s in r.get('skipped',[])],reports=reports,not_covered=['native VSCode/Tk foreground interaction','private OVF/archive comparisons','long production campaigns and hardware performance qualification'])
(out/(a.mode+'-summary.json')).write_text(json.dumps(summary,indent=2)+'\n')
print(json.dumps({k:v for k,v in summary.items() if k!='reports'}));raise SystemExit(not summary['passed'])
