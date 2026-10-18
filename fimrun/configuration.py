"""Thin typed-to-legacy mapping. Scientific constraints remain in legacy resolve."""
from dataclasses import asdict
from pathlib import Path
import math
from .api import *
from .bridge import legacy

class ConfigError(ValueError):
    pass

def number(path, value, *, positive=False, integer=False):
    try: finite = math.isfinite(value) if isinstance(value,(int,float)) else False
    except OverflowError: finite = False
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not finite:
        raise ConfigError(f'{path}: 需要有限数值，收到 {value!r}；数字不要加引号，bool不是数值')
    if integer and not isinstance(value, int):
        raise ConfigError(f'{path}: 需要整数，收到 {value!r}')
    if positive and value <= 0:
        raise ConfigError(f'{path}: 需要正数，收到 {value!r}')

def vector(path, value, length, *, integer=False):
    if not isinstance(value, (tuple, list)) or len(value) != length:
        raise ConfigError(f'{path}: 需要{length}个数，例如 '+('(125,125,1)' if integer else '(0.,0.,1.)'))
    for i, v in enumerate(value):
        number(f'{path}[{i}]', v, integer=integer)

def path_value(path, value, base):
    if not isinstance(value, (str, Path)) or not str(value):
        raise ConfigError(f'{path}: 需要非空路径字符串或Path')
    return (base / value).resolve()

def validate(case):
    expected={'material':Material,'mesh':Mesh,'field':Field,'initial':Initial,
              'preparation':Preparation,'drive':Drive,'runtime':Runtime,
              'budget':Budget,'output':Output,'preview':Preview}
    if not isinstance(case, Case): raise ConfigError('case: 需要Case(...)')
    for key, cls in expected.items():
        if not isinstance(getattr(case,key),cls): raise ConfigError(f'{key}: 需要{cls.__name__}(...)，不是dict')
    if case.workflow not in ('relax','prepare_then_drive','drive'): raise ConfigError('workflow: 只支持relax/prepare_then_drive/drive')
    if case.workflow=='drive' and not isinstance(case.prepared,PreparedState): raise ConfigError('prepared: drive需要合格PreparedState(report=...)；OVF先准备')
    if case.workflow!='drive' and case.prepared is not None: raise ConfigError('prepared: 仅独立drive使用，不能与新初猜混用')
    for key in ('Ms_Apm','A_Jpm','D_Jpm2','K1_Jpm3','K2_Jpm3','alpha','gamma_H_m_per_As'):
        vector('material.'+key,getattr(case.material,key),2)
    for key in ('Ah_Jpm3','Anh_Jpm'):number('material.'+key,getattr(case.material,key))
    vector('material.active',case.material.active,4,integer=True)
    if not isinstance(case.material.axes,(tuple,list)) or len(case.material.axes)!=2: raise ConfigError('material.axes: 需要A/B两个三维向量')
    for i,a in enumerate(case.material.axes):vector(f'material.axes[{i}]',a,3)
    for key,n in [('n',3),('pbc',3),('mirrors',2)]:vector('mesh.'+key,getattr(case.mesh,key),n,integer=True)
    vector('mesh.cell_nm',case.mesh.cell_nm,3);vector('mesh.origin_nm',case.mesh.origin_nm,3)
    for key in ('H_Apm','mu0_H_T'):
        if getattr(case.field,key) is not None:vector('field.'+key,getattr(case.field,key),3)
    for key in ('A','B'):vector('initial.'+key,getattr(case.initial,key),3)
    vector('initial.center_nm',case.initial.center_nm,2)
    for key in ('amplitude','radius_nm','wall_nm','helicity_rad'):number('initial.'+key,getattr(case.initial,key))
    number('initial.polarity',case.initial.polarity,integer=True)
    for key in ('ovf_A','ovf_B'):
        if not isinstance(getattr(case.initial,key),(str,Path)):raise ConfigError('initial.'+key+': 需要路径')
    for label,stage in [('preparation',case.preparation),('drive',case.drive)]:
        if not isinstance(stage.dynamics,Dynamics):raise ConfigError(label+'.dynamics: 需要Dynamics(...)')
        number(label+'.dynamics.dt_fs [fs]',stage.dynamics.dt_fs,positive=True)
        number(label+'.dynamics.T_ps [ps]',stage.dynamics.T_ps)
    number('preparation.tol_Apm [A/m]',case.preparation.tol_Apm,positive=True)
    number('preparation.max_updates',case.preparation.max_updates,integer=True)
    for key,n in [('Jc_Apm2',3),('incident_direction',3),('xi',2),('field_like_ratio',2)]:vector('drive.'+key,getattr(case.drive,key),n)
    if not isinstance(case.drive.times_ps,(tuple,list)):raise ConfigError('drive.times_ps: 需要时间数组，单位ps')
    for i,v in enumerate(case.drive.times_ps):number(f'drive.times_ps[{i}] [ps]',v)
    for key in ('new_fields','rss_bytes','output_bytes'):number('budget.'+key,getattr(case.budget,key),positive=True,integer=True)
    number('budget.wall_s [s]',case.budget.wall_s,positive=True)
    if case.budget.output_bytes < 1048576:raise ConfigError('budget.output_bytes: 至少1MiB，按整run目录累计')
    number('output.save_every',case.output.save_every,positive=True,integer=True);number('output.heartbeat_s',case.output.heartbeat_s,positive=True)
    if type(case.preview.enabled) is not bool or type(case.preview.open_browser) is not bool:raise ConfigError('preview.enabled/open_browser: 需要True或False，不能用字符串')
    number('preview.port',case.preview.port,integer=True)
    if not 1024<=case.preview.port<=65535:raise ConfigError('preview.port: 需要1024…65535的显式端口')
    number('preview.startup_s',case.preview.startup_s,positive=True);number('preview.max_rss_bytes',case.preview.max_rss_bytes,positive=True,integer=True)
    number('preview.log_bytes',case.preview.log_bytes,positive=True,integer=True)
    if case.preview.log_bytes>1048576:raise ConfigError('preview.log_bytes: bounded capture supports at most1MiB')
    if not isinstance(case.preview.command,tuple) or any(not isinstance(x,str) or not x for x in case.preview.command):raise ConfigError('preview.command: 需要命令字符串tuple，不使用shell字符串')

def lists(value):
    if isinstance(value, dict):return {k:lists(v) for k,v in value.items()}
    if isinstance(value, (list,tuple)):return [lists(v) for v in value]
    if isinstance(value,Path):return str(value)
    return value

def build_cases(case, base, cap, source=None):
    validate(case);b=legacy();root=path_value('output.directory',case.output.directory,base)
    raw={'schema':'user_case_v1','geometry':lists(asdict(case.mesh)),
         'material':lists(asdict(case.material)),
         'field':{k:lists(v) for k,v in asdict(case.field).items() if v is not None},
         'initial':lists(asdict(case.initial)),
         'dynamic':asdict(case.preparation.dynamics),
         'static':{'tol_Apm':case.preparation.tol_Apm,'max_updates':case.preparation.max_updates},
         'resources':{'wall_s':case.budget.wall_s,'kernel_s':min(120.,case.budget.wall_s),
                      'max_fields':cap,'rss_bytes':case.budget.rss_bytes,'output_bytes':min(case.budget.output_bytes,1073741824)},
         'output':{'directory':str(root/'prepare'),'cache':str(path_value('runtime.cache',case.runtime.cache,base)),
                   'bins':str(path_value('runtime.bins',case.runtime.bins,base)),
                   'save_every':case.output.save_every,'heartbeat_s':case.output.heartbeat_s,'goal':case.output.goal},
         'validation':{'step_sensitivity':False,'max_chord':1e-4,'rms_chord':1e-5}}
    if case.workflow in ('relax','drive'):raw['dynamic']['T_ps']=0. # no unused preparation-time budget for standalone drive
    try:
        prep=b['user_case'].resolve_dict(raw,base)
        drive_raw=lists(raw);drive_raw['schema']='user_case_v2';drive_raw['workflow']={'mode':'driven_dynamic'}
        drive_raw['drive']={'kind':'constant',**{k:lists(v) for k,v in asdict(case.drive).items() if k not in ('dynamics','times_ps')}}
        drive_raw['dynamic']=asdict(case.drive.dynamics)
        drive_raw['initial']={'kind':'checkpoint_directions','checkpoint':str(source['checkpoint'] if source else root/'prepare/static/checkpoint.bin'),
                              'metadata':str(source['metadata'] if source else root/'prepare/static/checkpoint.bin.json')}
        drive_raw['output']['directory']=str(root/'drive');drive_raw['output']['times_ps']=list(case.drive.times_ps)
        driven=b['current_case'].resolve(drive_raw,base) if case.workflow!='relax' else None
    except (ValueError,TypeError) as e:raise ConfigError(f'配置/物理约束: {e}；检查对应分组的单位、类型与支持范围') from None
    return root,prep,driven
