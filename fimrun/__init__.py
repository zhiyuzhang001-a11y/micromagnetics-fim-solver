"""Typed, opt-in orchestration; importing this package starts no processes."""
from .api import (AB, Vec3, Material, Mesh, Field, Initial, Dynamics, Preparation,
                  Drive, PreparedState, Runtime, Budget, Output, Preview, Case)

def run(case: Case, *, script: str) -> None:
    """Run once from __main__; --check performs only managed zero-Model preflight."""
    from .engine import cli
    cli(case, script=script)

from .legacy import describe_legacy
