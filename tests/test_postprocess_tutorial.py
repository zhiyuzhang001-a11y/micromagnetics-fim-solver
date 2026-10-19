"""Execute the real offline tutorial cells, never a kernel/server/native model."""
import ast
import contextlib
import io
import json
import os
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest.mock import patch
from fimrun.micromagnetics.native import Native, EVALUATIONS

ROOT = Path(__file__).resolve().parents[1]


def execute_cell(source, namespace):
    tree = ast.parse(source)
    if tree.body and isinstance(tree.body[-1], ast.Expr):
        exec(compile(ast.Module(body=tree.body[:-1], type_ignores=[]), 'tutorial-cell', 'exec'), namespace)
        return eval(compile(ast.Expression(tree.body[-1].value), 'tutorial-result', 'eval'), namespace)
    exec(compile(tree, 'tutorial-cell', 'exec'), namespace)


class Tutorial(unittest.TestCase):
    def test_real_offline_cells_and_mime(self):
        nb = json.loads((ROOT/'examples/notebook_skyrmion_postprocess.ipynb').read_text())
        namespace = {}; before = dict(EVALUATIONS)
        from IPython.core.interactiveshell import InteractiveShell
        with tempfile.TemporaryDirectory() as folder:
            previous = Path.cwd()
            try:
                os.chdir(folder)
                with patch.object(Native,'__init__',side_effect=AssertionError('Native forbidden')), patch.dict(os.environ,{'IPYTHONDIR':str(Path(folder)/'ipython')}), contextlib.redirect_stdout(io.StringIO()):
                    results = [execute_cell(''.join(c['source']), namespace) for c in nb['cells'] if c['cell_type']=='code']
                self.assertEqual(len(namespace['result'].rows),5)
                self.assertEqual(sum(r['valid_velocity'] for r in namespace['result'].rows),3)
                from IPython.display import HTML, SVG
                html = [r for r in results if isinstance(r,HTML)]
                svg = [r for r in results if isinstance(r,SVG)]
                self.assertGreaterEqual(len(html),3);self.assertGreaterEqual(len(svg),3)
                for result in html:
                    mime,_=InteractiveShell.instance().display_formatter.format(result)
                    self.assertIn('text/html',mime)
                for result in svg:
                    ET.fromstring(result.data)
                    mime,_=InteractiveShell.instance().display_formatter.format(result)
                    self.assertIn('image/svg+xml',mime)
                self.assertTrue((Path('new-skyrmion-example')/'new-analysis.csv').is_file())
                self.assertTrue((Path('new-skyrmion-example')/'center.svg').is_file())
                toy=next(c for c in nb['cells'] if c['id']=='toy')
                with self.assertRaises(FileExistsError): execute_cell(''.join(toy['source']),namespace)
            finally:
                os.chdir(previous)
        self.assertEqual(before,EVALUATIONS)

    def test_notebooks_syntax_and_no_user_display_loops(self):
        for name in ('notebook_single_sim.ipynb','notebook_skyrmion_postprocess.ipynb'):
            nb=json.loads((ROOT/'examples'/name).read_text())
            for cell in nb['cells']:
                if cell['cell_type']=='code':
                    tree=ast.parse(''.join(cell['source']))
                    self.assertFalse(any(isinstance(n,(ast.For,ast.While,ast.If)) for n in ast.walk(tree)))
                    self.assertEqual(cell['outputs'],[])
                    self.assertIsNone(cell['execution_count'])

    def test_simulation_imports_and_model_only(self):
        # Constructor calls core.check(), which needs the genuine native payload;
        # do not fabricate it or pretend scientific cells ran in a source clone.
        nb=json.loads((ROOT/'examples/notebook_single_sim.ipynb').read_text())
        before=dict(EVALUATIONS);namespace={}
        with patch.object(Native,'__init__',side_effect=AssertionError('Native forbidden')):
            for cell in nb['cells']:
                if cell['id'] in ('imports','model-code'):
                    execute_cell(''.join(cell['source']),namespace)
        self.assertIn('model',namespace);self.assertEqual(before,EVALUATIONS)
