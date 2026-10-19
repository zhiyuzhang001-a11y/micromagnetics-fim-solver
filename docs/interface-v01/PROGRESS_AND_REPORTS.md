# 进度、恢复与离线报告

动态进度以本次duration为目标，累计物理时间单列；保存频率、网页刷新和历史帧位置互相独立。静态显示真实接受迭代及A/B mxh（无量纲）、Residual（A/m）、阈值和连续达标数；单态达标不等于已收敛。长原生调用期间只能等待返回，界面不会伪造进度或保证立即中断。网页暂停只停止观看。

## 同名sim安全恢复

先确认要保留的旧工作；下面的backup必须是新文件名。目标验证或备份失败时原sim仍可继续使用，不先close。恢复会带回保存时的磁态、时间、电流和求解设置，后续按目标显式设置电流。

```python
sim = sim.restore('pre_s.state', output_dir='restart_from_relax',
                  backup='before_restart.state')
# 从relax状态重跑前按需设置sim.set_current(...)
sim.run(name='drive', dt=100e-15, duration=1e-9)
```

新对象替换变量指向，旧会话在成功交接后关闭；输出用新目录/名字，不覆盖旧研究结果。保存的电流可能非零，静态前必须显式set_current(None)。传统NotebookSimulation.load仍创建新对象，不能在未经验证时无条件先关闭旧sim。

## 分析自己的输出

```python
from pathlib import Path
import fimrun.postprocess as pp
frames = pp.frames_from_state(Path('sot_0.1_0.1.state'))
results = pp.analyze(frames, assume_temporal_sampling=True,
                     ab_reference='antiparallel')
results.show()
results.plot('center', sublattice='both')
# 显式查看各位移随时间：
results.plot('center', trajectory=False)
results.plot('velocity')
results.to_csv('new_analysis.csv')
```

不需要generate_demo或inputs.json。OVF提供磁结构，CSV/state绑定时间、阶段和来源；完整库存必须未改动，自动state入口不能重建任意旧阶段。旧文件需明确A/B帧列表及真实来源证据。analyze返回Analysis，analyze_ovf保留返回列表的旧合同。

相邻位移小于半周期盒的采样假设影响周期解包/速度；antiparallel只为A/B相位比较选择参考。原始角度仍默认，+π/−π等价；修正图必须显式corrected=True且满足有效性门。center默认横轴Δx、纵轴Δy（nm），各有效连续段首帧为(0,0)，A/B分色且等比例，标明起终点。trajectory=False显式显示位移随时间；trajectory=True保留旧版绝对XY位置图。无效数据留空不作0，科学审计SI值完整保留在CSV和详情。

同一内核、同一preview_port是一个自动跟随通道：新建/载入的空闲sim接管该通道，旧模拟磁态与原生资源不关闭。不同端口独立；正在运行的旧模拟和其他内核/程序不会被抢占。页面每2秒检查（后台接受态最多约每1秒发布），与CSV/OVF保存频率独立。关闭后同一内核重开通道保留来源能力标识，原页面可自动重新连接；失败标明非实时，释放冲突后sim.preview()可重试。长原生调用内不能伪造新进度。


## 三项交互修复

同一Python进程、同一显式preview_port作为一个预览通道。新的空闲Simulation可接管自己的通道，原网页自动发现新run；旧Simulation仍可使用。计算中的旧对象不被抢占，不同端口独立；未知端口/其他内核服务不关闭。启动失败后可重试sim.preview()。关闭后在同一进程、同一端口重新加载，保留有界通道标识，原网页继续跟随；内核重启不沿用旧进程身份。页面可见时每2秒检查，磁矩发布最多每秒一次，与文件保存间隔无关；耗时原生调用阻塞Python时不能保证实时刷新。

默认Δx–Δy位移需要有效连续跟踪和相应采样保证。周期边界下不能把包裹坐标直接相减当作位移；无有效跟踪时标明位移不可用。trajectory=True仍可显式查看绝对位置散点，不能将该散点视为跨周期位移。

Notebook覆盖确认默认显示简短结果名，完整路径可展开。确认框有焦点且初始按键保护结束后，普通Enter覆盖、Esc取消。启动残留/失焦/带修饰键的按键必须释放后重新按下，持续持键不会因延时结束变成同意；带Ctrl/Shift/Alt/Command的Enter不构成确认。关闭窗口或中断也取消并停止队列。Mac使用当前解释器的临时标准库Tk应用子进程，退出/中断后清理，只在确认成功后替换输出。窗口不可用时明确提示安全输入方式及Esc不可用，失败绝不视为同意。
