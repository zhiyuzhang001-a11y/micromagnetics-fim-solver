"""Parent-side sampled owned RSS, root output and monotonic deadline guard."""
from pathlib import Path
import os
import signal
import subprocess
import time

def process_table():
    rows = subprocess.run(['ps', '-axo', 'pid=,ppid=,rss='], capture_output=True,
                          text=True, check=True, timeout=2).stdout.splitlines()
    return {int(p): (int(parent), int(kib)*1024) for p, parent, kib in (r.split() for r in rows)}

def descendants(table, root):
    result = {root}
    while True:
        extra = {pid for pid, (parent, _) in table.items() if parent in result}
        if extra <= result: return result
        result |= extra

def owned_rss(root, excluded=()):
    table = process_table(); pids = descendants(table, root)
    for pid in excluded:
        if pid: pids -= descendants(table, pid)
    return sum(table[p][1] for p in pids if p in table)

def output_size(root, *, exclude=None):
    total = 0
    for p in Path(root).rglob('*'):
        if exclude is not None and p==Path(root)/exclude:continue
        try:
            if p.is_file():
                if not p.resolve().is_relative_to(Path(root).resolve()): raise ValueError('output symlink escape')
                total += p.stat().st_size
        except FileNotFoundError: pass # native atomic rename
    return total

def stop(proc, *, include_orphans=False):
    if proc and (proc.poll() is None or include_orphans):
        try: os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError: pass
        proc.wait()

class Guard:
    def __init__(self, budget, started, root, *, preview_log_bytes=0):
        self.deadline = started + budget.wall_s; self.budget = budget; self.root = root
        self.peak_rss = 0; self.preview_pid = None
        self.preview_log_bytes=preview_log_bytes
    def science_size(self):
        # Skip only this bounded sink when deriving the pre-reserved science
        # allowance; check() still counts ALL actual root bytes against total O.
        return output_size(self.root,exclude='preview.log' if self.preview_log_bytes else None)
    def remaining(self):
        remaining = self.deadline - time.monotonic()
        if remaining <= 0: raise TimeoutError('whole-chain wall budget exhausted')
        return remaining
    def check(self):
        self.remaining()
        used=output_size(self.root)
        if used > self.budget.output_bytes: raise RuntimeError('whole-root output budget exhausted')
        if (self.science_size() if self.preview_log_bytes else used)>self.budget.output_bytes-self.preview_log_bytes: raise RuntimeError('science output exceeds pre-reserved root allocation')
        pid = self.preview_pid() if callable(self.preview_pid) else self.preview_pid
        rss = owned_rss(os.getpid(), [pid]); self.peak_rss = max(self.peak_rss, rss)
        if rss > self.budget.rss_bytes: raise RuntimeError('owned science RSS budget exhausted')
    def stage_resources(self, cumulative_cap):
        self.check()
        # Worst-case preview allocation is fixed before science starts. Log growth
        # within it cannot shrink a stage's already-issued scientific allowance.
        output = min(1073741824, self.budget.output_bytes-self.preview_log_bytes-self.science_size())
        if output < 1048576: raise RuntimeError('remaining whole-root output below backend minimum 1MiB')
        wall = self.remaining()
        return dict(wall_s=wall, kernel_s=min(120., wall), max_fields=cumulative_cap,
                    rss_bytes=self.budget.rss_bytes, output_bytes=output)
