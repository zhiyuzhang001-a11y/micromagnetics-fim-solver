"""Compatibility entry; canonical helper lives in the installed package."""
from fimrun._support.contour_geometry import *
if __name__ == "__main__":
    import runpy
    runpy.run_module("fimrun._support.contour_geometry", run_name="__main__")
