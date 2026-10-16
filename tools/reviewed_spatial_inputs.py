"""GPL-3.0-only. Zero-Model adapters for the reviewed 125->250/M10 protocol.

Mapping creates an initial guess, not an equilibrium or an exact resume.
Cache import accepts only the already qualified fine payload, not a new kernel.
"""
from pathlib import Path
import argparse, hashlib, json, struct
import numpy as np
from user_case import load as load_user, digest
from kernel_cache import key_data, validate_kernel

FINE_SHA = 'fa09e930ac483924fb35491c96319721cc68c9adc7f71d1866a2b4f3d9f6784e'
COARSE_SHA = 'db71f379e2bea728a475d9e0c6e5e1183c7830ee1ba91e6909f84c532ec012b6'
def sha(path):
    return hashlib.file_digest(Path(path).open('rb'), 'sha256').hexdigest()
def map_state(checkpoint, output):
    checkpoint, output = Path(checkpoint), Path(output)
    meta = json.loads(Path(str(checkpoint)+'.json').read_text())
    raw = checkpoint.read_bytes()
    if (meta.get('schema') != 'user-checkpoint-v1' or meta.get('phase') != 'static'
        or meta.get('shape') != [125,125,1] or meta.get('kernel_sha256') != COARSE_SHA
        or meta.get('checkpoint_sha256') != sha(checkpoint)
        or len(raw) != 168+144*15625 or struct.unpack_from('<Q',raw,8)[0] != 15625
        or struct.unpack_from('<Q',raw,16)[0] != 64
        or raw[24:88].decode() != meta.get('identity')
        or list(struct.unpack_from('<3i',raw,88)) != [125,125,1]):
        raise ValueError('requires bound static125x125 canonical-M10 user checkpoint')
    m=np.frombuffer(raw[168:168+750000],'<f8').reshape(2,1,125,125,3)
    if not np.isfinite(m).all() or np.max(abs(np.linalg.norm(m,axis=-1)-1))>1e-12:
        raise ValueError('invalid source directions')
    u=(np.arange(250)+.5)/2-.5; i=np.floor(u).astype(int); f=u-i
    x=(1-f)[None,None,None,:,None]*m[:,:,:,i%125,:]+f[None,None,None,:,None]*m[:,:,:,(i+1)%125,:]
    v=(1-f)[None,None,:,None,None]*x[:,:,i%125,:,:]+f[None,None,:,None,None]*x[:,:,(i+1)%125,:,:]
    length=np.linalg.norm(v,axis=-1)
    if not np.isfinite(v).all() or length.min()<=1e-8:
        raise ValueError('unsafe interpolated vector')
    fine=v/length[...,None]
    output.mkdir(parents=True,exist_ok=False)
    header=('# OOMMF OVF 2.0\n# Segment count: 1\n# Begin: Segment\n# Begin: Header\n'
        '# meshtype: rectangular\n# meshunit: nm\n# valuedim: 3\n# valueunits: 1 1 1\n'
        '# xnodes: 250\n# ynodes: 250\n# znodes: 1\n# xstepsize: 2\n# ystepsize: 2\n'
        '# zstepsize: 3\n# xbase: 1\n# ybase: 1\n# zbase: 1.5\n# End: Header\n# Begin: Data Binary 8\n')
    for k,sub in enumerate(['A','B']):
        (output/f'fine_{sub}.ovf').write_bytes(header.encode()+struct.pack('<d',123456789012345.)
            +fine[k].astype('<f8').tobytes()+b'\n# End: Data Binary 8\n# End: Segment\n')
    report={'source_CP_sha256':sha(checkpoint),'minimum_interpolated_vector_norm':float(length.min()),
        'maximum_normalization_change':float(np.linalg.norm(fine-v,axis=-1).max()),
        'fine_direction_sha256':hashlib.sha256(fine.tobytes()).hexdigest(),
        'method':'separate A/B periodic cell-center bilinear interpolation then explicit normalization',
        'geometry':{'n':[250,250,1],'cell_nm':[2,2,3],'domain_nm':[500,500,3]},
        'not_exact_resume':True,'source_equilibrium_not_certified_by_this_adapter':True,
        'requires_independent_fine_preparation':True,'new_Models':0,'new_fields':0}
    (output/'mapping.json').write_text(json.dumps(report,indent=2)+'\n')
    return report

def import_cache(config,payload,cache):
    # user_case_v1 preparation template avoids any checkpoint/Model construction.
    case=load_user(Path(config)); g=case['geometry']; payload=Path(payload)
    if (g['n'] != [250,250,1] or g['cell_nm'] != [2,2,3] or g['pbc'] != [1,1,0]
        or g['mirrors'] != [10,10] or g['origin_nm'] != [0,0,0] or sha(payload) != FINE_SHA):
        raise ValueError('only the separately qualified250/M10 payload is accepted')
    folder=Path(cache)/digest(key_data(case)); folder.mkdir(parents=True,exist_ok=False)
    verification=validate_kernel(case,payload,samples=None)
    # Rechecks stored bytes/finite/reciprocity only; historical references are not rerun.
    (folder/'kernel.f64').write_bytes(payload.read_bytes())
    record=json.loads((Path(__file__).resolve().parents[1]/'results/current-sot-campaign-summary.json').read_text())['fine250_M10']
    manifest={'actual_generator_source_sha256':record['generator_source_sha256'],
        'actual_generator_binary_sha256':record['generator_binary_sha256'],'key':key_data(case),'payload_sha256':FINE_SHA,'source':'qualified-isolated-G1-import',
        'not_generated_by_current_builder':True,'verification':verification,
        'qualification_record':'results/current-sot-campaign-summary.json',
        'reference_qualification_replayed':False,'generation_and_validation_s':0,
        'cost_note':'import of previously qualified bytes; no generation/reference/Model/field',
        'physical_grid_convergence':'failed early sensitivity targets; not certified'}
    (folder/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    return {'cache_key':folder.name,'payload_sha256':FINE_SHA,'new_fields':0,'new_tensor_queries':0}

def main():
    p=argparse.ArgumentParser(description=__doc__); sub=p.add_subparsers(dest='action',required=True)
    a=sub.add_parser('map');a.add_argument('--checkpoint',required=True);a.add_argument('--output',required=True)
    a=sub.add_parser('cache');a.add_argument('--config',required=True);a.add_argument('--payload',required=True);a.add_argument('--cache',required=True)
    a=p.parse_args()
    result=map_state(a.checkpoint,a.output) if a.action=='map' else import_cache(a.config,a.payload,a.cache)
    print(json.dumps(result,indent=2))
if __name__=='__main__':main()
