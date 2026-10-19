"""Regression for the finite user-visible documentation review scope."""
from pathlib import Path
import re
import unittest
ROOT=Path(__file__).resolve().parents[1]

class Documentation(unittest.TestCase):
    def test_historical_entry_banners(self):
        for name in ('MODEL_AND_UNITS.md','NUMERICAL_GUIDE.md','CURRENT_SOT_WORKFLOW.md','MIRROR_TRUNCATION.md','REPRESENTATIVE_WORKFLOW.md','DYNAMIC_TO_STATIC.md','USER_SCRIPT_WORKFLOW.md','LOCAL_DELIVERY_STATUS.md'):
            text=(ROOT/'docs'/name).read_text()
            self.assertRegex(text[:650],r'Historical fixed-tool evidence|\u5386\u53f2\u56fa\u5b9a\u5de5\u5177\u4e0e\u8bc1\u636e')
            self.assertIn('notebook_single_sim.ipynb',text[:650])

    def test_reviewed_formula_tokens_are_math_delimited(self):
        for name in ('docs/MODEL_AND_UNITS.md','docs/NUMERICAL_GUIDE.md','docs/CURRENT_SOT_WORKFLOW.md','docs/interface-v01/PARAMETERS.md','docs/interface-v01/SKYRMION_POSTPROCESSING.md','docs/USER_SCRIPT_WORKFLOW.md','docs/REPRESENTATIVE_WORKFLOW.md','docs/DYNAMIC_TO_STATIC.md'):
            text=(ROOT/name).read_text()
            self.assertNotIn('sqrt(A/pi)',text);self.assertNotIn('a,b=2sqrt',text)
            self.assertNotIn('unwrapped=wrapped+image*L',text)
            self.assertNotIn('`E=V/(2h',text)
            self.assertNotIn('sqrt(1-a',text)
            self.assertNotIn('$$\u3002',text)
            self.assertEqual(text.count('```')%2,0,name)
        sot=(ROOT/'docs/CURRENT_SOT_WORKFLOW.md').read_text()
        self.assertNotIn('## \u53ef\u76f4\u63a5\u8fd0\u884c\u7684\u4e2d\u6587\u4f8b\u5b50',sot)
        self.assertIn('\u5386\u53f2CLI\u590d\u73b0',sot)
        self.assertGreater(sot.count('$$'),5)

    def test_reference_current_precedes_inherited(self):
        text=(ROOT/'docs/API_REFERENCE.md').read_text()
        self.assertLess(text.index('### NotebookSimulation \u2014 current API1.4'),text.index('### Inherited public members from the compatibility parent'))
        self.assertIn('None; exactly one of size/cells',text)
        self.assertIn('Public orchestration function semantics',text)
