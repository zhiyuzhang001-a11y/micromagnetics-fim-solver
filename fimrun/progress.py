"""Throttled, evaluation-free notebook progress. No background solver reads."""
import html
import time


def simulation_snapshot(sim, residual=None):
    """Only accepted arrays/caches; never call evaluate or a native solver."""
    segment = sim.segments[-1] if sim.segments else None
    restored = bool(getattr(sim, '_restored_pending', False))
    static = bool(segment and segment['kind'] == 'sdesc') and not restored
    stop = getattr(sim, '_preview_stop', None) if static else None
    if residual is None and sim._field is not None:
        residual = sim._residual(sim._m, sim._field)
    gates = []
    for i, label in enumerate(sim.labels):
        ms = (getattr(sim.model.material, label) if len(sim.labels) > 1 else sim.model.material).Ms
        r = float(residual[i]) if residual is not None else None
        q = r / ms if r is not None else None
        rt, qt = (stop.get('tolerance'), stop.get('mxh')) if stop else (None, None)
        gates.append(dict(label=label, residual_Apm=r, mxh=q, residual_limit_Apm=rt, mxh_limit=qt,
                          residual_pass=None if r is None or rt is None else r <= rt,
                          mxh_pass=None if q is None or qt is None else q <= qt))
    phase = 'restored' if restored else segment['status'] if segment else 'initialized'
    start = segment['t_start'] if segment and not restored else sim.time
    elapsed = max(0., time.monotonic() - getattr(sim, '_stage_started', time.monotonic()))
    if segment and segment['status']!='running':
        elapsed=getattr(sim,'_stage_elapsed',elapsed)
    target = getattr(sim, '_target_steps', None) if segment and not static and not restored else None
    steps = getattr(sim, '_active_steps', 0) if segment and not restored else 0
    sd = sim._sd if static else None
    if sd and sd.get('criterion', stop) != stop:
        sd = None  # New thresholds must not inherit an old criterion's streak.
    return dict(phase=phase, kind='static' if static else 'dynamic', step=steps,
                target_steps=target, physical_time_s=sim.time, stage_start_s=start,
                stage_elapsed_s=sim.time-start if not static else None,
                stage_duration_s=(target*sim.solver.dt) if target is not None and sim.solver.dt is not None else None,
                percent=(100.*steps/target if target else 100. if phase == 'completed' and target == 0 else 0.) if target is not None else None,
                elapsed_s=elapsed, convergence=gates,
                consecutive=(sd or {}).get('consecutive', 0) if static else None,
                consecutive_required=stop.get('consecutive') if stop else None,
                residual_checked=(sd or {}).get('residual_checked', False) if static else None,
                error=segment.get('error') if segment else None)


def simulation_text(s):
    status = {'restored':'已恢复 · 待运行','initialized':'初态 · 指标待计算','running':'运行中','completed':'已完成',
              'converged':'已收敛','cancelled':'已中断','failed':'失败'}.get(s['phase'], s['phase'])
    parts = [status]
    if s['kind'] == 'static':
        parts += [f"接受迭代 {s['step']}", f"连续达标 {s['consecutive']}/{s['consecutive_required']}"]
    elif s['target_steps'] is not None:
        parts += [f"本次 {s['stage_elapsed_s']*1e12:.3f}/{s['stage_duration_s']*1e12:.3f} ps ({s['percent']:.1f}%)",
                  f"接受步 {s['step']}/{s['target_steps']}", f"累计 {s['physical_time_s']*1e12:.3f} ps"]
    for g in s['convergence']:
        q, r = g['mxh'], g['residual_Apm']
        text = f"{g['label']} mxh {q:.3e} · Residual {r:.3e} A/m" if q is not None else f"{g['label']} 指标待计算"
        if s['kind'] == 'static' and g['residual_limit_Apm'] is not None:
            text += f" / 阈值 {g['residual_limit_Apm']:.3e} A/m"
            if g['mxh_limit'] is not None: text += f" · mxh阈值 {g['mxh_limit']:.3e}"
            text += ' · 本态达标' if g['residual_pass'] and (g['mxh_pass'] is not False) else ' · 尚未达标'
        parts.append(text)
    parts.append(f"耗时 {s['elapsed_s']:.1f} s")
    if s.get('error'): parts.append(str(s['error']))
    if s['phase'] == 'running': parts.append('等待下一接受态/原生调用返回；保存与显示频率独立')
    return ' | '.join(parts)


class Progress:
    """Display one replaceable HTML region only in an actual IPython kernel."""
    def __init__(self, label, *, interval=1., callback=None):
        self.label, self.interval, self.callback = label, interval, callback
        self.started, self.last = time.monotonic(), -float('inf')
        self.handle = None
        self.enabled = False
        try:
            from IPython import get_ipython
            self.enabled = getattr(get_ipython(), 'kernel', None) is not None
        except ImportError:
            pass

    def update(self, text, *, force=False):
        now = time.monotonic()
        if not force and now-self.last < self.interval: return
        self.last = now
        if self.callback is not None: self.callback(text)
        if self.enabled:
            try:
                from IPython.display import display, HTML
                parts=text.split(' | ')
                gates=[p for p in parts if ' mxh ' in p]
                heading=' · '.join(p for p in parts if ' mxh ' not in p)
                body='<div>'+html.escape(self.label+' · '+heading)+'</div>'
                body+=''.join('<div style="padding-top:4px">'+html.escape(p)+'</div>' for p in gates)
                value = HTML('<div role="status" style="padding:10px;border-left:3px solid #4285ab;line-height:1.7">'+body+'</div>')
                if self.handle is None: self.handle = display(value, display_id=True)
                else: self.handle.update(value)
            except Exception:
                # A renderer failure never aborts a scientific operation.
                self.enabled = False

    def count(self, stage, done, total, *, force=False):
        pct = f' ({100*done/total:.1f}%)' if total else ''
        self.update(f'{stage} {done}/{total}{pct} · 耗时 {time.monotonic()-self.started:.1f} s', force=force)
