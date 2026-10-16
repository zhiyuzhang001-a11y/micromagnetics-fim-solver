"""Build-command regression only: no compiler, Model or numerical run."""
from pathlib import Path
import importlib.util
import tempfile
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('project_build', ROOT / 'tools/build.py')
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


def check():
    for serial in (False, True):
        commands = []

        def compile_command(command, **kwargs):
            commands.append(command)
            return SimpleNamespace(returncode=0, stderr='')

        with tempfile.TemporaryDirectory() as out, \
             patch.object(builder.subprocess, 'check_output', return_value='-lfftw3'), \
             patch.object(builder.subprocess, 'run', side_effect=compile_command):
            records = builder.build(out, serial_local=serial)
        assert len(commands) == 3
        for command, record in zip(commands, records):
            assert ('-DLF_TWO_OWNER' in command) == (not serial)
            assert '-pthread' in command and '-O2' in command
            assert '-ffast-math' not in command and '-lfftw3_threads' not in command
            assert record['local_backend'] == ('serial' if serial else 'two-owner')
            assert record['fftw_threads_enabled'] is False
    print('passed: default two-owner and explicit serial rollback; zero numerical calls')


if __name__ == '__main__':
    check()
