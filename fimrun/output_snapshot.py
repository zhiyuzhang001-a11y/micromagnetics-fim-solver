"""Read a frozen set of committed OVF frames from a visible running output."""
import hashlib
import json
from pathlib import Path
from .postprocess.io import sha

SCHEMA = 'notebook-output-progress-v1'


def frames_from_output(directory):
    root = Path(directory).resolve()
    path = root/'progress.json'
    # The progress file and CSV may keep growing. Freeze this one document;
    # analysis verifies only its immutable committed OVFs, never a moving CSV.
    raw = path.read_bytes()
    snapshot = json.loads(raw)
    if snapshot.get('schema') != SCHEMA:
        raise ValueError('unsupported running output manifest')
    labels = snapshot.get('labels')
    if labels not in (['A'], ['A', 'B']):
        raise ValueError('unsupported output labels')
    identity = {k: snapshot[k] for k in ('run_id', 'segment_id', 'stage')}
    frames = []
    previous = -1
    for entry in snapshot['frames']:
        step = entry['accepted_index']
        if isinstance(step, bool) or not isinstance(step, int) or step <= previous:
            raise ValueError('output frame steps must increase')
        previous = step
        frame = {'mapping': {**identity, 'accepted_index': step,
                 'time_s': entry['time_s'], 'output_snapshot': {
                     'path': str(path), 'sha256': hashlib.sha256(raw).hexdigest(),
                     'status': snapshot['status']}}}
        for label in labels:
            member = entry['files'][label]
            target = root/member['path']
            if target.is_symlink() or not target.resolve().is_relative_to(root):
                raise ValueError('output frame outside its directory')
            if not target.is_file() or sha(target) != member['sha256']:
                raise ValueError('output frame hash mismatch: '+member['path'])
            frame[label] = target
        frames.append(frame)
    if not frames:
        raise ValueError('No complete saved frames yet; wait for the next save interval')
    return frames
