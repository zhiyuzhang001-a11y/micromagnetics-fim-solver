"""GPL-3.0-only. Small typed configuration API; importing it performs no work."""
from dataclasses import dataclass, field as dc_field
from pathlib import Path
from typing import Literal

Vec3 = tuple[float, float, float]
AB = tuple[float, float]

@dataclass(frozen=True, kw_only=True)
class Material:
    """Physical parameters, A/B order. Changing them requires new qualification."""
    Ms_Apm: AB = (300000., 600000.)
    A_Jpm: AB = (5e-12, 5e-12)
    Ah_Jpm3: float = -8e6
    Anh_Jpm: float = -5e-12
    D_Jpm2: AB = (.00105, .00105)
    K1_Jpm3: AB = (109000., 109000.)
    K2_Jpm3: AB = (0., 0.)
    axes: tuple[Vec3, Vec3] = ((0., 0., 1.), (0., 0., 1.))
    alpha: AB = (.01, .01)
    gamma_H_m_per_As: AB = (221276.1569, 221276.1569)
    active: tuple[int, int, int, int] = (1, 1, 1, 1)

@dataclass(frozen=True, kw_only=True)
class Mesh:
    """n: integer cell counts; cell_nm: nm. Box size is derived, never rounded."""
    n: tuple[int, int, int] = (125, 125, 1)
    cell_nm: Vec3 = (4., 4., 3.)
    pbc: tuple[int, int, int] = (1, 1, 0)
    mirrors: tuple[int, int] = (10, 10)
    origin_nm: Vec3 = (0., 0., 0.)

@dataclass(frozen=True, kw_only=True)
class Field:
    """Supply exactly one: H_Apm [A/m], or mu0_H_T [tesla]."""
    H_Apm: Vec3 | None = None
    mu0_H_T: Vec3 | None = None

@dataclass(frozen=True, kw_only=True)
class Initial:
    """Preparation guess only. OVF requires separate A/B files; not an equilibrium."""
    kind: Literal['canonical_legacy', 'uniform', 'smooth', 'skyrmion', 'ovf2'] = 'canonical_legacy'
    A: Vec3 = (0., 0., 1.)
    B: Vec3 = (0., 0., -1.)
    relation: Literal['antiparallel', 'independent'] = 'antiparallel'
    amplitude: float = .01
    center_nm: tuple[float, float] = (200., 300.)
    radius_nm: float = 25.
    wall_nm: float = 8.
    helicity_rad: float = 0.
    polarity: int = -1
    ovf_A: str | Path = ''
    ovf_B: str | Path = ''
    interpretation: Literal['direction', 'magnetization_Apm'] = 'direction'

@dataclass(frozen=True, kw_only=True)
class Dynamics:
    """Numerics: dt_fs [fs]; physical end time T_ps [ps]. No automatic dt/2."""
    dt_fs: float
    T_ps: float

@dataclass(frozen=True, kw_only=True)
class Preparation:
    """Explicit pre-dynamics then static. 1 A/m is this example's engineering gate."""
    dynamics: Dynamics = dc_field(default_factory=lambda: Dynamics(dt_fs=100., T_ps=500.))
    tol_Apm: float = 1.
    max_updates: int = 30000

@dataclass(frozen=True, kw_only=True)
class Drive:
    """Constant in-plane conventional J [A/m²]; independent dimensionless A/B xi,r."""
    dynamics: Dynamics = dc_field(default_factory=lambda: Dynamics(dt_fs=25., T_ps=2.))
    Jc_Apm2: Vec3 = (1e11, 0., 0.)
    incident_direction: Vec3 = (0., 0., 1.)
    xi: AB = (.1, .1)
    field_like_ratio: AB = (0., 0.)
    times_ps: tuple[float, ...] = (0., 2.)

@dataclass(frozen=True, kw_only=True)
class PreparedState:
    """Existing completed preparation report.json; CP, metadata and ledger are bound."""
    report: str | Path

@dataclass(frozen=True, kw_only=True)
class Runtime:
    """Paths relative to the user script. No automatic build or kernel generation."""
    bins: str | Path = 'build-unified'
    cache: str | Path = 'output/kernel-cache'

@dataclass(frozen=True, kw_only=True)
class Budget:
    """NEW complete fields for the whole chain; wall includes IO and stage transitions."""
    new_fields: int = 100000
    wall_s: float = 600.
    rss_bytes: int = 2147483648
    output_bytes: int = 1073741824

@dataclass(frozen=True, kw_only=True)
class Output:
    """New directory only; no implicit overwrite/resume. Sampling counts accepted steps."""
    directory: str | Path
    save_every: int = 100
    heartbeat_s: float = 2.
    goal: Literal['none', 'observe', 'single_skyrmion'] = 'observe'

@dataclass(frozen=True, kw_only=True)
class Preview:
    """Optional read-only protocol-v1 viewer. Port conflict never reuses another run."""
    enabled: bool = False
    command: tuple[str, ...] = ()
    port: int = 8766
    startup_s: float = 3.
    max_rss_bytes: int = 268435456
    log_bytes: int = 65536 # reserved before science; bounded combined stdout/stderr
    open_browser: bool = True

@dataclass(frozen=True, kw_only=True)
class Case:
    workflow: Literal['relax', 'prepare_then_drive', 'drive']
    output: Output
    material: Material = dc_field(default_factory=Material)
    mesh: Mesh = dc_field(default_factory=Mesh)
    field: Field = dc_field(default_factory=lambda: Field(mu0_H_T=(0., 0., -.002)))
    initial: Initial = dc_field(default_factory=Initial)
    preparation: Preparation = dc_field(default_factory=Preparation)
    drive: Drive = dc_field(default_factory=Drive)
    prepared: PreparedState | None = None
    runtime: Runtime = dc_field(default_factory=Runtime)
    budget: Budget = dc_field(default_factory=Budget)
    preview: Preview = dc_field(default_factory=Preview)
