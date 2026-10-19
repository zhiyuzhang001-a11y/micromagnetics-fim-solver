"""SI model contracts for the sequential FM/FiM interface."""
from dataclasses import dataclass, field, asdict, replace
from pathlib import Path
import math
from typing import Literal

MU0 = 4 * math.pi * 1e-7
Vec3 = tuple[float, float, float]


def scalar(value, name, *, positive=False, nonnegative=False):
    if isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value):
        raise ValueError(f'{name}: a finite number is required')
    if positive and value <= 0 or nonnegative and value < 0:
        raise ValueError(f'{name}: invalid range')
    return float(value)


def vector(value, name, *, unit=False):
    if not isinstance(value, (list, tuple)) or len(value) != 3:
        raise ValueError(f'{name}: a three-component vector is required')
    value = tuple(scalar(v, name) for v in value)
    if unit:
        n = math.hypot(*value)
        if not n or not math.isfinite(n):
            raise ValueError(f'{name}: nonzero finite direction required')
        value = tuple(v / n for v in value)
    return value


@dataclass(frozen=True, kw_only=True, init=False)
class Grid:
    cells: tuple[int, int, int]
    cell_size: Vec3
    boundary: Literal['open', 'periodic_xy'] = 'open'
    origin: Vec3 = (0., 0., 0.)
    mirrors: tuple[int, int] = (0, 0)

    def __init__(self, *, cell_size: Vec3, size: Vec3 | None = None,
                 cells: tuple[int, int, int] | None = None,
                 boundary: Literal['open', 'periodic_xy'] = 'open',
                 origin: Vec3 = (0., 0., 0.), mirrors: tuple[int, int] = (0, 0)):
        if (size is None) == (cells is None):
            raise ValueError('supply exactly one of size [m] and cells')
        spacing = vector(cell_size, 'cell_size')
        for value in spacing:
            scalar(value, 'cell_size', positive=True)
        requested = None
        if size is not None:
            requested = vector(size, 'size')
            counts = []
            for length, step in zip(requested, spacing):
                scalar(length, 'size', positive=True)
                ratio = length / step
                if not math.isfinite(ratio) or ratio > 2**31-1:
                    raise ValueError('size/cell_size exceeds native signed 32-bit count capacity')
                count = round(ratio)
                if count < 1 or abs(ratio-count) > 8*math.ulp(max(1., ratio)) or abs(length-count*step) > 8*max(math.ulp(length), math.ulp(count*step)):
                    raise ValueError(f'size must be an integer multiple of cell_size; nearest cell counts are {math.floor(ratio)} and {math.ceil(ratio)}')
                counts.append(count)
            cells = tuple(counts)
        for key, value in dict(cells=tuple(cells), cell_size=spacing, boundary=boundary,
                               origin=tuple(origin), mirrors=tuple(mirrors)).items():
            object.__setattr__(self, key, value)
        object.__setattr__(self, '_requested_size', requested)
        self.__post_init__()

    @property
    def size(self):
        return tuple(n*h for n,h in zip(self.cells, self.cell_size))

    @property
    def requested_size(self):
        return self._requested_size

    def __post_init__(self):
        for key in ('cells', 'cell_size', 'origin', 'mirrors'):
            object.__setattr__(self, key, tuple(getattr(self, key)))
        if len(self.cells) != 3 or any(type(v) is not int or v < 1 for v in self.cells):
            raise ValueError('cells: three positive integers required')
        if self.cells[2] != 1:
            raise ValueError('only single-layer geometry is implemented')
        vector(self.cell_size, 'cell_size')
        for v in self.cell_size:
            scalar(v, 'cell_size', positive=True)
        if max(self.cell_size) / min(self.cell_size) > 4:
            raise ValueError('cell aspect ratio exceeds the implemented kernel domain of four')
        if not math.isfinite(math.prod(self.cell_size)) or math.prod(self.cell_size) <= 0:
            raise ValueError('cell volume exceeds floating-point arithmetic range')
        vector(self.origin, 'origin')
        if self.boundary not in ('open', 'periodic_xy'):
            raise ValueError('boundary: open or periodic_xy required')
        if len(self.mirrors) != 2 or any(type(v) is not int or not 0 <= v <= 40 for v in self.mirrors):
            raise ValueError('mirrors: two integers in the implemented 0..40 domain required')
        if self.boundary == 'open' and self.mirrors != (0, 0):
            raise ValueError('open boundary requires mirrors=(0, 0)')
        if self.boundary == 'periodic_xy' and min(self.cells[:2]) < 3:
            raise ValueError('periodic dimensions require at least three cells')
        from ..capacity import geometry_capacity
        geometry_capacity(*self.cells[:2], self.boundary=='periodic_xy', self.mirrors)

    @property
    def shape(self):
        return (*reversed(self.cells), 3)


@dataclass(frozen=True, kw_only=True)
class Sublattice:
    Ms: float
    alpha: float
    gamma_H: float

    def __post_init__(self):
        scalar(self.Ms, 'Ms', positive=True)
        scalar(self.alpha, 'alpha', nonnegative=True)
        scalar(self.gamma_H, 'gamma_H', positive=True)
        if not math.isfinite(self.alpha * self.alpha):
            raise ValueError('alpha: arithmetic overflow')


@dataclass(frozen=True, kw_only=True)
class FMMaterial(Sublattice):
    pass


@dataclass(frozen=True, kw_only=True)
class FiMMaterial:
    A: Sublattice
    B: Sublattice
    convention: Literal['equal_half_volume'] = 'equal_half_volume'

    def __post_init__(self):
        if not isinstance(self.A, Sublattice) or not isinstance(self.B, Sublattice):
            raise TypeError('FiMMaterial requires explicit A and B Sublattice values')
        if self.convention != 'equal_half_volume':
            raise ValueError('only equal_half_volume is implemented')


@dataclass(frozen=True, kw_only=True)
class Exchange:
    A: float

    def __post_init__(self):
        scalar(self.A, 'A', nonnegative=True)


@dataclass(frozen=True, kw_only=True)
class FiMExchange:
    A_A: float
    A_B: float
    Anh: float = 0.

    def __post_init__(self):
        scalar(self.A_A, 'A_A', nonnegative=True)
        scalar(self.A_B, 'A_B', nonnegative=True)
        scalar(self.Anh, 'Anh')
        if self.Anh and (min(self.A_A, self.A_B) <= 0 or abs(self.Anh) >= 2 * math.sqrt(self.A_A) * math.sqrt(self.A_B)):
            raise ValueError('cross-gradient quadratic form must be positive definite')


@dataclass(frozen=True, kw_only=True)
class OnsiteCoupling:
    Ah: float

    def __post_init__(self):
        scalar(self.Ah, 'Ah')


@dataclass(frozen=True, kw_only=True)
class DMI:
    D_A: float
    D_B: float

    def __post_init__(self):
        scalar(self.D_A, 'D_A')
        scalar(self.D_B, 'D_B')


@dataclass(frozen=True, kw_only=True)
class UniaxialAnisotropy:
    K1: float
    axis: Vec3 = (0., 0., 1.)

    def __post_init__(self):
        scalar(self.K1, 'K1')
        object.__setattr__(self, 'axis', vector(self.axis, 'axis', unit=True))


@dataclass(frozen=True, kw_only=True)
class FiMAnisotropy:
    K1_A: float
    K1_B: float
    K2_A: float = 0.
    K2_B: float = 0.
    axis_A: Vec3 = (0., 0., 1.)
    axis_B: Vec3 = (0., 0., 1.)

    def __post_init__(self):
        for key in ('K1_A', 'K1_B', 'K2_A', 'K2_B'):
            scalar(getattr(self, key), key)
        for key in ('axis_A', 'axis_B'):
            object.__setattr__(self, key, vector(getattr(self, key), key, unit=True))


@dataclass(frozen=True, kw_only=True)
class Demag:
    pass


@dataclass(frozen=True, kw_only=True)
class Zeeman:
    H_ext: Vec3 | None = None
    B_ext: Vec3 | None = None

    def __post_init__(self):
        if (self.H_ext is None) == (self.B_ext is None):
            raise ValueError('supply exactly one of H_ext [A/m] and B_ext [T]')
        key = 'H_ext' if self.H_ext is not None else 'B_ext'
        object.__setattr__(self, key, vector(getattr(self, key), 'external field'))

    @property
    def H(self):
        return tuple(self.H_ext) if self.H_ext is not None else tuple(v / MU0 for v in self.B_ext)


@dataclass(frozen=True, kw_only=True)
class FiMSOT:
    J: Vec3
    xi_A: float
    xi_B: float
    incident_direction: Vec3 = (0., 0., 1.)
    field_like_A: float = 0.
    field_like_B: float = 0.

    def __post_init__(self):
        object.__setattr__(self, 'J', vector(self.J, 'J'))
        if self.J[2] != 0:
            raise ValueError('only constant in-plane conventional current is implemented')
        for key in ('xi_A', 'xi_B', 'field_like_A', 'field_like_B'):
            scalar(getattr(self, key), key)
        object.__setattr__(self, 'incident_direction', vector(self.incident_direction, 'incident_direction', unit=True))

    def with_current_density(self, *, J):
        return replace(self, J=J)


@dataclass(frozen=True, kw_only=True)
class FM:
    mesh: Grid
    material: FMMaterial
    energy: tuple = ()

    def __post_init__(self):
        validate_model(self, (Exchange, UniaxialAnisotropy, Demag, Zeeman))
        if not isinstance(self.material, FMMaterial):
            raise TypeError('FM requires FMMaterial')
        if self.mesh.boundary != 'open':
            raise ValueError('FM currently supports open boundary only')

    @property
    def labels(self):
        return ('FM',)


@dataclass(frozen=True, kw_only=True)
class FiM:
    mesh: Grid
    material: FiMMaterial
    energy: tuple = ()

    def __post_init__(self):
        validate_model(self, (FiMExchange, OnsiteCoupling, DMI, FiMAnisotropy, Demag, Zeeman))
        if not isinstance(self.material, FiMMaterial):
            raise TypeError('FiM requires FiMMaterial')
        for term in self.energy:
            if isinstance(term, FiMExchange) and term.Anh and self.mesh.boundary != 'periodic_xy':
                raise ValueError('nonzero Anh requires periodic_xy')

    @property
    def labels(self):
        return ('A', 'B')


def validate_model(model, allowed):
    if not isinstance(model.mesh, Grid):
        raise TypeError('mesh must be an SI Grid')
    if not isinstance(model.energy, (tuple, list)):
        raise TypeError('energy must be a sequence of explicit terms')
    seen = set()
    for term in model.energy:
        if type(term) not in allowed:
            raise TypeError(f'{type(model).__name__}: unsupported energy term {type(term).__name__}')
        if type(term) in seen:
            raise ValueError('duplicate energy term')
        seen.add(type(term))
    object.__setattr__(model, 'energy', tuple(model.energy))


def describe(model):
    return {'model': type(model).__name__, 'labels': model.labels,
            'mesh': asdict(model.mesh), 'material': asdict(model.material),
            'energy': [dict(type=type(term).__name__, **asdict(term)) for term in model.energy],
            'units': 'SI: m, s, A/m, J; B_ext alone is T',
            'convention': 'full_volume' if isinstance(model, FM) else 'equal_half_volume',
            'hidden_field': False, 'hidden_current': False, 'resource_budgets': None}
