"""Execute the actual new notebook cells, default and explicit synthetic path."""
import contextlib,io,json,os,tempfile,unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest.mock import patch
from fimrun.micromagnetics.native import Native,EVALUATIONS

ROOT=Path(__file__).resolve().parents[1]

class Tutorial(unittest.TestCase):
    def execute(self,synthetic):
        nb=json.loads((ROOT/'examples/notebook_skyrmion_postprocess.ipynb').read_text());namespace={};before=dict(EVALUATIONS)
        with tempfile.TemporaryDirectory() as folder:
            previous=Path.cwd()
            try:
                os.chdir(folder)
                with patch.object(Native,'__init__',side_effect=AssertionError('Native forbidden')),patch('IPython.display.display') as shown,patch.dict(os.environ,{'IPYTHONDIR':str(Path(folder)/'ipython-profile')}),contextlib.redirect_stdout(io.StringIO()):
                    for cell in nb['cells']:
                        if cell['cell_type']!='code':continue
                        code=''.join(cell['source'])
                        if synthetic and cell['id']=='toy':code=code.replace('generate_example = False','generate_example = True')
                        exec(compile(code,cell['id'],'exec'),namespace)
                self.assertEqual(before,EVALUATIONS)
                if synthetic:
                    self.assertEqual(len(namespace['rows']),5)
                    self.assertEqual(sum(r['valid_velocity'] for r in namespace['rows']),3)
                    self.assertTrue((namespace['example_dir']/'analysis.csv').is_file())
                    svg=namespace['analysis_svg'];tree=ET.fromstring(svg)
                    ns={'s':'http://www.w3.org/2000/svg'}
                    self.assertEqual(len(tree.findall('.//s:circle',ns)),40)
                    from IPython.display import SVG
                    objects=[c.args[0] for c in shown.call_args_list if c.args and isinstance(c.args[0],SVG)]
                    self.assertEqual(len(objects),1);self.assertEqual(objects[0]._repr_svg_(),svg)
                    from IPython.core.interactiveshell import InteractiveShell
                    mime,_=InteractiveShell.instance().display_formatter.format(objects[0])
                    self.assertEqual(mime['image/svg+xml'],svg)
                else:self.assertEqual(list(Path(folder).iterdir()),[])
            finally:os.chdir(previous)
    def test_default_no_outputs(self):self.execute(False)
    def test_selected_synthetic_zero_native(self):self.execute(True)
    def test_static_svg_cell_zero_native(self):
        import test_skyrmion_postprocess as support
        from fimrun.postprocess import analyze_ovf
        fixture=support.Offline();fixture.setUp()
        try:
            rows=analyze_ovf(fixture.frames(stage='sdesc'),fixture.root/'static-svg.csv',calibration=support.CAL)
            nb=json.loads((ROOT/'examples/notebook_skyrmion_postprocess.ipynb').read_text())
            cell=next(c for c in nb['cells'] if c['id']=='plots');namespace={'rows':rows}
            with patch('IPython.display.display') as shown:
                exec(compile(''.join(cell['source']),'actual-static-svg-cell','exec'),namespace)
            svg=shown.call_args.args[0]._repr_svg_();tree=ET.fromstring(svg);ns={'s':'http://www.w3.org/2000/svg'}
            self.assertIn('accepted iteration',svg);self.assertIn('wrapped points',svg)
            self.assertEqual(len([e for e in tree.findall('.//s:circle',ns) if e.get('data-panel')=='0']),10)
            self.assertTrue(all(not r['valid_velocity'] for r in rows))
        finally:fixture.tearDown()
