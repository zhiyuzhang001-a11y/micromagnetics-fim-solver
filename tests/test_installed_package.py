import unittest,subprocess,sys,tempfile,shutil,json,os,socket,urllib.request
from pathlib import Path
from unittest.mock import patch
from fimrun import runtime
from fimrun.micromagnetics import Simulation
from fimrun.micromagnetics.native import Native,EVALUATIONS
class InstalledContract(unittest.TestCase):
 def test_provenance_and_legacy_refusal(self):
  report=runtime.doctor(native=True);self.assertTrue(Path(report['package_path']).is_relative_to(Path(sys.prefix)))
  from fimrun.bridge import legacy
  with self.assertRaisesRegex(RuntimeError,'Legacy Case'):legacy()
  self.assertIsNone(runtime.identity()['dirty'])
 def _copied_probe(self,code):
  with tempfile.TemporaryDirectory() as d:
   target=Path(d)/'fimrun';shutil.copytree(runtime.PACKAGE_ROOT,target,ignore=shutil.ignore_patterns('__pycache__'))
   command='import sys;sys.path.insert(0,'+repr(d)+');from pathlib import Path;from fimrun import runtime;'+code
   subprocess.run([sys.executable,'-I','-c',command],check=True,capture_output=True)
 def test_missing_resource_rejected(self):
  self._copied_probe("next((runtime.RESOURCE_ROOT/'build-script-api').glob('libfim*')).unlink();\ntry:runtime.ensure_integrity()\nexcept RuntimeError as e:assert 'missing or changed' in str(e)\nelse:raise AssertionError('tamper accepted')")
 def test_changed_source_stale_kernel_rejected(self):
  self._copied_probe("p=runtime.PACKAGE_ROOT/'notebook_output.py';p.write_text(p.read_text()+'\\n# test change\\n');\ntry:runtime.ensure_integrity()\nexcept RuntimeError as e:assert 'changed in this kernel' in str(e)\nelse:raise AssertionError('stale source accepted')")
 def test_preview_installed_assets_identity_and_port_conflict(self):
  from fimrun.micromagnetics.preview import LivePreview,ASSETS
  before=dict(EVALUATIONS)
  with patch.object(Native,'__init__',side_effect=AssertionError('zero field required')):
   s=Simulation.load_state(os.environ['FIMRUN_C4_TEST_STATE'])
   with socket.socket() as port:port.bind(('127.0.0.1',0));number=port.getsockname()[1]
   v=LivePreview(s,number)
   with patch('webbrowser.open') as browser:
    v.start();browser.assert_called_once()
   try:
    with urllib.request.urlopen(v.url) as response:self.assertEqual(response.read(),(ASSETS/'index.html').read_bytes())
    for path in ASSETS.rglob('*.js'):
     with urllib.request.urlopen('http://127.0.0.1:'+str(number)+'/'+str(path.relative_to(ASSETS))) as response:self.assertEqual(response.read(),path.read_bytes())
    with self.assertRaises(urllib.error.HTTPError):urllib.request.urlopen('http://127.0.0.1:'+str(number)+'/?run_id=wrong&instance=wrong')
    conflict=LivePreview(s,number)
    with self.assertWarns(RuntimeWarning),patch('webbrowser.open') as browser:conflict.start();browser.assert_not_called()
    self.assertIsNone(conflict.server)
   finally:v.close();s.close()
  self.assertEqual(before,EVALUATIONS)
