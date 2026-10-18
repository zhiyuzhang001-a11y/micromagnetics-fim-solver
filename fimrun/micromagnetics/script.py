"""CLI plumbing for an explicit, preflighted scientific stage sequence."""
import argparse
from dataclasses import replace
import json
from datetime import datetime
from uuid import uuid4
from pathlib import Path
import re
import unicodedata
from .model import FM, Zeeman
from .simulation import Simulation, MaxTransverseField, RunResult
from .stages import Evolve, Relax, SetField, SetCurrent, SetSolver, SetOutputs, SaveState


# Fixed output ownership used by Simulation._begin/_observe/_finish. Custom
# saves may use an established segment's other names, but cannot create one.
ROOT_INDEX = 'segments.json'
SEGMENT_DIRECTORY = re.compile(r'segment-[0-9]{5,}\Z')
SEGMENT_FILES = ('accepted.state', 'result.json', 'scalars.csv')
SNAPSHOT_FILE = re.compile(r'm-[0-9]{12,}\.npz\Z')


def _overlaps(first, second):
    first, second = _path_key(first), _path_key(second)
    return first == second or first.is_relative_to(second) or second.is_relative_to(first)


def _path_key(path):
    # Conservative portable ownership also covers case/Unicode aliases on macOS.
    return Path(unicodedata.normalize('NFD', str(path)).casefold())


def _check_save_targets(targets, root, segments):
    root_key = _path_key(root) if root is not None else None
    segment_keys = {_path_key(path): position for path, position in segments.items()}
    for position, destination in targets:
        for parent in destination.parents:
            if parent.exists() and not parent.is_dir():
                raise FileExistsError('save parent is an existing file: ' + str(parent))
        if root is None:
            continue
        destination_key = _path_key(destination)
        if root_key.is_relative_to(destination_key):
            raise ValueError('save target occupies the experiment root or its ancestor')
        if _overlaps(destination, root / ROOT_INDEX):
            raise ValueError('save target conflicts with the runner segment index')
        if not destination_key.is_relative_to(root_key):
            continue
        parts = destination_key.relative_to(root_key).parts
        if not SEGMENT_DIRECTORY.fullmatch(parts[0]):
            continue
        segment = root_key / parts[0]
        if len(parts) == 1 or segment not in segment_keys or segment_keys[segment] >= position:
            raise ValueError('save target requires a segment directory established by an earlier stage')
        # Checking the first component also rejects descendants of managed files.
        if parts[1] in SEGMENT_FILES or SNAPSHOT_FILE.fullmatch(parts[1]):
            raise ValueError('save target conflicts with a runner-managed segment file')


def check_stages(sim, stages):
    if not isinstance(stages, (tuple, list)):
        raise TypeError('stages must be an explicit sequence')
    initial = sim.m[0] if isinstance(sim.model, FM) else dict(zip(sim.labels, sim.m))
    plans = []
    save_paths = set()
    save_targets = []
    segment_paths = {}
    segment_index = len(sim.segments)
    with Simulation(model=sim.model, initial=initial, solver=sim.solver, outputs=sim.outputs) as plan:
        plan.check()
        established_root = None
        for position, stage in enumerate(stages):
            if isinstance(stage, (Evolve, Relax)) and plan.outputs.directory is not None:
                target = Path(plan.outputs.directory).resolve()
                if established_root is None:
                    if target.exists():raise FileExistsError('output directory already exists')
                    established_root = target
                elif established_root != target:
                    raise ValueError('output root changes require a branch')
                plan._root = established_root
                segment_paths[established_root / f'segment-{segment_index:05d}'] = position
            if isinstance(stage, (Evolve, Relax)):
                segment_index += 1
            if isinstance(stage, Evolve):
                plans.append(plan.check(duration=stage.duration))
            elif isinstance(stage, Relax):
                if isinstance(plan.model, FM) or stage.method != 'sdesc' or not isinstance(stage.stop, MaxTransverseField) or plan.current is not None:
                    raise ValueError('static stage requires conservative FiM SDesc and an explicit stop')
            elif isinstance(stage, SetField):
                term = Zeeman(H_ext=stage.H_ext, B_ext=stage.B_ext)
                plan._model = replace(plan.model, energy=tuple(t for t in plan.model.energy if not isinstance(t, Zeeman))+(term,))
            elif isinstance(stage, (SetCurrent, SetSolver, SetOutputs)):
                stage.execute(plan)
            elif isinstance(stage, SaveState):
                if type(stage.strict) is not bool or not isinstance(stage.path, (str, Path)):
                    raise ValueError('save stage requires a path and bool strict flag')
                raw = Path(stage.path)
                destination = raw.resolve()
                if raw.is_symlink() or destination.exists() or any(_overlaps(destination, previous) for previous in save_paths):
                    raise FileExistsError('save destination exists or overlaps another save target')
                save_paths.add(destination)
                save_targets.append((position, destination))
            else:
                raise TypeError('unknown stage descriptor')
        _check_save_targets(save_targets, established_root, segment_paths)
    return {'valid': True, 'managed_fields': 0, 'managed_Model_calls': 0,
            'operations': [type(stage).__name__ for stage in stages], 'dynamic_plans': plans,
            'output_root': str(established_root) if established_root is not None else None,
            'save_targets': [{'stage_index': position, 'path': str(path)} for position, path in save_targets]}


def run_script(*, model, initial, solver, outputs=None, stages, argv=None):
    parser = argparse.ArgumentParser(description='Explicit sequential micromagnetic simulation')
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args(argv)
    with Simulation(model=model, initial=initial, solver=solver, outputs=outputs) as sim:
        plan = check_stages(sim, stages)
        if args.check:
            print(json.dumps(plan, indent=2))
            return 0
        # Execute the exact normalized targets that passed preflight. In particular,
        # mkdir on a raw path containing "segment-00000/.." could otherwise create
        # a future managed directory even when its resolved save target is safe.
        targets = {item['stage_index']: Path(item['path']) for item in plan['save_targets']}
        stages = tuple(replace(stage, path=targets[index]) if isinstance(stage, SaveState) else stage
                       for index, stage in enumerate(stages))
        # Claim the experiment before an initial-state save can create its parents.
        # Exclusive creation still rejects an external directory appearing after preflight.
        if plan['output_root'] is not None:
            root = Path(plan['output_root'])
            root.parent.mkdir(parents=True, exist_ok=True)
            root.mkdir(exist_ok=False)
            sim._root = root
        results = sim.execute(stages)
        if any(isinstance(r, RunResult) and r.status not in ('completed', 'converged') for r in results):
            print(sim.last_result)
            return 130
        print(json.dumps(sim.describe(), indent=2))
        return 0


def run_directory(parent, name):
    if not isinstance(name, str) or not name or Path(name).name != name:
        raise ValueError('task name must be one nonempty path component')
    return Path(parent) / (name+'_'+datetime.now().strftime('%Y%m%d-%H%M%S')+'-'+uuid4().hex[:8])
