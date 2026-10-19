"""Explicit offline pairing -> one exclusive CSV, with compact source bindings."""
from .session import read_bytes, parsed, report, tracked_reads
import csv,hashlib,io,json,re
from pathlib import Path
import numpy as np
from .io import read_ovf,read_state,sha,canonical,content_sha,implementation
from .geometry import measure,image,wrap
from .calibration import validate_calibration


@tracked_reads
def frames_from_state(path):
    """Only automatic flat output families with complete hash inventories."""
    path=Path(path).resolve();state,binding=read_state(path);flat=state.get('notebook_flat',{});inv=flat.get('inventory')
    if not isinstance(inv,dict):raise ValueError('automatic flat state inventory required; use explicit frames for legacy data')
    groups={};csvs=[]
    for scan,(rel,expected) in enumerate(inv.items(),1):
        report('库存文件校验',scan,len(inv))
        if expected is None:continue
        target=(path.parent/rel).resolve()
        if not target.is_relative_to(path.parent) or not target.is_file() or sha(target)!=expected:raise ValueError('state inventory path/hash mismatch: '+rel)
        if rel.endswith('.csv'):csvs.append(target)
        match=re.fullmatch(r'(rk4|sdesc)-(\d+)_(A|B)\.ovf',target.name)
        if match:
            kind,idx,label=match.groups();key=(kind,int(idx));groups.setdefault(key,{})[label]=target
    if len(csvs)>1:raise ValueError('ambiguous scalar CSV')
    return [{**group,'state':path,**({'csv':csvs[0]} if csvs else {}),'mapping':{'stage':kind,'accepted_index':idx}} for (kind,idx),group in sorted(groups.items())]


def _typed(name,value):
    if value is None:return None
    if name=='time_s':
        if isinstance(value,bool):raise ValueError('invalid physical time')
        value=float(value)
        if not np.isfinite(value) or value<0:raise ValueError('invalid physical time')
    elif name=='accepted_index':
        if isinstance(value,bool) or float(value)!=int(value) or int(value)<0:raise ValueError('invalid accepted index')
        value=int(value)
    elif name=='mirrors':
        value=list(map(int,value.split(','))) if isinstance(value,str) else list(value)
        if len(value)!=2 or any(isinstance(x,bool) or int(x)!=x or x<0 for x in value):raise ValueError('invalid mirrors metadata')
        value=list(map(int,value))
    elif name in ('run_id','segment_id') and (not isinstance(value,str) or not value):raise ValueError('invalid tracking identity')
    return value


def resolve(frame):
    sources={};choices={};arrays={};state=None;segment=None;inventory=None
    def add(name,value,source,field):
        if value is not None:choices.setdefault(name,[]).append((_typed(name,value),source,field))
    if frame.get('state'):
        state,binding=read_state(frame['state']);sources['state']=binding
        segment=state.get('segments',[])[-1] if state.get('segments') else None
        add('run_id',state['run_id'],'state','run_id')
        mesh=state['model']['mesh'];add('boundary',mesh['boundary'],'state','model.mesh.boundary');add('mirrors',mesh['mirrors'],'state','model.mesh.mirrors')
        inventory=state.get('notebook_flat',{}).get('inventory')
        if segment:
            add('segment_id',segment['id'],'state','segments[-1].id');add('stage',segment['kind'],'state','segments[-1].kind')
    mapping=frame.get('mapping',{})
    if isinstance(mapping,(str,Path)):
        path=Path(mapping).resolve();raw=read_bytes(path);mapping=json.loads(raw);sources['mapping']={'path':str(path),'sha256':hashlib.sha256(raw).hexdigest(),'canonical_sha256':content_sha(mapping)}
    else:sources['mapping']={'path':None,'canonical_content':mapping,'canonical_sha256':content_sha(mapping)}
    if not isinstance(mapping,dict):raise ValueError('mapping must be an explicit object')
    for i,evidence in enumerate(mapping.get('evidence',[])):
        p=Path(evidence['path']).resolve();actual=sha(p)
        if evidence.get('sha256',actual)!=actual:raise ValueError('mapping evidence hash mismatch')
        sources['mapping_evidence_'+str(i)]={'path':str(p),'sha256':actual}
    for name in ('run_id','segment_id','stage','time_s','accepted_index','boundary','mirrors'):add(name,mapping.get(name),'mapping',name)
    for label in ('A','B'):
        if label not in frame:continue
        ms=state['model']['material'][label]['Ms'] if state and label in state['model']['material'] else mapping.get('Ms_'+label)
        data=read_ovf(frame[label],Ms=ms,legacy=mapping.get('legacy_'+label));arrays[label]=data;sources[label]={'path':data['path'],'sha256':data['sha256'],'label_declaration':label,'normalization':data['normalization'],'legacy_header_overrides':data['legacy_header_overrides']}
        if data['label'] is not None and data['label']!=label:raise ValueError('sublattice label conflict')
        if inventory is not None:
            matching=[key for key,value in inventory.items() if value==data['sha256'] and key.endswith('.ovf')]
            if len(matching)!=1:raise ValueError('OVF not uniquely bound by state inventory')
            sources[label]['inventory_member']=matching[0]
        if state:
            mesh=state['model']['mesh']
            if tuple(mesh['cells'])!=data['cells'] or not np.allclose(mesh['cell_size'],data['h'],rtol=1e-12,atol=0) or not np.allclose(mesh['origin'],data['origin'],rtol=1e-12,atol=1e-20):raise ValueError('OVF/state grid mismatch')
        for name in ('run_id','segment_id','stage','time_s','accepted_index','boundary','mirrors'):add(name,data['fields'].get(name),label,'Desc.'+name)
    preliminary={k:values[0][0] for k,values in choices.items()}
    for name,enabled in mapping.get('overrides',{}).items():
        if enabled and name in mapping and mapping.get('override_reason'):preliminary[name]=_typed(name,mapping[name])
    if frame.get('packet'):
        p=Path(frame['packet']).resolve();raw=read_bytes(p);packet=json.loads(raw);sources['packet']={'path':str(p),'sha256':hashlib.sha256(raw).hexdigest()}
        if not packet.get('complete'):raise ValueError('incomplete legacy packet')
        for label,data in arrays.items():
            if packet['sublattices'][label]['sha256']!=data['sha256']:raise ValueError('packet hash mismatch')
        add('time_s',packet.get('time_s'),'packet','time_s');add('run_id',packet.get('run_id'),'packet','run_id')
    if frame.get('csv'):
        path=Path(frame['csv']).resolve();raw=read_bytes(path);sources['csv']={'path':str(path),'sha256':hashlib.sha256(raw).hexdigest()}
        if inventory is not None and not any(k.endswith('.csv') and v==sources['csv']['sha256'] for k,v in inventory.items()):raise ValueError('CSV not bound by state inventory')
        records=parsed(path,'csv',lambda:list(csv.DictReader(io.StringIO(raw.decode('utf-8')))))
        matches=[r for r in records if (preliminary.get('accepted_index') is None or int(r['step'])==preliminary['accepted_index']) and (preliminary.get('segment_id') is None or r['segment_id']==preliminary['segment_id'])]
        if len(matches)!=1:raise ValueError('ambiguous or missing CSV frame row')
        r=matches[0];sources['csv']['row_key']={k:r[k] for k in ('segment_id','step')}
        for name,col in [('time_s','time_s'),('stage','stage'),('segment_id','segment_id'),('accepted_index','step')]:add(name,r.get(col),'csv',col)
    facts={};meta={}
    overrides=mapping.get('overrides',{})
    for name,candidates in choices.items():
        distinct={canonical(v) for v,_,_ in candidates}
        if len(distinct)>1:
            if not overrides.get(name) or not mapping.get('override_reason'):raise ValueError('conflicting metadata: '+name)
            candidates=[c for c in candidates if c[1]=='mapping']
            if len(candidates)!=1:raise ValueError('override requires explicit mapped value')
        value,source,field=candidates[0];meta[name]=value;facts[name]={'source':source,'field':field,'override':len(distinct)>1,'reason':mapping.get('override_reason') if len(distinct)>1 else None}
    if 'boundary' not in meta:raise ValueError('missing_boundary; explicitly bind state or mapping')
    if meta['boundary'] not in ('open','periodic_xy'):raise ValueError('unsupported_boundary')
    if len(arrays)==2:
        a,b=arrays.values()
        if a['cells']!=b['cells'] or not np.array_equal(a['h'],b['h']) or not np.array_equal(a['origin'],b['origin']):raise ValueError('A/B grid mismatch')
    facts['frame_pair']={'source':'explicit frame A/B declarations plus available header labels/inventory','labels':list(arrays)}
    if segment:
        meta['lineage']={k:segment.get(k) for k in ('parent_segment','t_start','t_end','events_before')};facts['lineage']={'source':'state','field':'segments[-1] and events'}
    return arrays,meta,dict(schema='source-bindings-v1',sources=sources,facts=facts)


def _analyze_rows(frames,*,calibration=None,assume_temporal_sampling=False,ab_reference=None,velocity_window_s=None):
    """User-selected frames only. Unknown/invalid quantities -> NaN + reasons.

    Segments intentionally do not connect automatically. A physical velocity
    requires explicit sampling assumption and >=3 valid times in one segment.
    """
    if calibration is None:calibration=Path(__file__).parent/'calibration_v1.json'
    if isinstance(calibration,(str,Path)):
        p=Path(calibration).resolve();raw=p.read_bytes();c=json.loads(raw);cal_binding={'path':str(p),'sha256':hashlib.sha256(raw).hexdigest(),'canonical_sha256':content_sha(c)}
    else:c=calibration;cal_binding={'path':None,'canonical_content':c,'canonical_sha256':content_sha(c)}
    validate_calibration(c)
    if type(assume_temporal_sampling) is not bool or ab_reference not in (None,'antiparallel'):raise ValueError('explicit boolean sampling assumption and supported A/B reference required')
    if velocity_window_s is not None and (len(velocity_window_s)!=2 or not np.isfinite(velocity_window_s).all() or velocity_window_s[1]<=velocity_window_s[0]):raise ValueError('velocity_window_s requires two increasing finite SI times')
    options={'velocity_window_s':velocity_window_s,'assume_temporal_sampling':assume_temporal_sampling,'ab_reference':ab_reference,'velocity':'nonuniform3point;endpointsNaN','cross_segment':'break','phase_coverage':'complete_only'}
    impl=implementation();rows=[];tracks={};previous_key=None;run_segment_seen=set()
    for number,frame in enumerate(frames):
        row={'input_index':number,'valid_pair':False,'valid_tracking':False,'valid_velocity':False,'time_s':float('nan'),'sampling_assumption':'explicit temporal <half-box displacement' if assume_temporal_sampling else 'not_asserted','spatial_sampling_assumption':'calibration domain conditional; original wall/high-frequency resolution not independently certified','analysis_version':impl['version'],'calibration_id':c['id'],'calibration_config_sha256':content_sha(c),'reason_codes':''}
        reasons=[];data={};meta={};binding={'schema':'source-bindings-v1','sources':{},'facts':{}}
        try:
            for source in ('A','B','state','csv','packet'):
                if frame.get(source):
                    path=Path(frame[source]).resolve();binding['sources'][source]={'path':str(path),'sha256':sha(path)}
            if isinstance(frame.get('mapping'),dict):binding['sources']['mapping']={'canonical_content':frame['mapping'],'canonical_sha256':content_sha(frame['mapping'])}
            elif frame.get('mapping'):
                path=Path(frame['mapping']).resolve();binding['sources']['mapping']={'path':str(path),'sha256':sha(path)}
            arrays,meta,binding=resolve(frame);row.update({k:v for k,v in meta.items() if k!='lineage'})
            row['iteration']=meta.get('accepted_index',float('nan')) if meta.get('stage')=='sdesc' else float('nan')
            for label,a in arrays.items():
                data[label]=measure(a['m'],a['h'],a['origin'],meta['boundary'],calibration=c)
                for k,v in data[label].items():
                    if not k.startswith('_') and k!='reasons':
                        required=('valid_topology' if k in ('topo_x','topo_y') or k.startswith('topo_area_') else 'valid_geometry' if k in ('area_x','area_y','area_m2','radius_m','major_m','minor_m','axis_ratio','ellipticity') else None)
                        if required and not data[label].get(required):row[label+'_raw_'+k]=v;v=float('nan')
                        row[label+'_'+k]=v
                if meta['boundary']=='periodic_xy':
                    L=np.array(a['cells'][:2])*a['h'][:2]
                    for kind in ('area','topo'):
                        for j,axis in enumerate('xy'):
                            key=label+'_'+kind+'_'+axis
                            if key in row and np.isfinite(row[key]):row[key]=float(a['origin'][j]+(row[key]-a['origin'][j])%L[j])
                row[label+'_input_sha256']=a['sha256'];row[label+'_legacy_missing_header']=';'.join(a['legacy_missing_header'])
                reasons.extend(label+':'+r for r in data[label]['reasons'])
            row['valid_pair']=set(data)=={'A','B'}
            if not row['valid_pair']:reasons.append('missing_sublattice')
            if 'time_s' not in meta:reasons.append('missing_time')
            if 'stage' not in meta:reasons.append('missing_stage')
            elif meta['stage'] not in ('rk4','sdesc'):reasons.append('unsupported_stage')
            key=(meta.get('run_id'),meta.get('segment_id'),meta.get('stage'))
            if None in key:reasons.append('missing_tracking_identity')
            time=meta.get('time_s',float('nan'));dynamic=meta.get('stage')=='rk4'
            # Input order is authoritative; never sort an unverified sequence.
            if key!=previous_key:
                if key in run_segment_seen:reasons.append('noncontiguous_segment');tracks.pop(key,None)
                run_segment_seen.add(key)
            previous_key=key
            group=tracks.setdefault(key,{'last_time':None,'last':{},'last_error':{},'unwrapped':{},'rows':[],'broken':False,'part':0})
            eligible=bool(row['valid_pair'] and all(d.get('valid_geometry') for d in data.values()) and dynamic and np.isfinite(time) and assume_temporal_sampling and None not in key)
            if group['last_time'] is not None and time<=group['last_time']:eligible=False;reasons.append('nonincreasing_time')
            if not eligible:
                group['broken']=True;group['last_time']=None
                group['last']={};group['unwrapped']={}
            elif group['broken']:
                group['part']+=1;group['broken']=False
            row['tracking_part']=group['part']
            if row['valid_pair']:
                a=arrays['A'];L=np.array(a['cells'][:2])*a['h'][:2];periodic=meta['boundary']=='periodic_xy'
                for kind,flag in (('area','valid_geometry'),('topo','valid_topology')):
                    if not all(d.get(flag) for d in data.values()):
                        for label in ('A','B'):
                            group['last'].pop(label+'_'+kind,None);group['unwrapped'].pop(label+'_'+kind,None)
                            group['last_error'].pop(label+'_'+kind,None)
                        continue
                    # Canonical initial chart: A starts at its public wrapped
                    # coordinate; B uses the nearest image to A. Image counters
                    # always refer to the public wrapped coordinates, including
                    # B's initial alignment, never to the already aligned pos.
                    wrapped={label:np.array([row[label+'_'+kind+'_'+axis] for axis in 'xy']) for label in data}
                    positions={label:pos.copy() for label,pos in wrapped.items()}
                    if periodic:positions['B']=positions['A']+image(positions['B']-positions['A'],L)
                    delta=positions['B']-positions['A']
                    row['AB_'+kind+'_minimum_image_dx'],row['AB_'+kind+'_minimum_image_dy']=map(float,delta)
                    row['AB_'+kind+'_relative_convention']='tracked initial minimum image' if eligible else 'per-frame minimum image; continuity not asserted'
                    image_error=sum(d['radius_m'] for d in data.values())*c['accuracy_envelopes']['center_rel']
                    ambiguous=bool(periodic and np.any(abs(abs(delta)-L/2)<=image_error+L*np.finfo(float).eps*32))
                    row['AB_'+kind+'_valid_relative']=not ambiguous
                    row['AB_'+kind+'_relative_reason']='ambiguous_AB_image' if ambiguous else ''
                    row['AB_'+kind+'_dx'],row['AB_'+kind+'_dy']=(float('nan'),float('nan')) if ambiguous else map(float,delta)
                    if ambiguous:eligible=False;reasons.append('ambiguous_AB_image');reasons.append('AB_'+kind+':ambiguous_image')
                    if eligible:
                        for label,pos in positions.items():
                            ident=label+'_'+kind
                            position_error=data[label]['radius_m']*c['accuracy_envelopes']['center_rel']
                            if ident in group['last']:
                                step=pos-group['last'][ident]
                                if periodic:step=image(step,L)
                                if periodic and np.any(abs(abs(step)-L/2)<=position_error+group['last_error'].get(ident,position_error)+L*np.finfo(float).eps*32):eligible=False;reasons.append('ambiguous_temporal_image');break
                                group['unwrapped'][ident]+=step
                            else:group['unwrapped'][ident]=pos.copy()
                            group['last'][ident]=pos.copy()
                            group['last_error'][ident]=position_error
                            for axis,value in zip('xy',group['unwrapped'][ident]):row[ident+'_unwrapped_'+axis]=float(value)
                            for axis,value in zip('xy',np.rint((group['unwrapped'][ident]-wrapped[label])/L).astype(int) if periodic else (0,0)):row[ident+'_image_'+axis]=int(value)
                if all(d.get('valid_geometry') for d in data.values()):row['AB_radius_difference_m']=data['B']['radius_m']-data['A']['radius_m']
                if ab_reference=='antiparallel' and all(d.get('valid_helicity') for d in data.values()) and data['A'].get('polarity')==-data['B'].get('polarity'):
                    row['B_chi_corrected_rad']=float(wrap(data['B']['chi_raw']-np.pi));row['AB_chi_difference_rad']=float(wrap(row['B_chi_corrected_rad']-data['A']['chi_raw']))
                else:reasons.append('AB_phase_reference_or_validity_missing')
            if not eligible:
                group['broken']=True;group['last']={};group['unwrapped']={};group['last_time']=None
            if eligible and row['valid_pair']:
                for kind in ('area','topo'):
                    ka,kb='A_'+kind,'B_'+kind
                    if ka in group['unwrapped'] and kb in group['unwrapped']:
                        delta=group['unwrapped'][kb]-group['unwrapped'][ka]
                        image_error=sum(d['radius_m'] for d in data.values())*c['accuracy_envelopes']['center_rel']
                        large=periodic and (abs(delta)>=L/2-image_error-L*np.finfo(float).eps*32).any()
                        if large:reasons.append('AB_relative_image_uncertain')
                        row['AB_'+kind+'_valid_relative']=not bool(large)
                        row['AB_'+kind+'_relative_reason']='AB_relative_image_uncertain' if large else ''
                        row['AB_'+kind+'_dx'],row['AB_'+kind+'_dy']=(float('nan'),float('nan')) if large else map(float,delta)
            row['valid_tracking']=bool(eligible and not group['broken'])
            for kind in ('area','topo'):
                if 'AB_'+kind+'_valid_relative' in row:
                    row['AB_'+kind+'_relative_convention']=('ambiguous; minimum image is diagnostic only' if not row['AB_'+kind+'_valid_relative'] else 'tracked initial minimum image' if row['valid_tracking'] else 'per-frame minimum image; continuity not asserted')
            if row['valid_tracking']:group['rows'].append(len(rows));group['last_time']=time
            else:
                for label in ('A','B'):
                    for kind in ('area','topo'):
                        for component in ('unwrapped','image'):
                            for axis in 'xy':row[label+'_'+kind+'_'+component+'_'+axis]=float('nan')
        except (ValueError,KeyError,OSError,TypeError) as exc:
            reasons.append('source_or_analysis_error:'+str(exc))
            for group in tracks.values():group['broken']=True;group['last']={};group['unwrapped']={};group['last_time']=None
        binding.update(implementation=impl,calibration=cal_binding,analysis_options=options,analysis_options_sha256=content_sha(options),serialization='analysis-json-v1')
        row['source_bindings']=canonical(binding).decode();row['reason_codes']=';'.join(reasons);rows.append(row)
    # Nonuniform 3-point quadratic derivative within an intact segment only.
    for group in tracks.values():
        ids=group['rows']
        for left,idx,right in zip(ids,ids[1:],ids[2:]):
            if not (left+1==idx and idx+1==right):continue
            t=np.array([rows[k]['time_s'] for k in (left,idx,right)]);dt=t-t[1]
            for label in ('A','B'):
                for kind in ('area','topo'):
                    for axis in 'xy':
                        key=label+'_'+kind+'_unwrapped_'+axis
                        y=np.array([rows[k].get(key,np.nan) for k in (left,idx,right)])
                        if np.isfinite(y).all():rows[idx][label+'_'+kind+'_v'+axis+'_mps']=float(np.polyfit(dt/(t[2]-t[0]),y-y[1],2)[1]/(t[2]-t[0]))
            span=t[2]-t[0];x=(t-t[1])/span
            weights=np.array([-x[2]/(x[0]*(x[0]-x[2])),-(x[0]+x[2])/(x[0]*x[2]),-x[0]/(x[2]*(x[2]-x[0]))])/span
            for label in ('A','B'):
                sigma=np.array([rows[k].get(label+'_radius_m',np.nan)*c['accuracy_envelopes']['center_rel'] for k in (left,idx,right)])
                rows[idx][label+'_v_position_envelope_mps']=float(abs(weights)@sigma)
            rows[idx]['velocity_uncertainty_scope']='train spatial envelope only; no physical/time uncertainty guarantee'
            rows[idx]['valid_velocity']=all(np.isfinite(rows[idx].get(label+'_area_v'+axis+'_mps',np.nan)) for label in ('A','B') for axis in 'xy')
    if velocity_window_s is not None:
        lo,hi=velocity_window_s
        for group in tracks.values():
            ids=[i for i in group['rows'] if lo<=rows[i]['time_s']<=hi]
            if len(ids)<2 or any(b!=a+1 for a,b in zip(ids,ids[1:])):continue
            t=np.array([rows[i]['time_s'] for i in ids]);span=t[-1]-t[0]
            for label in ('A','B'):
                for kind in ('area','topo'):
                    y=np.array([[rows[i].get(label+'_'+kind+'_unwrapped_'+axis,np.nan) for axis in 'xy'] for i in ids])
                    if not np.isfinite(y).all():continue
                    coef=np.polyfit((t-t[0])/span,y-y[0],1);fit=(t-t[0])[:,None]/span*coef[0]+coef[1];err=float(np.linalg.norm(fit-(y-y[0]),axis=1).max())
                    for i in ids:
                        rows[i][label+'_'+kind+'_window_vx_mps'],rows[i][label+'_'+kind+'_window_vy_mps']=map(float,coef[0]/span)
                        rows[i][label+'_'+kind+'_window_residual_m']=err
                        rows[i]['velocity_window_s']=canonical(list(velocity_window_s)).decode()
    # Union columns, numeric missing values are explicit NaN, not zeros.
    names=list(dict.fromkeys(k for row in rows for k in row))
    for name in ['A_area_vx_mps','A_area_vy_mps','B_area_vx_mps','B_area_vy_mps','AB_radius_difference_m','AB_chi_difference_rad']:
        if name not in names:names.append(name)
    numeric=('Q','area_x','area_y','topo_x','topo_y','radius_m','area_m2','major_m','minor_m','axis_ratio','ellipticity','axis_rad','chi_raw','chi_rad','coherence','phase_rms','phase_p95','phase_coverage','topo_area_distance_m','area_unwrapped_x','area_unwrapped_y','topo_unwrapped_x','topo_unwrapped_y','area_image_x','area_image_y','topo_image_x','topo_image_y')
    for row in rows:
        for kind in ('area','topo'):
            row.setdefault('AB_'+kind+'_valid_relative',False)
            row.setdefault('AB_'+kind+'_relative_reason','missing_or_invalid_centers')
            for suffix in ('dx','dy','minimum_image_dx','minimum_image_dy'):row.setdefault('AB_'+kind+'_'+suffix,float('nan'))
        for label in ('A','B'):
            for key in numeric:row.setdefault(label+'_'+key,float('nan'))
            for flag in ('valid_geometry','valid_topology','valid_axis','valid_helicity'):row.setdefault(label+'_'+flag,False)
    names=list(dict.fromkeys(names+[k for row in rows for k in row]+[label+'_'+key for label in ('A','B') for key in numeric]+[label+'_'+flag for label in ('A','B') for flag in ('valid_geometry','valid_topology','valid_axis','valid_helicity')]))
    return rows, names


def _write_csv(rows, output, fieldnames):
    output=Path(output)
    with output.open('x',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=fieldnames,restval=float('nan'));writer.writeheader();writer.writerows(rows)


@tracked_reads
def analyze_ovf(frames,output,*,calibration=None,assume_temporal_sampling=False,ab_reference=None,velocity_window_s=None):
    """Analyze explicit frames and create one exclusive CSV (legacy contract)."""
    rows,names=_analyze_rows(frames,calibration=calibration,assume_temporal_sampling=assume_temporal_sampling,
                       ab_reference=ab_reference,velocity_window_s=velocity_window_s)
    _write_csv(rows,output,names)
    return rows
