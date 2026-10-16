"""Relocatable C++17 build; no downloads or system configuration changes."""
from pathlib import Path
import argparse,os,shlex,shutil,subprocess,sys,time,json
ROOT=Path(__file__).resolve().parents[1]
def build(out,validation=False,cap=90,serial_local=False):
 out=Path(out);out.mkdir(parents=True,exist_ok=True);start=time.monotonic();records=[]
 compiler=shlex.split(os.environ.get('CXX',shutil.which('clang++') or shutil.which('c++') or 'c++'))
 targets=[('fim_dynamic','src/dynamic.cpp',['fftw3']),('fim_static','src/static.cpp',['fftw3']),('fim_inspect','src/inspect.cpp',['fftw3'])]
 if validation:targets += [('label_prefix','validation/label/core_label.cpp',['fftw3']),('d0_reference','validation/d0/reference_point.cpp',['mpfr','gmp'])]
 if validation and sys.platform=='darwin':targets += [('fm_d1ns','validation/fm/fm_d1ns.cpp',[])]
 for name,source,libs in targets:
  remain=cap-(time.monotonic()-start)
  if remain<=0:raise RuntimeError('total build budget exhausted')
  flags=shlex.split(subprocess.check_output(['pkg-config','--cflags','--libs',*libs],text=True,timeout=min(5,remain))) if libs else ['-framework','Accelerate']
  backend_flags=(['-pthread']+([] if serial_local else ['-DLF_TWO_OWNER'])) if name.startswith('fim_') else []
  cmd=[*compiler,'-std=c++17','-O2',*backend_flags,str(ROOT/source),*flags,'-o',str(out/name)]
  t=time.monotonic();r=subprocess.run(cmd,text=True,capture_output=True,timeout=max(.1,min(60,cap-(time.monotonic()-start))))
  (out/(name+'.stderr.txt')).write_text(r.stderr);records.append({'target':name,'returncode':r.returncode,'elapsed_s':time.monotonic()-t,'local_backend':('serial' if serial_local else 'two-owner') if name.startswith('fim_') else 'unchanged','fftw_threads_enabled':False})
  (out/'build.json').write_text(json.dumps(records,indent=2)+'\n')
  if r.returncode:raise RuntimeError(r.stderr)
 return records
if __name__=='__main__':
 a=argparse.ArgumentParser();a.add_argument('--out',type=Path,default=ROOT/'build');a.add_argument('--validation',action='store_true');a.add_argument('--serial-local',action='store_true',help='build the C1 serial local-field rollback instead of the adopted two-owner backend');a.add_argument('--cap',type=float,default=90);args=a.parse_args();print(json.dumps(build(args.out,args.validation,args.cap,args.serial_local),indent=2))
