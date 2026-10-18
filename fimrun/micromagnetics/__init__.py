"""Sequential SI micromagnetics; legacy Case remains in fimrun unchanged."""
from .model import (Grid, Sublattice, FMMaterial, FiMMaterial, FM, FiM, Exchange,
                    FiMExchange, OnsiteCoupling, DMI, UniaxialAnisotropy,
                    FiMAnisotropy, Demag, Zeeman, FiMSOT)
from .initial import Magnetization, Uniform, Smooth, Skyrmion, OVF, Antiparallel, LegacyFixture
from .simulation import Simulation, RK4, Outputs, MaxTransverseField, RunResult
from .persistence import read_segments
from .stages import Evolve, Relax, SetField, SetCurrent, SetSolver, SetOutputs, SaveState
from .reference import parameters
from .script import run_script, check_stages, run_directory
