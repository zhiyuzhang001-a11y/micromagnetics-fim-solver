# Notebook API 1.4：同一磁态，按需逐单元

直接打开安装版 `notebook_single_sim.ipynb`，选择正式环境的新内核；不依赖.command，不热重载当前模拟。个人 `first_try/1.ipynb` 原样保留。

```python
import fimrun.micromagnetics as mm
from fimrun.notebook import NotebookSimulation

sim = NotebookSimulation(model=model, initial=initial, output_dir=output_dir)
sim.relax(name='prepare', mxh=1e-5, residual=1.0, save_step=10)
sim.set_current(mm.FiMSOT(J=(1e11, 0., 0.), xi_A=0.1, xi_B=-0.1))
sim.run(name='drive', dt=1e-15, duration=1e-12, save_interval=1e-14)
```

构造保存模型、初态、输出目录，立即打开初态viewer，不求场。尚无动态dt，静态只使用原优化器内部步长。首次动态须明确dt；后续省略dt可继承。duration是**本次时长**，在累计物理时钟上追加；同一个sim延续当前A/B。静态不推进物理时间，无max_steps或固定迭代上限，达到A/B双门或用户Interrupt才停；开启电流时必须先明确 `sim.set_current(None)` 才能静态。

| 操作 | 参数与默认 |
|---|---|
| 新构造 | 必填model/initial/output_dir；默认七种scalar、A/B OVF和viewer；不自动结构分析。dt未配置，`sim.dt is None`。 |
| run | `name`、`dt`、`duration`、`save_interval`；不提供steps参数。时间与频率须为dt的整数倍。 |
| relax | `name`、必填无量纲mxh、residual=1 A/m、consecutive=1；`save_step`为正整数接受迭代间隔或None。 |
| load | `NotebookSimulation.load(path, output_dir=..., name='restored', checkpoint=False)`；恢复物理态、累计时间、电流、dt与已保存频率。纯静态state恢复后仍无dt。 |
| save | `sim.save('manual.state')`；strict用checkpoint=True，必须同实现和条件；普通state重建BB私有历史。只新建、不覆盖、不额外求场。 |

动态与静态分别记忆保存频率。**省略**时继承该类阶段已配置频率，新会话尚未配置则仅末态；**显式None**设为仅末态。没有自动100帧/100步政策，也不新增“总是另存初态”政策。显式频率按既有规则采样（含满足间隔条件的初态）；CSV和OVF共享频率，定期、末态及可处理中断按本阶段接受态索引去重。零时长只写同态一次；静态不能用不变物理时间去重。

每阶段保存 `<name>.csv`、`<name>_ovf/`（A/B单位方向）和 `<name>.state`。CSV记录stage、step、static iteration、time_s和status。无缓存时缓存标量留空，表示不可用，不为输出暗中求场。硬杀/重启只保证已落盘的接受态。

## 标量与能量列

既有七种scalar为 `time/mean_m/energy/dissipation/drive_work/residual/mxh`。新版默认全部保存，仍可兼容旧显式选择；结构分析必须显式调用。`energy`产生下列J列，直接映射同一已接受态的原生缓存，没有新的能量方程或额外求场。

| CSV列 | 物理项与离散式 | FiM `Eparts` 索引 |
|---|---|---|
| `energy_total_J` | 下述七项之和：$\sum_{k=0}^{6}E_k$ | `sum(0..6)` |
| `energy_exchange_J` | 亚晶格内梯度交换：$\sum_{j,d,i}\frac{V A_i}{2h_d^2}\lVert\Delta_d\mathbf m_i\rVert^2$ | `0` |
| `energy_anh_J` | 交叉梯度：$\sum_{j,d}\frac{V A_{nh}}{2h_d^2}\Delta_d\mathbf m_A\cdot\Delta_d\mathbf m_B$ | `1` |
| `energy_ah_J` | 局域耦合：$-2A_hV\sum_j\mathbf m_A\cdot\mathbf m_B$ | `2` |
| `energy_dmi_J` | $\sum_{j,d\in\{x,y\},i}\frac{VD_i}{2h_d}(m_{i,d}m'_{i,z}-m_{i,z}m'_{i,d})$ | `3` |
| `energy_anisotropy_J` | $\sum_{j,i}w_iV[K_{1,i}s_i+K_{2,i}s_i^2]$，$s_i=1-(\mathbf m_i\cdot\mathbf a_i)^2$ | `4` |
| `energy_demag_J` | $-\frac{\mu_0V}{2}\sum_j\overline{\mathbf M}_j\cdot\mathbf H_{d,j}$ | `5` |
| `energy_zeeman_J` | $-\mu_0V\sum_j\overline{\mathbf M}_j\cdot\mathbf H_{\mathrm{ext}}$ | `6` |

FiM 的 $w_A=w_B=\tfrac12$，$\overline{\mathbf M}=(M_{s,A}\mathbf m_A+M_{s,B}\mathbf m_B)/2$。共享耦合及退磁只计一次，不硬拆 A/B。`energy_J` 保留为旧总能量别名，与 `energy_total_J` 同值，**不能再加入七项求和**。SOT 驱动功 `drive_work_A/B` 与阻尼耗散 `dissipation_A/B` 单列，不混入保守能量。

缓存来源：[FiM native](../../src/script_api/fim.cpp) `Evaluation.Eparts` → [Native.evaluate](../../fimrun/micromagnetics/native.py) → `Simulation._energy` → [energy_columns](../../fimrun/micromagnetics/simulation.py) / [FlatOutputs.observe](../../fimrun/notebook_flat.py)。索引0已从含交叉的交换总项减去Ecross，避免重复。FM原生缓存前四项是exchange/anisotropy/Zeeman/demag，按0/4/6/5列重排，其余FiM专属项为0。完整公式、边界和单位见[数学参考](../MATHEMATICS.md)。

## 兼容、预检与中断

旧完整构造 `dt/output_name/save_interval/scalars/magnetization/preview` 原样支持。**传入旧构造dt即保留旧默认**：scalars=('time','mean_m')、preview=False、magnetization=True，显式设置及阶段频率继承不变。早期results/name布局与位置tolerance[A/m]仍是独立兼容路径。

`output_name`兼容新`name`，同次同传一律拒绝，即使相同。`save_every_steps`兼容静态`save_step`，同传也拒绝，包括None；旧every薄别名仍警告，与相应新频率同传拒绝。错误名称、时间、采样、路径、别名或覆盖取消均不改变m、时钟、电流、dt、输出设置或阶段历史，求场0。

同名输出先检查state所有权和CSV/OVF哈希；明确输入OVERWRITE才替换，拒绝会报CellStopped。外来文件、链接、已改结果或锁冲突均保留，选新名字。发布使用独占创建，失败保留接受态及可见运行目录，不宣称跨文件崩溃原子。显式save不覆盖旧文件。重新构造会重置闲置sim，旧结果保留；续算不要重跑构造单元。

Interrupt 保留最后接受态，并抛出 `CellStopped` 阻止排队阶段当作成功继续；之后可手动明确续算。网页“暂停观看”只暂停观看，不停止求解。A/B 在同一接受态同时满足 $R_i\leq\mathrm{residual}$ 和 $R_i/M_{s,i}\leq\mathrm{mxh}$；`consecutive` 数不同接受态。其中 $R_i=\max_j\lVert\mathbf H_{i,j}-\mathbf m_{i,j}(\mathbf m_{i,j}\cdot\mathbf H_{i,j})\rVert$，不是完整 LLG/SOT 力矩。

同一个viewer跨阶段复用，保留来源/历史身份校验。3D显示密度不改变计算网格，超量箭头会拒绝并保留有效画面；2D独立支持单层XY至65,536像素/子晶格，200×200每格全热图。旧残差长段、z层和箭头长度控件移除；彩色XYZ保留。参数按组显示，历史帧使用当时快照，无快照明确不可用。服务冲突不杀别人的服务；关闭自己的旧sim或显式选择空闲preview_port。离线分析见[后处理](SKYRMION_POSTPROCESSING.md)。


## 运行期间查看和分析已保存结果

每次阶段开始时创建可见的 `<name>-running-随机字符/`，按用户配置的保存间隔持续写入 CSV 和 OVF；`progress.json` 标明 `running`、`finalizing` 或 `failed`，并记录已完整写入的帧及其哈希。没有新增自动采样频率。仅在 A/B 两份 OVF 均写完后才提交到清单，半写帧不会进入分析。

运行中或失败后，可以直接读取该目录中已经提交的磁态，无需最终 state：

```python
results = pp.analyze(output_dir / 'drive-running-实际后缀',
                     assume_temporal_sampling=True,
                     ab_reference='antiparallel')
```

一次分析冻结调用开始时的清单，仅校验其中不再改写的 OVF；不会追踪后续新帧，也不将正在追加的 CSV 当作固定来源。帧的时间、边界、Ms 和阶段来自已有 OVF 元数据，并与清单的运行/阶段/步数/时间逐项核对。来源记录包含清单快照的 SHA256。尚未保存完整帧时明确报错，标量关闭/磁态关闭的设置保持有效。此目录用于离线分析已有帧，不承诺逐帧续算 checkpoint。

正常完成后仍发布原来的 `<name>.csv`、`<name>_ovf/`、`<name>.state`，可见运行目录移除，原有 `pp.frames_from_state()` 用法不变。同名旧结果仍在明确确认后、最终发布成功时才替换。最终 state 保存失败也会保留已写好的 CSV、完整磁态和错误路径；最终磁态输出失败仍尝试保存接受态 state。硬杀时目录保留，但状态可能停在 running；磁盘写满/系统断电不保证更新状态或正在写入的文件完整，只分析清单中校验通过的帧。成功发布期间目录正在移动，若同时分析遭遇文件消失，应在发布完成后改用正式 state。
