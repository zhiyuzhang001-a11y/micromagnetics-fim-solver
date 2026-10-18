"""Compatibility entry; canonical helper lives in the installed package."""
from fimrun._support.user_case import *
if __name__ == "__main__":
    import runpy
    runpy.run_module("fimrun._support.user_case", run_name="__main__")
