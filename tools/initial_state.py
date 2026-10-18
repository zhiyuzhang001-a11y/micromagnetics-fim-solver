"""Compatibility entry; canonical helper lives in the installed package."""
from fimrun._support.initial_state import *
if __name__ == "__main__":
    import runpy
    runpy.run_module("fimrun._support.initial_state", run_name="__main__")
