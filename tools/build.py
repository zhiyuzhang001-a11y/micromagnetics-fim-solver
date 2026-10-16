"""Relocatable C++17 build; no downloads or system configuration changes."""
from pathlib import Path
import argparse,os,shlex,shutil,subprocess,sys,time,json
ROOT=Path(__file__).resolve().parents[1]
def build(out,validation=False,cap=90,serial_local=False,user_workflow=False,current_sot=False):
 out=Path(out);out.mkdir(parents=True,exist_ok=True);start=time.monotonic();records=[]
 compiler=shlex.split(os.environ.get('CXX',shutil.which('clang++') or shutil.which('c++') or 'c++'))
 targets=[('fim_dynamic','src/dynamic.cpp',['fftw3']),('fim_static','src/static.cpp',['fftw3']),('fim_inspect','src/inspect.cpp',['fftw3'])]
 if current_sot:user_workflow=True
 if current_sot:targets += [('fim_drive','src/current_native.cpp',['fftw3']),('sot_checks','src/current_checks.cpp',['fftw3']),('sot_observer_checks','tests/current_observer.cpp',['fftw3'])]
 if user_workflow:targets += [('fim_user','src/user_native.cpp',['fftw3']),('kernel_builder','src/kernel_builder.cpp',['mpfr','gmp'])]
 if validation:targets += [('label_prefix','validation/label/core_label.cpp',['fftw3']),('d0_reference','validation/d0/reference_point.cpp',['mpfr','gmp'])]
 if validation and sys.platform=='darwin':targets += [('fm_d1ns','validation/fm/fm_d1ns.cpp',[])]
 for name,source,libs in targets:
  remain=cap-(time.monotonic()-start)
  if remain<=0:raise RuntimeError('total build budget exhausted')
  flags=shlex.split(subprocess.check_output(['pkg-config','--cflags','--libs',*libs],text=True,timeout=min(5,remain))) if libs else ['-framework','Accelerate']
  backend_flags=(['-pthread']+([] if serial_local else ['-DLF_TWO_OWNER'])) if name.startswith('fim_') else []
  cmd=[*compiler,'-std=c++17','-O2',*backend_flags,str(ROOT/source),*flags,'-o',str(out/name)]
  t=time.monotonic();r=subprocess.run(cmd,text=True,capture_output=True,timeout=max(.1,min(60,cap-(time.monotonic()-start))))
  (out/(name+'.stderr.txt')).write_text(r.stderr);records.append({'target':name,'command':cmd,'dependency_versions':{lib:subprocess.check_output(['pkg-config','--modversion',lib],text=True,timeout=5).strip() for lib in libs},'returncode':r.returncode,'elapsed_s':time.monotonic()-t,'local_backend':('serial' if serial_local else 'two-owner') if name.startswith('fim_') else 'unchanged','fftw_threads_enabled':False})
  (out/'build.json').write_text(json.dumps(records,indent=2)+'\n')
  if r.returncode:raise RuntimeError(r.stderr)
 return records
if __name__=='__main__':
 a=argparse.ArgumentParser();a.add_argument('--out',type=Path,default=ROOT/'build');a.add_argument('--validation',action='store_true');a.add_argument('--user-workflow',action='store_true',help='also build parameterized workflow and MPFR kernel generator');a.add_argument('--current-sot',action='store_true',help='also build the constant-current effective SOT workflow/checks');a.add_argument('--serial-local',action='store_true',help='build the C1 serial local-field rollback instead of the adopted two-owner backend');a.add_argument('--cap',type=float,default=90);args=a.parse_args();print(json.dumps(build(args.out,args.validation,args.cap,args.serial_local,args.user_workflow,args.current_sot),indent=2))
