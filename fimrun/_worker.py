"""Private subprocess adapter. Only execute invokes the unchanged scientific backend."""
import sys
from .bridge import legacy
from .protocol import read, atomic
from .qualification import verify_bindings, kernel_binding

def main():
    request = read(sys.argv[1]); c = request['case']; b = legacy()
    verify_bindings(request['bindings'])
    if kernel_binding(c)['sha256'] != request['kernel_sha256']: raise ValueError('worker kernel changed')
    module = b['run_current_workflow' if request['kind'] == 'drive' else 'run_user_workflow']
    report = module.run(c)
    atomic(request['result'], report)
    good = module.successful(report) if request['kind'] == 'drive' else module.requirements_met(report)
    return 0 if report.get('execution_completed') and good else 2

if __name__ == '__main__': raise SystemExit(main())
