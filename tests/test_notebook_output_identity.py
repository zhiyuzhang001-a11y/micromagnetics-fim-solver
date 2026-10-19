"""Fresh-copy regression for the output adapter's first import identity."""
import json
from pathlib import Path
import subprocess
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]


class OutputIdentity(unittest.TestCase):
    def test_create_then_changed_output_source_requires_restart_without_reload(self):
        probe = r'''
from pathlib import Path
import hashlib,json,shutil,sys,tempfile
from unittest.mock import patch
root=Path(sys.argv[1]).resolve()
notebook=json.loads((root/'examples/notebook_single_sim.ipynb').read_text())
cell='import sys\nsys.path.insert(0, '+repr(str(root))+')\nfrom fimrun.notebook import NotebookSimulation, module_identity\nfrom fimrun.micromagnetics import *\n_boris_import_identity=module_identity('+repr(str(root))+')'
with tempfile.TemporaryDirectory() as folder:
    copied=Path(folder).resolve()/'source'
    shutil.copytree(root/'fimrun',copied/'fimrun',ignore=shutil.ignore_patterns('__pycache__'))
    (copied/'build-script-api').symlink_to(root/'build-script-api',target_is_directory=True)
    actual_cell=cell.replace(str(root),str(copied))
    namespace={}
    exec(compile(actual_cell,'actual-environment-cell','exec'),namespace)
    identity=namespace['_boris_import_identity']
    assert 'fimrun.notebook_output' in identity['modules'], 'adapter missing from first snapshot'
    module=sys.modules['fimrun.notebook_output']
    original_function=module.snapshot_format
    entry=dict(identity['modules']['fimrun.notebook_output'])
    from fimrun.micromagnetics.native import Native,EVALUATIONS
    with patch.object(Native,'__init__',side_effect=AssertionError('native construction forbidden')) as forbidden:
        exec("sub=Sublattice(Ms=3e5,alpha=.01,gamma_H=2e5)\n"
             "model=FiM(mesh=Grid(cells=(3,3,1),cell_size=(4e-9,4e-9,3e-9)),"
             "material=FiMMaterial(A=sub,B=sub),energy=(FiMAnisotropy(K1_A=1e4,K1_B=2e4),))\n"
             "initial=Antiparallel(Uniform((0.,0.,1.)))\n",namespace)
        sim=namespace['NotebookSimulation'](model=namespace['model'],initial=namespace['initial'],
                                           dt=1e-15,results=copied/'results')
        try:
            before=sim.m;run_id=sim.run_id
            path=copied/'fimrun/notebook_output.py'
            source=path.read_text()
            path.write_text(source.replace('def snapshot_format(value):'+chr(10),
                'def snapshot_format(value):'+chr(10)+"    raise RuntimeError('edited copied source only')"+chr(10),1))
            import ast
            function=next(node for node in ast.parse(path.read_text()).body
                          if isinstance(node,ast.FunctionDef) and node.name=='snapshot_format')
            edited={}
            exec(compile(ast.Module(body=[function],type_ignores=[]),'edited-function','exec'),edited)
            try:edited['snapshot_format']('ovf')
            except RuntimeError:pass
            else:raise AssertionError('copied disk function was not changed')
            disk_sha=hashlib.sha256(path.read_bytes()).hexdigest()
            assert disk_sha!=entry['sha256']
            try:sim.run(0.)
            except RuntimeError as error:
                assert 'kernel' in str(error).lower()
                message=str(error)
            else:raise AssertionError('edited output source accepted while cached code remains')
            assert namespace['_boris_import_identity']['modules']['fimrun.notebook_output']==entry
            assert module.snapshot_format is original_function and original_function('ovf')=='ovf'
            import numpy as np
            np.testing.assert_array_equal(sim.m,before)
            assert sim.run_id==run_id and sim.time==0. and not sim.closed
            assert dict(EVALUATIONS)=={'fm':0,'fim':0} and forbidden.call_count==0
            print(json.dumps({'status':'passed','first_snapshot_contains_output':True,
                'rerun_rejected':message,'frozen_sha256':entry['sha256'],'edited_copy_sha256':disk_sha,
                'live_function_unchanged':True,'sim_preserved':True,'fields':dict(EVALUATIONS)}))
        finally:sim.close()
'''
        result=subprocess.run([sys.executable,'-I','-c',probe,str(ROOT)],capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        proof=json.loads(result.stdout)
        self.assertEqual(proof['fields'],{'fm':0,'fim':0})
        self.assertTrue(proof['first_snapshot_contains_output'])
        self.assertTrue(proof['sim_preserved'])
        print(json.dumps(proof))
