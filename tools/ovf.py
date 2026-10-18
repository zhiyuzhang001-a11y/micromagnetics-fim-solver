"""Compatibility entry; canonical helper lives in the installed package."""
from fimrun._support.ovf import *
if __name__ == "__main__":
    import runpy
    runpy.run_module("fimrun._support.ovf", run_name="__main__")
