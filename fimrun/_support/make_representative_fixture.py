"""GPL-3.0-only. Fixed project-authored historical direction-profile fixture."""
from pathlib import Path
import argparse
import hashlib
import json
import math
import numpy as np

HEADER = '''P-Anh-v1 original_seed user_script_I1
125 125 1
4.0000000000000002e-09 4.0000000000000002e-09 3e-09
1 1 0
300000 600000
4.9999999999999997e-12 4.9999999999999997e-12
-8000000 -8000000
-4.9999999999999997e-12 -4.9999999999999997e-12
0.0010499999999999999 0.0010499999999999999
109000 109000
0 0
0 0 1
1 1 1 1
1 30 2147483648
'''


def directions():
    # Original fixed-length direction construction, not a saved relaxed state.
    n = 125
    y, x = np.meshgrid((np.arange(n) + .5) * 4e-9,
                       (np.arange(n) + .5) * 4e-9, indexing='ij')
    dx, dy = 200e-9 - x, 300e-9 - y
    r = np.hypot(dx, dy)
    a = np.zeros((n, n, 3)); a[..., 2] = 1
    ix0, ix1 = [int(math.floor(v / 4e-9 + .5)) for v in [175e-9, 225e-9]]
    iy0, iy1 = [int(math.floor(v / 4e-9 + .5)) for v in [275e-9, 325e-9]]
    rect = np.zeros((n, n), dtype=bool); rect[iy0:iy1, ix0:ix1] = True
    inside = rect & (r <= 25e-9)
    ring = inside & (r >= 25e-9 * .4)
    a[inside & ~ring] = [0, 0, -1]
    z = -np.tanh((r - 25e-9 * .7) * 2 / (25e-9 * .3))
    radial = np.sqrt(np.maximum(0, 1 - z * z))
    a[..., 0][ring] = (dx * radial / np.where(r > 0, r, 1))[ring]
    a[..., 1][ring] = (dy * radial / np.where(r > 0, r, 1))[ring]
    a[..., 2][ring] = -z[ring]
    return np.array([a[None], -a[None]])


def make(out):
    out = Path(out); out.mkdir(parents=True, exist_ok=False)
    m = directions()
    pairs = np.concatenate([m[0].reshape(-1, 3), m[1].reshape(-1, 3)], axis=1)
    config = out / 'config.dat'
    config.write_text(HEADER + ''.join(' '.join(format(float(v), '.17g') for v in row)
                                     + '\n' for row in pairs))
    m.astype('<f8').tofile(out / 'seed.f64')
    metadata = {'profile': 'fixed original direction profile; center (200,300) nm; radius parameter25nm',
                'shape': [2, 1, 125, 125, 3], 'storage': 'little-endian binary64, A then B, x fastest',
                'configuration_sha256': hashlib.sha256(config.read_bytes()).hexdigest(),
                'seed_sha256': hashlib.sha256((out / 'seed.f64').read_bytes()).hexdigest(),
                'provenance_limit': 'Historical B-amplitude mapping to fixed-length directions retained; not an installation-specific BORIS reproduction.'}
    (out / 'metadata.json').write_text(json.dumps(metadata, indent=2) + '\n')
    return metadata


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('out', type=Path)
    print(json.dumps(make(parser.parse_args().out), indent=2))
