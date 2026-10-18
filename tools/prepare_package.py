"""Explicit native build/resource preparation. Never invoked by import or run."""
from pathlib import Path
import argparse,hashlib,json,os,platform,shutil,subprocess
ROOT=Path(__file__).resolve().parents[1];PKG=ROOT/'fimrun';PAYLOAD=PKG/'_runtime'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def manifest():
    sources={str(p.relative_to(ROOT)):sha(p) for p in sorted(PKG.rglob('*.py')) if '_runtime' not in p.parts}
    payload={str(p.relative_to(PKG)):sha(p) for p in sorted(PKG.rglob('*')) if p.is_file() and p.suffix not in ('.py','.pyc') and p.name!='_build_info.json' and '__pycache__' not in p.parts}
    info=dict(schema='fimrun-installed-build-v1',version='0.2.0rc1',source_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        source_tree_dirty=bool(subprocess.check_output(['git','status','--porcelain'],cwd=ROOT,text=True).strip()),source_manifest=sources,payload_manifest=payload,supported='macOS 27 arm64',minimum_macos='27.0')
    (PKG/'_build_info.json').write_text(json.dumps(info,sort_keys=True,indent=2)+'\n')
def prepare(prefix):
    if platform.system()!='Darwin' or platform.machine()!='arm64':raise RuntimeError('qualified build host is macOS arm64')
    PAYLOAD.mkdir(exist_ok=True)
    for path in ('src','validation/fm'):
        shutil.copytree(ROOT/path,PAYLOAD/path,dirs_exist_ok=True)
    (PAYLOAD/'examples').mkdir(exist_ok=True);shutil.copy2(ROOT/'examples/kernel125-mirror10.f64',PAYLOAD/'examples/kernel125-mirror10.f64')
    for path in ('COPYING','LICENSE','NOTICE'):shutil.copy2(ROOT/path,PAYLOAD/path)
    shutil.copytree(ROOT/'LICENSES',PAYLOAD/'LICENSES',dirs_exist_ok=True)
    out=PAYLOAD/'build-script-api';out.mkdir(exist_ok=True);commands=[]
    for name in ('fm','fim','kernel_builder'):
        source=ROOT/'src/script_api'/(name+'.cpp');target=out/(name if name=='kernel_builder' else 'lib'+name+'.dylib')
        cmd=['/usr/bin/clang++','-std=c++17','-O2']
        if name!='kernel_builder':cmd+=['-dynamiclib','-pthread','-DLF_TWO_OWNER','-Wl,-install_name,@rpath/'+target.name]
        cmd += [str(source),'-o',str(target),'-I'+str(prefix/'include'),'-L'+str(prefix/'lib'),'-Wl,-rpath,@loader_path/../../../../..']
        cmd += ['-framework','Accelerate'] if name=='fm' else ['-lfftw3'] if name=='fim' else ['-lmpfr','-lgmp']
        subprocess.run(cmd,check=True);commands.append(cmd)
        deps=subprocess.check_output(['/usr/bin/otool','-L',str(target)],text=True).splitlines()[1:]
        for line in deps:
            dep=line.strip().split(' (')[0]
            if dep.startswith(str(prefix/'lib')+'/'):
                subprocess.run(['/usr/bin/install_name_tool','-change',dep,'@rpath/'+Path(dep).name,str(target)],check=True)
        subprocess.run(['/usr/bin/codesign','--force','--sign','-',str(target)],check=True)
    records={p.name:dict(sha256=sha(p),otool=subprocess.check_output(['/usr/bin/otool','-L',str(p)],text=True)) for p in out.iterdir() if p.is_file()}
    receipt=dict(schema='fimrun-native-build-v1',compiler=subprocess.check_output(['/usr/bin/clang++','--version'],text=True),commands=commands,source={str(p.relative_to(ROOT)):sha(p) for base in ('src','validation/fm') for p in (ROOT/base).rglob('*') if p.is_file()},artifacts=records,numerical_equations_changed=False)
    (PAYLOAD/'native-build.json').write_text(json.dumps(receipt,indent=2)+'\n');manifest()
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--native-prefix',type=Path);p.add_argument('--manifest-only',action='store_true');a=p.parse_args()
    if a.manifest_only:manifest()
    elif a.native_prefix:prepare(a.native_prefix.resolve())
    else:p.error('explicit --native-prefix required')
