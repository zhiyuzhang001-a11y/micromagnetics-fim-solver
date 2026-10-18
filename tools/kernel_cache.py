"""Compatibility entry; canonical helper lives in the installed package."""
from fimrun._support.kernel_cache import *
if __name__ == "__main__":
    import runpy
    runpy.run_module("fimrun._support.kernel_cache", run_name="__main__")
