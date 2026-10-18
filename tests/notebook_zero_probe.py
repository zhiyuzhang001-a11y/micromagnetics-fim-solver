"""Fresh interpreter identity/Run All probes; no server or native evaluation."""
import contextlib
import io
import json
from pathlib import Path
import shutil
import sys
import tempfile
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
cells = [''.join(c['source']) for c in json.loads((ROOT/'my_case.ipynb').read_text())['cells'] if c['cell_type']=='code']
mode = sys.argv[1]
namespace = {}


def reject():
    try:
        exec(compile(cells[0], 'identity-cell', 'exec'), namespace)
    except RuntimeError as error:
        assert 'restart kernel' in str(error).lower(), str(error)
    else:
        raise AssertionError('Unverified imported cache accepted')


with tempfile.TemporaryDirectory() as folder:
    if mode in ('foreign-cache', 'source-priority'):
        foreign = (Path(folder)/'foreign').resolve()
        shutil.copytree(ROOT/'fimrun',foreign/'fimrun',ignore=shutil.ignore_patterns('__pycache__'))
        sys.path[:] = [str(foreign),str(ROOT)] + [p for p in sys.path if p != str(ROOT)]
    else:
        sys.path.insert(0,str(ROOT))
    if mode in ('foreign-cache','same-path-cache'):
        import fimrun.micromagnetics
        actual = Path(fimrun.micromagnetics.__file__).resolve()
        if mode=='foreign-cache':assert actual.is_relative_to(foreign)
        reject()
        assert 'sim' not in namespace
    else:
        exec(compile(cells[0], 'identity-cell', 'exec'), namespace)
        identity = namespace['_boris_import_identity']
        assert identity['Simulation'] == str(ROOT/'fimrun/micromagnetics/simulation.py')
        assert identity['NotebookSession'] == str(ROOT/'fimrun/notebook.py')
        assert identity['notebook_api']=='1.1'
        for name,entry in identity['modules'].items():
            assert Path(entry['file']).is_relative_to(ROOT)
        if mode=='changed-cache':
            identity['modules']['fimrun']['sha256']='changed'
            reject()
        if mode=='source-priority':assert sys.path[0]==str(ROOT)
    from fimrun.micromagnetics.native import Native, EVALUATIONS
    if mode=='run-all':
        import numpy as np
        with patch.object(Native,'__init__',side_effect=AssertionError('native work forbidden')), \
             patch('fimrun.notebook.run_directory',return_value=Path(folder)/'fresh'), \
             patch('fimrun.micromagnetics.preview.LivePreview.start'), \
             contextlib.redirect_stdout(io.StringIO()):
            for cell in cells:exec(compile(cell,'delivered-notebook','exec'),namespace)
            sim=namespace['sim'];before=sim.m
            try:
                try:
                    for cell in cells:exec(compile(cell,'delivered-notebook','exec'),namespace)
                except RuntimeError:pass
                else:raise AssertionError('Repeated creation accepted')
                assert namespace['sim'] is sim
                np.testing.assert_array_equal(sim.m,before)
                assert sim.time==0.
                assert sim.metrics()['fields']==sim.metrics()['analysis_calls']==sim.metrics()['snapshot_writes']==0
                session=namespace.pop('session')
                try:exec(compile(cells[2],'new-session','exec'),namespace)
                except RuntimeError:pass
                else:raise AssertionError('Independent sim overwritten')
                assert namespace['sim'] is sim
            finally:session.close()
    assert dict(EVALUATIONS)=={'fm':0,'fim':0},dict(EVALUATIONS)
    print(json.dumps({'mode':mode,'fields':dict(EVALUATIONS),'status':'passed'}))
