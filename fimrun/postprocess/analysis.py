"""Finite offline facade. Selection never reconstructs historical state segments."""
from .session import tracked_reads, report, ProgressFrames
import copy
import json
import math
import textwrap
from html import escape
from pathlib import Path
from types import MappingProxyType

from .pipeline import _analyze_rows, _write_csv, frames_from_state, resolve
from .io import read_state

_METRICS = ('center', 'topology_center', 'radius', 'shape', 'axis', 'helicity',
            'topology', 'relative', 'velocity')
_DEFAULT = ('center', 'radius', 'shape', 'helicity')
_TOKEN = object()


def _finite(value):
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def _freeze(value):
    if isinstance(value, dict):
        return MappingProxyType({k: _freeze(v) for k, v in value.items()})
    if isinstance(value, (tuple, list)):
        return tuple(_freeze(v) for v in value)
    return value


def _validate(metric, sublattice):
    if metric not in _METRICS:
        raise ValueError('Unknown metric: ' + str(metric))
    if sublattice not in ('A', 'B', 'both'):
        raise ValueError('sublattice must be A, B or both')
    if metric == 'relative' and sublattice != 'both':
        raise ValueError('relative requires sublattice=both')


def _columns(metric, label):
    p = label + '_'
    return {
        'center': [(p+'area_x', p+'valid_geometry'), (p+'area_y', p+'valid_geometry')],
        'topology_center': [(p+'topo_x', p+'valid_topology'), (p+'topo_y', p+'valid_topology')],
        'radius': [(p+'radius_m', p+'valid_geometry')],
        'shape': [(p+k, p+'valid_geometry') for k in ('major_m', 'minor_m', 'axis_ratio', 'ellipticity')],
        'axis': [(p+'axis_rad', p+'valid_axis')],
        'helicity': [(p+'chi_rad', p+'valid_helicity')],
        'topology': [(p+'Q', p+'valid_topology')],
        'relative': [('AB_area_dx', 'AB_area_valid_relative'), ('AB_area_dy', 'AB_area_valid_relative'),
                     ('AB_topo_dx', 'AB_topo_valid_relative'), ('AB_topo_dy', 'AB_topo_valid_relative'),
                     ('AB_radius_difference_m', 'pair_geometry'), ('AB_chi_difference_rad', 'pair_helicity')],
        'velocity': [(p+'area_vx_mps', 'valid_velocity'), (p+'area_vy_mps', 'valid_velocity')],
    }[metric]


def _valid(row, flag):
    if flag.startswith('pair_'):
        suffix = 'valid_' + flag.removeprefix('pair_')
        key = 'AB_chi_difference_rad' if suffix == 'valid_helicity' else 'AB_radius_difference_m'
        return bool(row.get('A_'+suffix) and row.get('B_'+suffix) and _finite(row.get(key)))
    return row.get(flag) is True


def _choices(frames):
    facts = []
    for number,frame in enumerate(frames):
        report('输入选择校验',number,len(frames))
        try:
            arrays, meta, binding = resolve(frame)
            facts.append((None, meta, binding))
        except (ValueError, KeyError, OSError, TypeError):
            # No selector: the original analysis retains this submitted failure.
            facts.append(None)
    return facts


def _state_frames(path):
    state, _ = read_state(path)
    frames = frames_from_state(path)  # Validate the ENTIRE inventory first.
    if not state.get('segments') or not frames:
        raise ValueError('State requires uniquely bound frames in its last segment; use explicit frames with evidence')
    latest = state['segments'][-1]
    if latest.get('kind') not in ('rk4', 'sdesc') or not latest.get('id'):
        raise ValueError('Unsupported or unidentified last state segment')
    facts = []
    for number,frame in enumerate(frames):
        report('输入选择校验',number,len(frames))
        arrays, meta, binding = resolve(frame)  # Conflicts reject the whole container.
        if (meta.get('segment_id'), meta.get('stage'), meta.get('run_id')) != (latest['id'], latest['kind'], state.get('run_id')):
            raise ValueError('Historical or conflicting state frames; use explicit frames with evidence')
        evidence = [a['fields'].get('segment_id') for a in arrays.values() if a['fields'].get('segment_id')]
        if 'csv' in binding['sources']:
            # resolve has already established a unique, hash-bound CSV row.
            evidence.append(binding['sources']['csv']['row_key']['segment_id'])
        if not evidence or any(value != latest['id'] for value in evidence):
            raise ValueError('State frame has no independent unique last-segment binding; use explicit frames with evidence')
        facts.append((None, meta, binding))
    return frames, facts


@tracked_reads
def analyze(source, *, stage=None, segment=None, calibration=None,
            assume_temporal_sampling=False, ab_reference=None, velocity_window_s=None):
    """Return an in-memory Analysis. No file writes, solver, Native or service.

    State input is restricted to inventories independently bound to the last
    segment. A visible running directory freezes its committed OVF manifest.
    Explicit frames retain their input order and legacy failure rows.
    """
    if stage is not None and stage not in ('rk4', 'sdesc'):
        raise ValueError('stage must be rk4, sdesc or None')
    if segment is not None and (not isinstance(segment, str) or not segment):
        raise ValueError('segment must be a nonempty exact id or None')
    if isinstance(source, (str, Path)):
        if Path(source).is_dir():
            from ..output_snapshot import frames_from_output
            frames = frames_from_output(source)
            facts = _choices(frames)
            if any(fact is None for fact in facts):
                raise ValueError('Conflicting or invalid committed output frame')
        else:
            frames, facts = _state_frames(source)
    elif isinstance(source, list) and all(isinstance(f, dict) for f in source):
        frames = copy.deepcopy(source)
        facts = _choices(frames)
    else:
        raise TypeError('source must be a state path or a concrete list of frame dictionaries, not rows')
    # Rows from generate_demo are not frame declarations.
    if frames and not any('A' in f or 'B' in f for f in frames):
        raise TypeError('Frame declarations require explicit A/B paths; analysis rows are not frames')
    selectors = {'stage': stage, 'segment_id': segment}
    selected = list(range(len(frames)))
    for key, value in selectors.items():
        if value is not None:
            if any(facts[i] is None or facts[i][1].get(key) is None for i in selected):
                raise ValueError('Cannot uniquely select '+key+' for every submitted frame')
            selected = [i for i in selected if facts[i][1].get(key) == value]
    if frames and not selected:
        raise ValueError('Selection has no matching frames')
    for key, value in selectors.items():
        known = {facts[i][1].get(key) for i in selected if facts[i] is not None}
        if value is None and len(known) > 1:
            raise ValueError('Ambiguous '+key+'; select one exact value')
    chosen = [frames[i] for i in selected]
    rows, columns = _analyze_rows(ProgressFrames(chosen), calibration=calibration,
                         assume_temporal_sampling=assume_temporal_sampling,
                         ab_reference=ab_reference, velocity_window_s=velocity_window_s)
    # Prevent selection preflight / analysis races from silently changing scope.
    for row, i in zip(rows, selected):
        if facts[i] is not None:
            expected = facts[i][2]['sources']
            actual = json.loads(row['source_bindings'])['sources']
            if any(actual.get(k, {}).get('sha256') != v['sha256'] for k, v in expected.items() if 'sha256' in v):
                raise ValueError('Source changed after selection; submit the request again')
    paths = set()
    for frame in frames:
        for key in ('A', 'B', 'state', 'csv', 'packet', 'mapping'):
            if isinstance(frame.get(key), (str, Path)):
                paths.add(str(Path(frame[key]).resolve()))
        mapping = frame.get('mapping')
        if isinstance(mapping, dict):
            for evidence in mapping.get('evidence', []):
                if isinstance(evidence, dict) and evidence.get('path'):
                    paths.add(str(Path(evidence['path']).resolve()))
    if isinstance(source, (str, Path)):
        paths.add(str(Path(source).resolve()))
    for row in rows:
        for entry in json.loads(row['source_bindings'])['sources'].values():
            if isinstance(entry, dict) and entry.get('path'):
                paths.add(str(Path(entry['path']).resolve()))
    return Analysis(_TOKEN, rows, selected, paths, columns)


class Analysis:
    """Immutable public rows and source indices; displays never rerun analysis."""
    def __init__(self, token, rows, indices, paths, columns):
        if token is not _TOKEN:
            raise TypeError('Use analyze() to obtain an Analysis')
        self._rows = tuple(copy.deepcopy(rows))
        self._indices = tuple(indices)
        self._paths = frozenset(paths)
        self._columns = tuple(columns)

    @property
    def rows(self):
        return _freeze(self._rows)

    @property
    def source_indices(self):
        return self._indices

    @property
    def csv_source(self):
        """Loaded CSV identity, or None for a fresh analysis."""
        return _freeze(getattr(self, '_csv_source', None))

    def _destination(self, path):
        requested = Path(path).expanduser()
        if requested.is_symlink():
            raise FileExistsError(str(requested))
        p = requested.resolve()
        if str(p) in self._paths:
            raise ValueError('Output conflicts with an input source')
        if p.exists() or p.is_symlink():
            raise FileExistsError(str(p))
        return p

    def to_csv(self, path):
        """Create a complete SI audit CSV, including original source_index."""
        p = self._destination(path)
        rows = [dict(r, source_index=i) for r, i in zip(self._rows, self._indices)]
        _write_csv(rows, p, list(self._columns)+["source_index"])
        return p

    def table(self, *, metrics=None, sublattice='both', limit=None):
        """Return HTML; invalid cells remain NaN with flags and reasons."""
        from IPython.display import HTML
        metrics = _DEFAULT if metrics is None else tuple(metrics)
        cols = ['source_index', 'input_index', 'stage', 'segment_id', 'time_s', 'iteration']
        labels = ('A', 'B') if sublattice == 'both' else (sublattice,)
        if sublattice not in ('A', 'B', 'both'):
            raise ValueError('sublattice must be A, B or both')
        for metric in metrics:
            _validate(metric, sublattice)
            for label in labels[:1] if metric == 'relative' else labels:
                for key, flag in _columns(metric, label):
                    cols += [key, flag]
        cols = list(dict.fromkeys(cols + ['reason_codes']))
        text = ['<div style="overflow-x:auto"><table><caption>SI audit values; NaN is not zero</caption><tr>']
        text += ['<th>'+escape(c)+'</th>' for c in cols]
        text.append('</tr>')
        if limit is not None and (type(limit) is not int or limit < 1): raise ValueError('limit must be positive or None')
        for r, idx in list(zip(self._rows, self._indices))[:limit]:
            shown = dict(r, source_index=idx)
            for metric in metrics:
                for label in labels[:1] if metric == 'relative' else labels:
                    for key, flag in _columns(metric, label):
                        shown[flag] = _valid(r, flag)
                        if not _valid(r, flag):
                            shown[key] = math.nan
            text += ['<tr>'] + ['<td>'+escape(str(shown.get(c, math.nan)))+'</td>' for c in cols] + ['</tr>']
        text.append('</table></div>')
        if not self._rows:
            text.append('<p>No submitted frames.</p>')
        return HTML(''.join(text))

    def _context_lines(self, metric=None):
        def values(key):
            return ', '.join(sorted({str(r.get(key)) if r.get(key) is not None else 'unknown' for r in self._rows})) or 'unknown'
        options = [json.loads(r['source_bindings']).get('analysis_options', {}) for r in self._rows]
        def option(key):
            return ', '.join(sorted({json.dumps(o.get(key), separators=(',', ':')) for o in options})) or 'unknown'
        indices = ','.join(map(str, self._indices)) if len(self._indices) <= 12 else str(self._indices[0])+'..'+str(self._indices[-1])+' (see CSV source_index for exact selection)'
        lines = ['run='+values('run_id')+'; stage='+values('stage')+'; segment='+values('segment_id'),
                 'Selected source indices: '+(indices or 'none')+'; submitted rows='+str(len(self._rows)),
                 'ab_reference='+option('ab_reference')+'; temporal_sampling_asserted='+option('assume_temporal_sampling'),
                 'velocity_window_s='+option('velocity_window_s')+'; calibration='+values('calibration_id')]
        if metric == 'helicity':
            lines.append('Independent A/B phase references (valid chi_rad); no B-pi correction in this plot.')
        elif metric == 'relative':
            ref = {o.get('ab_reference') for o in options}
            lines.append('Phase reference: antiparallel; B-pi correction only where valid.' if ref == {'antiparallel'} else 'Phase reference: unspecified; no corrected phase comparison.' if ref <= {None} else 'Phase reference: mixed declarations; inspect CSV source_bindings.')
            lines.append('Area branch: '+values('AB_area_relative_convention'))
            lines.append('Topology branch: '+values('AB_topo_relative_convention'))
        if self.csv_source is not None:
            lines.append('Loaded CSV: '+self.csv_source['path']+'; SHA256='+self.csv_source['sha256']+'; original OVF/state not reverified')
        return [part for line in lines for part in textwrap.wrap(line, width=105, break_long_words=True)]

    def plot(self, metric, *, sublattice='both', output=None, trajectory=None, corrected=False):
        """Plot cached measurements; centers default to equal-scale segment displacement XY."""
        from IPython.display import SVG
        _validate(metric, sublattice)
        if corrected and metric != 'helicity': raise ValueError('corrected applies only to helicity')
        center = metric in ('center', 'topology_center')
        relative_xy = center and trajectory is None
        if trajectory is None: trajectory = center
        if trajectory and not center: raise ValueError('trajectory applies only to centers')
        labels = ('A','B') if sublattice == 'both' else (sublattice,)
        rows = self._rows
        stage = rows[0].get('stage') if rows else None
        has_clock = bool(rows) and stage == 'rk4' and all(_finite(r.get('time_s')) for r in rows)
        iterations = bool(rows) and stage == 'sdesc' and all(_finite(r.get('iteration')) for r in rows)
        axis = '时间 / ps' if has_clock else '接受迭代 / 次' if iterations else '输入帧序号（非物理时间）'
        def clock(i,r): return r['time_s']*1e12 if has_clock else r['iteration'] if iterations else self._indices[i]
        names = dict(center='面积中心位移',topology_center='拓扑中心位移',radius='半径',shape='形状',axis='长轴方向',helicity='旋向角 helicity',topology='拓扑荷',relative='A/B 相对关系',velocity='速度')
        title = names[metric] + (' · XY轨迹' if trajectory else '') + (' · B按反平行参考修正' if corrected else '')
        kind = 'area' if metric == 'center' else 'topo'
        tracked = center and any(r.get('valid_tracking') for r in rows)
        groups = {}
        invalid = set()
        for label in labels[:1] if metric == 'relative' else labels:
            columns = _columns(metric,label)
            if center:
                columns = [(label+'_'+kind+'_x',columns[0][1])] if trajectory else [(label+'_'+kind+'_'+a,columns[0][1]) for a in 'xy']
            for key, flag in columns:
                quantity = key.removeprefix('AB_').removeprefix('A_').removeprefix('B_')
                if center: quantity = 'XY' if trajectory else '位移'
                seq=[]; references={}; previous_identity=None; previous_t=None
                for i,row in enumerate(rows):
                    valid=_valid(row,flag)
                    identity=(row.get('run_id'),row.get('segment_id'),row.get('stage'),row.get('tracking_part'))
                    t=clock(i,row)
                    if previous_identity != identity or (previous_t is not None and _finite(t) and t<=previous_t): references={}
                    previous_identity,previous_t=identity,t
                    if center:
                        prefix=label+'_'+kind+('_unwrapped_' if tracked else '_')
                        if tracked or relative_xy: valid=valid and row.get('valid_tracking') is True
                        if not trajectory and row.get('boundary')=='periodic_xy' and not tracked: valid=False
                        px,py=row.get(prefix+'x',math.nan),row.get(prefix+'y',math.nan)
                        if trajectory:
                            if relative_xy:
                                if valid and _finite(px) and _finite(py) and 'origin' not in references:references['origin']=(px,py)
                                ox,oy=references.get('origin',(math.nan,math.nan));xx,yy=(px-ox)*1e9,(py-oy)*1e9
                            else:xx,yy=px*1e9,py*1e9
                        else:
                            value=px if key.endswith('_x') else py
                            if valid and _finite(value) and 'zero' not in references: references['zero']=value
                            xx,yy=t,(value-references.get('zero',math.nan))*1e9
                    else:
                        xx,yy=t,row.get(key,math.nan)
                        if corrected and label=='B': yy=row.get('B_chi_corrected_rad',math.nan)
                        if any(s in key for s in ('radius_m','major_m','minor_m','_difference_m','_dx','_dy')): yy*=1e9
                    if valid and _finite(xx) and _finite(yy): seq.append((xx,yy,identity))
                    else:
                        seq.append(None);references={};invalid.add(label+' '+quantity)
                groups.setdefault(quantity,[]).append((key,seq))
        context=self._context_lines(metric)
        good=sum(any(_valid(row,flag) for label in labels for _,flag in _columns(metric,label)) for row in rows)
        reasons=sorted({row.get('reason_codes','') for row in rows if row.get('reason_codes')})
        context += [f'Valid selected rows: {good}/{len(rows)}', 'Reasons: '+('; '.join(reasons) or 'none')]
        if not has_clock: context += ['source input index (not physical time)']
        # Full source audit stays embedded for standalone exports, out of the visual plot.
        note=f'所选 {len(rows)} 帧；缺失/无效数据留空，不作0'
        if invalid: note='存在缺失/无效的 '+', '.join(sorted(invalid))+'；对应值留空，详见数据表'
        if relative_xy: note += ' · Δx–Δy等比例；各有效连续段以首帧为(0,0)；起点圆点/终点方块'
        if center and not relative_xy: note += ' · '+(('等比例XY；起点圆点/终点方块' if tracked else '等比例XY位置散点；未声明有效跟踪，不连轨迹') if trajectory else '各有效连续段以首帧为0；'+('周期解包中心' if tracked else '无有效跟踪时不推断跨界位移'))
        if relative_xy and not tracked: note += ' · 无有效跟踪或采样保证，位移不可用；可显式选择绝对位置散点'
        if metric=='helicity': note += ' · 原始A/B角度；+π与−π同向，折返不是翻转' if not corrected else ' · 仅有效反平行参考下显示B−π'
        if not has_clock and stage=='rk4': note += ' · Missing time: input index scatter only; no inferred clock or velocity'
        panels=max(1,len(groups)); xy=bool(center and trajectory)
        width=800; panel_h=590 if xy else 300; offset=110
        svg=[f'<svg xmlns="http://www.w3.org/2000/svg" width="800" height="{offset+panels*panel_h}" viewBox="0 0 800 {offset+panels*panel_h}" role="img">',
             '<desc>'+escape('\n'.join(context))+'</desc>',f'<rect width="800" height="{offset+panels*panel_h}" fill="white"/>','<g font-family="system-ui,sans-serif" fill="#182333">',f'<text x="26" y="32" font-size="20">{escape(title)}</text>']
        for j,line in enumerate(textwrap.wrap(note,55)): svg.append(f'<text x="26" y="{58+j*18}" font-size="13">{escape(line)}</text>')
        human={'chi_rad':'旋向角','Q':'拓扑荷','radius_m':'半径','major_m':'长半轴','minor_m':'短半轴','axis_ratio':'轴比','ellipticity':'椭圆度','axis_rad':'长轴方向','area_vx_mps':'vx','area_vy_mps':'vy'}
        for panel,(quantity,group) in enumerate(groups.items()):
            top=offset+panel*panel_h+25; ph=450 if xy else 170; pw=450 if xy else 610; left=140 if xy else 100
            points=[p for _,seq in group for p in seq if p is not None]
            xmin,xmax=(min(p[0] for p in points),max(p[0] for p in points)) if points else (0.,1.)
            ymin,ymax=(min(p[1] for p in points),max(p[1] for p in points)) if points else (0.,1.)
            dx,dy=max(xmax-xmin,1e-6),max(ymax-ymin,1e-6)
            if xy: dx=dy=max(dx,dy)
            cx,cy=(xmin+xmax)/2,(ymin+ymax)/2;dx*=1.12;dy*=1.12
            if metric=='helicity':cy=0.;dy=2.2*math.pi
            xmin,ymin=cx-dx/2,cy-dy/2
            pixel=lambda p:(left+(p[0]-xmin)*pw/dx,top+ph-(p[1]-ymin)*ph/dy)
            unit='m/s' if 'mps' in quantity else 'rad' if 'chi' in quantity or 'axis_rad' in quantity else '1' if quantity in ('Q','axis_ratio','ellipticity') else 'nm'
            ylabel='Δy' if relative_xy else 'Y' if xy else human.get(quantity,quantity)
            svg.append(f'<text x="{left}" y="{top-12}" font-size="14">{escape(ylabel)} / {unit}</text>')
            svg.append(f'<path d="M{left} {top}V{top+ph}H{left+pw}" fill="none" stroke="#777"/>')
            for j in range(5):
                xx=left+pw*j/4;xtick=format(xmin+dx*j/4,'.8g' if xy else '.4g');svg.append(f'<text x="{xx}" y="{top+ph+24}" text-anchor="middle" font-size="12">{xtick}</text>')
                yy=top+ph-ph*j/4
                if metric=='helicity':
                    v=(-math.pi,-math.pi/2,0,math.pi/2,math.pi)[j];yy=pixel((0,v))[1];tick=('−π','−π/2','0','π/2','π')[j]
                else:tick=format(ymin+dy*j/4,'.8g' if xy else '.4g')
                svg.append(f'<text x="{left-12}" y="{yy+4}" text-anchor="end" font-size="12">{tick}</text>')
            for n,(key,seq) in enumerate(group):
                isb=key.startswith('B_');color='#d36316' if isb else '#1864ab';dash=('8 3 2 3' if isb else '2 3') if center and not trajectory and key.endswith('_y') else '7 4' if isb else 'none'
                label=('B' if isb else 'A')+' · '+('Δx' if center and not trajectory and key.endswith('_x') else 'Δy' if center and not trajectory else '面积中心' if metric=='center' else '拓扑中心' if metric=='topology_center' else human.get(quantity,quantity))
                if corrected and isb:label+='（反平行修正）'
                lx,ly=left+(n%2)*300,top+ph+62+18*(n//2)
                svg.append(f'<path d="M{lx},{ly-4}h24" stroke="{color}" stroke-dasharray="{dash}"/>')
                svg.append(f'<text x="{lx+32}" y="{ly}" font-size="13" fill="{color}">{escape(label)}</text>')
                previous=None;validpts=[];distance=0.
                for point in seq:
                    if point is None:previous=None;distance=0.;continue
                    xypt=pixel(point);validpts.append(xypt)
                    connect=(tracked if xy else has_clock or iterations) and previous and point[2]==previous[0][2] and (xy or point[0]>previous[0][0]) and (metric!='helicity' or abs(point[1]-previous[0][1])<=math.pi) and (metric!='axis' or abs(point[1]-previous[0][1])<=math.pi/2)
                    if connect:svg.append(f'<path data-series="{escape(key)}" d="M{previous[1][0]},{previous[1][1]}L{xypt[0]},{xypt[1]}" stroke="{color}" stroke-dasharray="{dash}" stroke-dashoffset="{-distance}" fill="none"/>')
                    # Sparse markers retain direction clarity without 2001 giant dots.
                    if not connect:svg.append(f'<circle data-series="{escape(key)}" cx="{xypt[0]}" cy="{xypt[1]}" r="2.2" fill="{color}"/>')
                    distance=distance+math.hypot(xypt[0]-previous[1][0],xypt[1]-previous[1][1]) if connect else 0.
                    previous=(point,xypt)
                if xy and validpts:
                    a,b=validpts[0],validpts[-1];svg += [f'<circle cx="{a[0]}" cy="{a[1]}" r="5" fill="none" stroke="{color}"/>',f'<rect x="{b[0]-4}" y="{b[1]-4}" width="8" height="8" fill="{color}"/>']
            if not points:svg.append(f'<text x="{left+20}" y="{top+ph/2}">No valid samples; inspect table reasons</text>')
            svg.append(f'<text x="{left}" y="{top+ph+44}" font-size="13">{escape("Δx / nm（等比例）" if relative_xy else "X / nm（等比例）" if xy else axis)}</text>')
        svg.append('</g></svg>');text=''.join(svg)
        if output is not None:
            with self._destination(output).open('x') as f:f.write(text)
        return SVG(text)

    def show(self):
        """Concise report; complete source audit remains in collapsed details."""
        from IPython.display import HTML
        count=len(self._rows);valid=sum(bool(r.get('A_valid_geometry') and r.get('B_valid_geometry')) for r in self._rows)
        text=['<div style="font-family:system-ui;line-height:1.6"><h3>磁结构分析</h3>',f'<p>帧数 {count} · 有效几何 {valid}/{count}</p>']
        if self.csv_source is not None:
            text.append('<p>从已保存CSV加载；保留历史来源记录，未重新读取或校验原始OVF/state。</p>')
        if not count:text.append('<p>No submitted frames</p>')
        clocks=[r.get('time_s') for r in self._rows if _finite(r.get('time_s'))]
        if clocks:text.append(f'<p>物理时间 {min(clocks)*1e12:.3f}–{max(clocks)*1e12:.3f} ps</p>')
        invalid=[]
        for flag in ('valid_geometry','valid_helicity'):
            for label in ('A','B'):
                n=sum(r.get(label+'_'+flag) is not True for r in self._rows)
                if n:invalid.append(f"{label} {'几何' if flag=='valid_geometry' else '旋向角'}: {n}帧不可用")
        if invalid:text.append('<p role="status">'+escape('；'.join(invalid))+'；不把无效值作0。</p>')
        text += [self.plot(m).data for m in _DEFAULT]
        text.append('<details><summary>数据预览与来源/有效性详情</summary>')
        text.extend('<p>'+escape(line)+'</p>' for line in self._context_lines())
        reasons=sorted({r.get('reason_codes','') for r in self._rows if r.get('reason_codes')})
        text.append('<p>'+escape(' | '.join(reasons) or '无诊断原因')+'</p>')
        text.append(self.table(limit=12).data)
        text.append('<p>仅预览前12帧；完整SI值、来源和有效性使用to_csv导出。经验校准适用域及采样假设不构成普遍精度保证。</p></details></div>')
        return HTML(''.join(text))
