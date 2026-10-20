"""Zero-native regression: user-visible Notebook errors contain recovery paths."""
import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import numpy as np
from IPython.core.interactiveshell import InteractiveShell
from fimrun.notebook import NotebookSimulation,CellStopped
from fimrun.micromagnetics import Simulation,Antiparallel,Uniform
from fimrun.micromagnetics.native import Native,EVALUATIONS
from test_notebook_usability import model


class RecoveryVisibility(unittest.TestCase):
    def check_fault(self,mode):
        before=dict(EVALUATIONS)
        with tempfile.TemporaryDirectory() as folder,patch.object(Native,'__init__',side_effect=AssertionError('native construction forbidden')):
            root=Path(folder).resolve()
            sim=NotebookSimulation(model=model(),initial=Antiparallel(Uniform((0.,0.,1.))),dt=1e-15,output_dir=root)
            core=sim._session.sim
            core._field=np.zeros_like(core._m);core._energy=np.zeros(2)
            reason='injected '+mode+' disk failure'
            target=('fimrun.micromagnetics.persistence.export_ovf' if mode=='final-OVF' else 'fimrun.notebook_flat.publish_exclusive')
            sentinel=[]
            def operation():
                sim.run(0.)
                sentinel.append('must not execute')
            shell=InteractiveShell();shell.user_ns['operation']=operation
            output=io.StringIO()
            try:
                with patch(target,side_effect=OSError(reason)),contextlib.redirect_stdout(output),contextlib.redirect_stderr(output):
                    result=shell.run_cell('operation()',store_history=False)
                error=result.error_in_exec
                self.assertIsInstance(error,CellStopped)
                self.assertEqual(sentinel,[])
                states=list(root.glob('experiment-running-*/experiment.state'))
                self.assertEqual(len(states),1)
                state=states[0];location=state if mode=='final-OVF' else state.parent
                for visible in (str(error),'\n'.join(error._render_traceback_()),output.getvalue()):
                    self.assertIn(reason,visible)
                    self.assertIn(str(location),visible)
                self.assertIn('"error":',output.getvalue())
                restored=Simulation.load_state(state)
                np.testing.assert_array_equal(restored.m,sim.m)
                self.assertEqual(restored.time,sim.time);restored.close()
                self.assertEqual(before,EVALUATIONS)
                print(json.dumps({'mode':mode,'status':'passed','visible_error':str(error),
                    'IPython_output':output.getvalue(),'recovery_exists_and_load_exact':True,'native_constructor_forbidden':True,'fields':dict(EVALUATIONS)}))
            finally:
                sim.close()
                shell.clear_instance()
    def test_final_ovf_failure_visible_and_stops_queue(self):self.check_fault('final-OVF')
    def test_publication_failure_visible_and_stops_queue(self):self.check_fault('publication')
