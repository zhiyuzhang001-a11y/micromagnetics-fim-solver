# Notebook API 1.3：连续运行与逐阶段输出

使用 `examples/notebook_single_sim.ipynb`，在新项目内核运行。不要给正在计算的内核热重载源码。`my_case.ipynb` 是用户文件，本轮不改动。

```python
sim = NotebookSimulation(model=model, initial=initial, dt=1e-15,
    output_dir=output_dir, output_name='prepare', save_interval=1e-15,
    scalars=('time', 'mean_m'), magnetization=True)
sim.run(1e-15)
sim.relax(mxh=1e-5, residual=1.0, consecutive=1,
          output_name='static', save_every_steps=1, scalars=('time', 'residual', 'mxh'))
sim.run(1e-15, dt=1e-15, output_name='drive', save_interval=None)
```

`output_dir` 固定；`output_name` 是输出名，不是模拟身份。run续算同一磁态、累计物理时间和动力学耗散/做功，静态不推进物理时间。构造器显式重跑仍是重置闲置sim，旧输出保留。其它模型/能量/初态参数详见 [PARAMETERS](PARAMETERS.md)，完整调用见教程。

| 操作 | 参数及默认 |
|---|---|
| 构造 | model/initial/dt/output_dir必填；output_name='experiment'；save_interval=None仅末态；scalars=('time','mean_m')；magnetization=True（OVF）；preview=False；preview_port=8766；replace=True。 |
| run | duration [s]；dt=None继承；output_name/save_interval/scalars/magnetization未填继承，save_interval=None显式仅末态。时间和间隔必须是固定dt的整数倍，dt变更后同样检查。 |
| relax | mxh仅关键字且必填；residual=1.0 [A/m]；consecutive=1；输出设置可逐次改。save_every_steps用正整数接受迭代数或None；与动态cadence分开记忆。仅现有无电流FiM sdesc。旧位置tolerance或tolerance=在新接口预检报迁移错误，绝不解释为mxh。 |
| scalars | 元组，可选time/mean_m/energy/dissipation/drive_work/residual/mxh；()关闭CSV。磁态开关不影响CSV，二者关闭仍写state。 |
| load | `NotebookSimulation.load(path, output_dir=..., output_name='restored', checkpoint=False)`，恢复dt、电流、物理态及已保存输出策略。普通state重建BB历史；checkpoint=True检查strict身份和历史，不能随意换条件。 |
| save | `sim.save('manual.state')`，或checkpoint=True保存支持的strict历史；显式另存不覆盖同名，不额外求场。 |

每阶段只发布启用项：`<output_name>.csv`、`<output_name>_ovf/` 和 `<output_name>.state`。CSV和OVF共享cadence，末接受态统一保存；静态记录iteration而不冒充物理时间。OVF为A/B单位方向，包含实际时间/接受步或迭代；state包含恢复与所有权清单。取消/科学失败保留最后接受态及状态。

已存在同名对象时，先验证state所记所有权和哈希，列出精确目标，输入 `OVERWRITE` 才开始计算。拒绝不改变磁态、时间、dt、输出配置、历史或文件，求场0。没有默认追加。外来文件、结果被改动、链接或锁冲突会拒绝，不能随意清理；选择新名字或先检查恢复信息。仅替换该名称明确归属的对象。发布文件使用独占创建，失败回滚并留下隐藏恢复目录和可恢复接受态；跨文件不能宣称崩溃瞬间原子。异常竞争导致原位置被占时，恢复副本仍保留，须按错误给出的位置检查，不能强行覆盖冲突文件。旧用户结果不迁移、不删除，旧read_segments仍读取原分段布局。

新mxh是**同一接受态、各子晶格自己的Ms**：`R_i=max_cells |H_i−m_i(m_i·H_i)|` [A/m]，`q_i=R_i/Ms_i`（当前常量Ms模型，无量纲）。A/B各自同时满足R_i≤residual、q_i≤mxh，并连续满足consecutive个不同接受态。重绘同一态不增加计数。等效物理限制是min(residual,Ms_i×mxh)，默认1A/m可能更严。不用净Ms，面内/面外均适用。改变停止条件不沿用不匹配计数；这不是任意参数的科学精度保证。

BORIS归档原稿是5e-5；手册示例有1e-5。官方v3.80 AFM SDesc在固定模长下的归一化可化简为A横向场/Ms_A，但原指标取更新前A；本接口改为接受态A/B双方，不宣称原样复刻。证据详见 [公开验收摘要](../ACCEPTANCE_SUMMARY.md)。

网页显示R/q/阈值/通过或未过/更严格门槛。动态阈值标未启用，不静态判停；保守场残差不代表完整LLG/SOT力矩。仅从同态缓存归约，缓存缺失即不可用。2D/3D、mx/my/mz、XYZ正方向、XY物理坐标nm、z层及箭头密度共用原页；工具栏列当前倍率、每个可见子晶格的实际箭头数及合计，切A/B立即更新；2D列采样格点数。密度和箭头长度独立，不改网格。替换sim时通过随机服务身份和递增绑定版本重绑定原页，旧run/stage/frame校验保留。视图操作不额外求场，但拷贝/网络/归约/绘图与I/O仍有成本。

旧results/name构造保留原行为与旧目录、A/m停止接口，供已有脚本/数据兼容；不能混用新旧输出参数。默认新Notebook路径统一用output_dir/output_name。

动态构造默认save_interval=None，仅设置动态；首次静态save_every_steps=None。省略各自继承，显式None只保存末态。旧every本版本保留薄别名并发FutureWarning；同次新旧参数即使相等/None也拒绝，阶段错名和构造save_every_steps均在询问/提交/求场之前拒绝。旧results/name路径不支持新参数，恢复旧state不发别名弃用提示。本版本未指定移除日期。

离线科学分析见 [skyrmion后处理](SKYRMION_POSTPROCESSING.md)，不会自动分析已有用户文件。
