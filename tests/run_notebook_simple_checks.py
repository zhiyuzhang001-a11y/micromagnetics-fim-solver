"""Run isolated facade checks and record every native evaluation attempt.

Run with the notebook-env interpreter; --phase zero/finite/tutorial/restart.
A native allowance bounds this invocation only, not the public simulation API.
"""
import argparse
import ast
import contextlib
import datetime
import hashlib
import io
import json
from pathlib import Path
import re
import sys
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
sys.path.insert(0,str(ROOT/'tests'))
parser=argparse.ArgumentParser()
parser.add_argument('--phase',choices=('zero','finite','tutorial','restart','replacement-zero','replacement-finite'),required=True)
parser.add_argument('--out',type=Path,required=True)
parser.add_argument('--allowance',type=int,default=160)
args=parser.parse_args()
args.out=args.out.resolve();args.out.mkdir(parents=True,exist_ok=True)
started={'fm':0,'fim':0}
namespace={}
notebook=json.loads((ROOT/'examples/notebook_single_sim.ipynb').read_text())
by={cell['id']:''.join(cell['source']) for cell in notebook['cells']}
# The identity cell must run before any fimrun imports in a fresh interpreter.
if args.phase in ('tutorial','restart'):
    exec(compile(by['environment'],'tutorial:environment','exec'),namespace)
from fimrun.micromagnetics.native import Native,EVALUATIONS
original=Native.evaluate

def evaluate(engine,m):
    if sum(started.values())>=args.allowance:
        raise RuntimeError('isolated smoke allowance reached; inspect before another attempt')
    started[engine.kind]+=1
    return original(engine,m)

def python_block(text):
    return re.search(r'```python\n(.*?)```',text,re.S).group(1)

stdout,stderr=io.StringIO(),io.StringIO()
status='failed';details={}
try:
    with contextlib.redirect_stdout(stdout),contextlib.redirect_stderr(stderr),patch.object(Native,'evaluate',evaluate):
        if args.phase in ('zero','finite','replacement-zero','replacement-finite'):
            import test_notebook_simple as simple
            if args.phase.startswith('replacement'):
                import test_notebook_replace_ovf as revised
                chosen=revised.ZeroReplacementOVF if args.phase=='replacement-zero' else revised.FiniteReplacementOVF
                suite=unittest.defaultTestLoader.loadTestsFromTestCase(chosen)
            elif args.phase=='zero':
                import test_notebook as old
                suite=unittest.TestSuite([unittest.defaultTestLoader.loadTestsFromTestCase(simple.ZeroSimple)])
                for name in ('test_summary_raises_and_control_sequence_cannot_reach_sentinel',
                             'test_initial_save_restore_and_repeated_create_guard',
                             'test_save_new_never_overwrites_or_escapes_and_handles_competing_file'):
                    suite.addTest(old.ZeroNotebook(name))
            else:suite=unittest.defaultTestLoader.loadTestsFromTestCase(simple.FiniteSimple)
            result=unittest.TextTestRunner(verbosity=2,stream=stderr).run(suite)
            details={'tests':result.testsRun,'failures':len(result.failures),'errors':len(result.errors)}
            if not result.wasSuccessful():raise AssertionError('directed tests failed')
        else:
            def start(display):display.server=object()
            def close(display):display.server=None
            with patch('fimrun.micromagnetics.preview.LivePreview.start',start),patch('fimrun.micromagnetics.preview.LivePreview.close',close):
                import numpy as np
                if args.phase=='tutorial':
                    notes=[]
                    for cell in notebook['cells']:
                        if cell['cell_type']!='code' or cell['id']=='environment':continue
                        exec(compile(''.join(cell['source']),'tutorial:'+cell['id'],'exec'),namespace)
                        if cell['id']=='model':namespace['results']=args.out/'tutorial-results'
                        sim=namespace.get('sim')
                        if sim is not None:notes.append({'cell':cell['id'],'time':sim.time,'run_id':sim.run_id,'closed':sim.closed})
                        if cell['id']=='save':
                            state=Path(namespace['saved']['path'])
                            np.savez(args.out/'expected.npz',m=sim.m,time=sim.time,D=sim.dissipation,P=sim.drive_work)
                    sim=namespace['sim'];assert not sim.closed
                    identity=sim.run_id;viewer=sim._session.sim._preview
                    assert sim.time==2e-15
                    # The exact dt example from the adjacent tutorial Markdown.
                    example=re.search(r'sim\.run\(2e-15, dt=0\.5e-15\)',by['run-help']).group(0)
                    exec(example,namespace);assert sim.dt==0.5e-15
                    exec(python_block(by['optional-current']),namespace)
                    assert sim.run_id==identity and sim._session.sim._preview is viewer
                    current=sim.m.copy();clock=sim.time
                    try:sim.relax(1.)
                    except ValueError:pass
                    else:raise AssertionError('static silently disabled current')
                    np.testing.assert_array_equal(sim.m,current);assert sim.time==clock
                    sim.set_current(None)
                    assert sim._session.sim.current is None
                    saved_m=sim.m
                    from fimrun.micromagnetics.initial import generate
                    model=namespace['model']
                    np.testing.assert_array_equal(generate(model,{'A':saved_m[0],'B':saved_m[1]}),saved_m)
                    try:generate(model,saved_m)
                    except ValueError:pass
                    else:raise AssertionError('combined FiM array wrongly accepted')
                    exec(python_block(by['close-help']),namespace)
                    assert sim.closed and viewer.server is None
                    details={'main_cells':notes,'optional_SOT_executed':True,'dt_example':example,
                             'manual_close_executed':True,'state_path':str(state),'final_time_s':clock,
                             'actual_viewer':'deterministic substitute; no HTTP/browser',
                             'state_sha256':hashlib.sha256(state.read_bytes()).hexdigest()}
                    (args.out/'TUTORIAL_STATE.json').write_text(json.dumps(details,indent=2)+'\n')
                else:
                    assert 'sim' not in namespace and 'saved' not in namespace and 'model' not in namespace
                    exec(python_block(by['restart-example']),namespace)
                    sim=namespace['sim']
                    try:
                        expected=np.load(args.out/'expected.npz')
                        np.testing.assert_array_equal(sim.m,expected['m'])
                        np.testing.assert_array_equal(sim.dissipation,expected['D'])
                        np.testing.assert_array_equal(sim.drive_work,expected['P'])
                        assert sim.time==float(expected['time'])
                        details={'fresh_interpreter_restore':'exact m/time/D/P','state_path':str(namespace['state_path']),
                                 'new_directory':str(sim.directory),'actual_VS_Code_Restart':False}
                    finally:sim.close()
        status='passed'
except BaseException:
    import traceback
    traceback.print_exc(file=stderr)
finally:
    # A failed test must not leave a facade, viewer or native model owned by us.
    from fimrun.notebook import _ACTIVE_NOTEBOOKS
    for sim in list(_ACTIVE_NOTEBOOKS.values()):
        try:sim.close()
        except Exception:
            import traceback
            traceback.print_exc(file=stderr)
    index=len(list(args.out.glob('attempt-*.json')))+1
    prefix=args.out/f'attempt-{index:02d}-{args.phase}'
    Path(str(prefix)+'.stdout.txt').write_text(stdout.getvalue())
    Path(str(prefix)+'.stderr.txt').write_text(stderr.getvalue())
    value={'recorded_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'phase':args.phase,
           'status':status,'native_started_fields':started,'successful_evaluations':dict(EVALUATIONS),
           'allowance_this_attempt':args.allowance,'details':details,
           'stdout_sha256':hashlib.sha256(stdout.getvalue().encode()).hexdigest(),
           'stderr_sha256':hashlib.sha256(stderr.getvalue().encode()).hexdigest()}
    Path(str(prefix)+'.json').write_text(json.dumps(value,indent=2)+'\n')
    print(json.dumps(value));print(stderr.getvalue(),file=sys.stderr)
if status!='passed':sys.exit(1)
