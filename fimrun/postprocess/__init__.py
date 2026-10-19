"""Opt-in, read-only scientific postprocessing; never a solver operation."""
from .pipeline import analyze_ovf,frames_from_state
from .io import read_ovf
from .calibration import calibrate
from .plotting import summary_svg
from .demo import generate as generate_demo
__all__=['analyze_ovf','frames_from_state','read_ovf','calibrate','summary_svg','generate_demo']

from .analysis import analyze, Analysis
__all__ += ["analyze", "Analysis"]
