"""Inert descriptions; execution is explicit and uses the sequential operations."""
from dataclasses import dataclass
from pathlib import Path
from .simulation import MaxTransverseField, RK4, Outputs
from .model import FiMSOT


@dataclass(frozen=True, kw_only=True)
class Evolve:
    duration: float

    def execute(self, sim):
        return sim.run(duration=self.duration)


@dataclass(frozen=True, kw_only=True)
class Relax:
    stop: MaxTransverseField
    method: str = 'sdesc'

    def execute(self, sim):
        return sim.relax(method=self.method, stop=self.stop)


@dataclass(frozen=True, kw_only=True)
class SetField:
    H_ext: tuple | None = None
    B_ext: tuple | None = None

    def execute(self, sim):
        return sim.set_field(H_ext=self.H_ext, B_ext=self.B_ext)


@dataclass(frozen=True)
class SetCurrent:
    current: FiMSOT | None

    def execute(self, sim):
        return sim.set_current(self.current)


@dataclass(frozen=True)
class SetSolver:
    solver: RK4

    def execute(self, sim):
        return sim.set_solver(self.solver)


@dataclass(frozen=True)
class SetOutputs:
    outputs: Outputs

    def execute(self, sim):
        return sim.set_outputs(self.outputs)


@dataclass(frozen=True)
class SaveState:
    path: str | Path
    strict: bool = False

    def execute(self, sim):
        return sim.save_checkpoint(self.path) if self.strict else sim.save_state(self.path)
