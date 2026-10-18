"""Typed initial directions; no hidden opposite sublattice or normalization."""
from dataclasses import dataclass
import importlib
import numpy as np
from .model import FM, vector, scalar
from .._support import ovf as _ovf, initial_state as _initial_state


@dataclass(frozen=True)
class Uniform:
    direction: tuple
    normalize: bool = False

    def __post_init__(self):
        if type(self.normalize) is not bool:
            raise TypeError('normalize must be True or False')
        object.__setattr__(self, 'direction', vector(self.direction, 'direction'))

    def generate(self, grid):
        v = np.array(vector(self.direction, 'direction'))
        return directions(np.broadcast_to(v, grid.shape).copy(), grid.shape, self.normalize)


@dataclass(frozen=True, kw_only=True)
class Smooth:
    amplitude: float

    def generate(self, grid):
        scalar(self.amplitude, 'amplitude')
        if abs(self.amplitude) >= 1:
            raise ValueError('smooth amplitude must have magnitude below one')
        nx, ny, _ = grid.cells
        yy, xx = np.meshgrid((np.arange(ny) + .5) / ny, (np.arange(nx) + .5) / nx, indexing='ij')
        t = self.amplitude * np.cos(2 * np.pi * (xx + yy))
        return np.stack((t, np.zeros_like(t), np.sqrt(1 - t * t)), -1)[None]


@dataclass(frozen=True, kw_only=True)
class Skyrmion:
    center: tuple
    radius: float
    wall: float
    helicity: float = 0.
    polarity: int = -1

    def generate(self, grid):
        for key in ('radius', 'wall'):
            scalar(getattr(self, key), key, positive=True)
        scalar(self.helicity, 'helicity')
        if len(self.center) != 2 or any(not np.isfinite(v) for v in self.center):
            raise ValueError('center requires two finite SI coordinates')
        if type(self.polarity) is not int or self.polarity not in (-1, 1):
            raise ValueError('polarity must be -1 or 1')
        nx, ny, _ = grid.cells
        yy, xx = np.meshgrid(grid.origin[1] + (np.arange(ny) + .5) * grid.cell_size[1],
                             grid.origin[0] + (np.arange(nx) + .5) * grid.cell_size[0], indexing='ij')
        dx, dy = xx - self.center[0], yy - self.center[1]
        theta = .5 * np.pi * (1 - np.tanh((np.hypot(dx, dy) - self.radius) / self.wall))
        phi = np.arctan2(dy, dx) + self.helicity
        return np.stack((np.sin(theta) * np.cos(phi), np.sin(theta) * np.sin(phi),
                         -self.polarity * np.cos(theta)), -1)[None]


@dataclass(frozen=True)
class Antiparallel:
    A: object


@dataclass(frozen=True)
class LegacyFixture:
    name: str


@dataclass(frozen=True, kw_only=True)
class OVF:
    path: str
    quantity: str

    def generate(self, grid, Ms):
        if self.quantity not in ('direction', 'magnetization_Apm'):
            raise ValueError('OVF quantity must be direction or magnetization_Apm')
        geometry = {'n': list(grid.cells), 'cell_nm': [h * 1e9 for h in grid.cell_size],
                    'origin_nm': [h * 1e9 for h in grid.origin]}
        return _ovf.read(self.path, geometry, Ms, self.quantity)[0]


class Magnetization:
    uniform = Uniform
    smooth = Smooth
    skyrmion = Skyrmion
    antiparallel = Antiparallel
    legacy = LegacyFixture
    ovf = OVF


def directions(value, shape, normalize=False):
    raw = np.asarray(value)
    if raw.dtype.kind not in 'fiu':
        raise ValueError('magnetization arrays must contain real numeric values, not strings, booleans or complex values')
    array = np.array(raw, dtype=np.float64, copy=True)
    if array.shape != shape or not np.isfinite(array).all():
        raise ValueError(f'magnetization must have finite shape {shape}')
    n = np.linalg.norm(array, axis=-1)
    if np.any(n == 0) or not np.isfinite(n).all():
        raise ValueError('magnetic directions must be finite and nonzero')
    if normalize:
        array /= n[..., None]
    elif np.max(np.abs(n - 1)) > 1e-12:
        raise ValueError('directions must be unit length; request normalization explicitly')
    return array


def generate(model, initial):
    grid = model.mesh
    if isinstance(initial, LegacyFixture):
        if isinstance(model, FM) or initial.name != 'canonical_legacy' or grid.cells != (125, 125, 1) or grid.cell_size != (4e-9, 4e-9, 3e-9) or grid.origin != (0., 0., 0.):
            raise ValueError('legacy fixture requires canonical FiM geometry and explicit name')
        return _initial_state.generate({'geometry': {'n': list(grid.cells), 'cell_nm': [h * 1e9 for h in grid.cell_size], 'origin_nm': [0, 0, 0]}, 'initial': {'kind': 'canonical_legacy'}})[0]
    if isinstance(initial, Antiparallel):
        if isinstance(model, FM):
            raise ValueError('antiparallel constructor requires FiM')
        a = one(initial.A, grid, model.material.A.Ms)
        return np.array([a, -a])
    if isinstance(model, FM):
        if isinstance(initial, dict):
            raise ValueError('FM accepts one field, not A/B labels')
        return one(initial, grid, model.material.Ms)[None]
    if not isinstance(initial, dict) or set(initial) != {'A', 'B'}:
        raise ValueError('FiM requires explicit independent A/B fields or Antiparallel')
    return np.array([one(initial[label], grid, getattr(model.material, label).Ms) for label in model.labels])


def one(value, grid, Ms):
    if isinstance(value, OVF):
        return directions(value.generate(grid, Ms), grid.shape)
    if isinstance(value, (Uniform, Smooth, Skyrmion)):
        return directions(value.generate(grid), grid.shape)
    return directions(value, grid.shape)
