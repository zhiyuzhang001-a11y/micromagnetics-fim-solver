# 单层 skyrmion 离线后处理（候选，待独立验收）

`fimrun.postprocess` 只读用户明确选择的 OVF/恢复 state/标量 CSV，不运行 LLG、不求场。输入必须是矩形单层、局域单对象；A/B 各自分析自己的单位方向，不能先合成净磁化。全部长度为 m、时间为 s、速度为 m/s、角度为 rad。原始文件和同名输出均不覆盖。

```python
from pathlib import Path
from fimrun.postprocess import analyze_ovf, frames_from_state

core_dir = Path('/path/to/boris-unified-entry')
calibration = core_dir / 'fimrun/postprocess/calibration_v1.json'
frames = frames_from_state('/path/to/drive.state')
rows = analyze_ovf(frames, '/path/to/new-analysis.csv',
                   calibration=calibration,
                   assume_temporal_sampling=True,
                   ab_reference='antiparallel')
```

`frames_from_state` 只接受自动平铺输出 state 的完整哈希清单，核对被绑定的 OVF 和 CSV；不恢复模拟，不创建 Native。`magnetization=False` 没有 OVF 时不能据 state 凭空构造磁态序列。该 helper 不跨 stage 拼接 lineage；显式不同 segment 同样断开追踪。较早旧布局请明确列出帧：

```python
frames = [dict(A='/data/a.ovf', B='/data/b.ovf',
               mapping=dict(boundary='periodic_xy', mirrors=[10, 10],
                            stage='sdesc'))]
rows = analyze_ovf(frames, '/data/new-static-analysis.csv',
                   calibration=calibration, ab_reference='antiparallel')
```

`mapping` 也可给 JSON 文件路径；可补充 run_id、segment_id、stage、time_s、accepted_index、boundary、mirrors、Ms_A、Ms_B 和 evidence 路径及 SHA。stage 使用 `rk4` / `sdesc`；未知项不猜。A/B 文件标签与明确配对冲突、state 网格冲突、来源事实冲突都留下无效行及 reason_codes。覆盖普通时序事实必须显式指定映射值、`overrides={字段: True}` 及非空 `override_reason`；不允许据此覆盖文件哈希或错误网格。显式 `csv` / `packet` 路径只在实际匹配且哈希通过后参与来源绑定。

输出一行对应一对输入，缺文件、源冲突、多对象、退化轮廓也保留审计行。`source_bindings` 是紧凑 JSON 列，绑定实际字节 SHA、所取字段/CSV 行、映射及证据、实际加载源码哈希与 commit/dirty、校准内容哈希和选项。文件读取使用同一字节快照解析并计算哈希。磁态/后处理源码更改后须新内核再导入；不热重载用户运行内核。

state 只读取已校验的 manifest 元数据及输出清单，不加载其中的物理态、核或 BB 历史；这不是 strict checkpoint 恢复资格检查。内部 every/cadences 和原 state 格式没有迁移，普通恢复保持兼容。导出器源码变化仍会使旧 strict checkpoint 的严格实现身份检查拒绝恢复，本次不绕过该保护，也不重写旧文件。

## 测量与有效标志

| 列 | 定义与限制 |
|---|---|
| A/B_Q、topo_x/y | 有符号三角形立体角；先按网格邻接展开每个三角形，再给整个重心选周期像，求局域一阶矩。signed seed 除以 signed Q，整体反号不改变 seed。 |
| A/B_area_x/y、area_m2、radius_m | 唯一可缩 m_z=0 轮廓的面积中心、面积、sqrt(A/pi)。主坐标折入原盒，unwrapped 另列。topo_area_dx/dy/distance_m 为两中心定义的诊断差。 |
| major_m、minor_m、axis_ratio、ellipticity、axis_rad | 面积协方差本征值定义 a,b=2sqrt(lambda)，是半轴；ratio=a/b，epsilon=(a-b)/(a+b)，主轴模 pi。接近圆或矩不可分辨时方向 NaN。 |
| chi_raw、chi_rad、coherence、phase_rms、phase_p95、n | 沿轮廓等物理弧长采样，对 psi-n phi 作圆均值，phi 从面积中心量取。n 按 CCW 测得，不能用 Q 符号代替。C 与局部 wrapped 相位偏差同时保留。低 C/强调制时 chi_rad 无效，chi_raw 仅诊断。 |
| B_chi_corrected_rad、AB_chi_difference_rad | 只有用户声明 antiparallel 且双方有效、极性相反，才给 B 减 pi 后比较；不自动猜材料参考关系。 |
| AB_area/topo_dx/dy、AB_area/topo_valid_relative | B-A 的短距离分支，追踪时从初帧最近像连续积累；按中心定义分别判定，接近半盒、误差包络覆盖分支或追踪相对量超过该分支时，主相对向量 NaN、valid_relative=False，relative_reason 解释原因。另存 minimum_image_dx/dy，仅为逐帧最近像诊断；静态或未声明采样时也保留，不表示分支唯一。 |
| area/topo_unwrapped_x/y、image_x/y | 各中心定义分别追踪。image 整数相对公开 wrapped 坐标，满足 unwrapped=wrapped+image*L，包括初帧 B 相对 A 的选像。每次重建分支以 A 的 wrapped 坐标为初始图，B 对齐最近像；计数不是从历史丢失帧恢复的圈数。默认不追踪；需明确 `assume_temporal_sampling=True`，声明每次实际位移小于半盒。半盒附近按训练位置误差包络保守拒绝。 |
| area/topo_vx/vy_mps | 同 run/segment 动态三连续有效帧，实际非均匀时间的局部三点二次导数；端点 NaN。缺帧/失效/非递增时间断轨，拓扑失效不沿用旧拓扑历史。静态 iteration 可用，物理速度始终 NaN。 |
| *_v_position_envelope_mps | 训练位置包络经过三点导数权重传播；不包含物理模型误差、未知时间误差或时间截断误差，不是置信区间。 |
| *_window_vx/vy_mps、window_residual_m | 仅显式 `velocity_window_s=(lo,hi)` 才作窗口线性拟合；报告最大位置残差，不暗插平滑。 |

分别检查 `valid_geometry`、`valid_topology`、`valid_axis`、`valid_helicity`、`valid_tracking`、`valid_velocity` 和 reason_codes。无效公开数值 NaN，有些中间值保留 raw_* 审计；不能将 raw 当有效结果。valid_velocity 表示双方**面积中心**导数可用，拓扑导数还须检查对应数值有限。`valid_pair` 只说明输入 A/B 皆已解析。

## 校准与精度适用范围

配置 `compact-wall-train-v1` 用 18 个独立于真实数据的解析紧支撑壁纹理训练：64/96/128 网格、圆/旋转椭圆、弱相位调制及跨角位置。门槛为声明的两倍训练误差包络加浮点累积底限，在 24 个新网格/半径/角度/相位/正负 Q 保留态和 3 个矩形网格保留态前冻结；没有用真实文件或保留态重调门。配置内部 sha256 为 `996211a75986d55287dd11f05db6488a53803b654bc1732be06acfa44b4ed607`。

当前细化实例在 64/128/256 网格上的半径绝对误差分别约 0.0717/0.0196/0.00439 nm；相位误差约 1.92e-5/7.33e-6/8.20e-8 rad。这些是指定合成纹理的离散误差实测，不能推广为任意壁宽、材料或真实 OVF 的精度保证。矩形保留态独立改变 hx/hy，并检查原点平移与正负 Q seed 不变。弧长细化只检验既有插值场，不能恢复原网格没解析的窄壁或高频相位。

实际输入的采样充分性没有自动认证。强调制、多 sky、消失、开放边界截断、周期切缝拓扑不稳定或不唯一轮廓均可无效；不做目标跟踪猜测。跨不同 segment 的 lineage 自动拼接尚未实现，采取断轨。未知 time/run/segment 仍可测几何，但不计算速度。

## 旧 OVF 与新导出元数据

新文本 OVF 增加标准 valuelabels 与 min/max；原数据数组不变。Notebook 自动输出另写重复 Desc 中的命名空间键：boris_metadata_version、quantity、time_s、stage、accepted_index、run_id、segment_id、boundary、mirrors、Ms_Apm。普通手工 export_ovf 只补标准头和子晶格标签，不伪造时序；此类文件需显式来源映射。旧重复 Desc 与普通自然语言均保留，只识别白名单机器键。

缺 valueunits/base 的旧文件只有经用户证据明确单位与原点，才用 `legacy_A/B={quantity:'magnetization_Apm', origin_m:[0,0,0]}` 补缺项；不改原件。A/m 输入须用各自正 Ms，单位方向输入须已在存储误差内归一。绝不自动把任意非单位场归一后当可信。

一对实际 BORIS 旧文件的 binary8 容器保存了可精确往返 binary32 的分量，模长偏差超过默认 binary8 门。为**明确声明的历史舍入假设**提供 `normalization_roundoff='binary32-gamma12'`：必须是 binary8 且每分量精确 binary32；仅将模长容差改为 gamma12=12u/(1-12u)，u=eps32/2，约 7.15e-7。这不是历史编译精度证明、物理 Ms 误差证明或默认规则；缺此显式假设仍拒绝。它不改几何/相位校准阈值，假设与原始 norm 范围写进来源列。

## 看示例

新文件 [notebook_skyrmion_postprocess.ipynb](../../examples/notebook_skyrmion_postprocess.ipynb) 默认不生成数据、不处理用户路径。也可显式运行：

```sh
python examples/postprocess_synthetic.py /path/to/new-toy-directory
```

该命令只生成解析合成 OVF，导出一个 analysis.csv；5 个非均匀时刻的真面积中心速度为 (10,-3) m/s，B-A 位移为 (6,-3) nm，反平行校正相位差为 0.15 rad，包含跨周期边界和呼吸。这个合成示例不替代 LLG 验证，也不调用求解器。

教程直接用 `summary_svg(rows)` 和 `IPython.display.SVG` 显示中心、半径、矩轴比及螺旋度四图，无需 matplotlib 或浏览器。动态有有效追踪时使用 unwrapped 中心，无追踪时为 wrapped 散点；静态始终用 wrapped 中心。静态横轴为已知接受迭代，未知迭代明确标为 input index，不伪造时间。无效样本、断段及相位±pi跳变不连线；混合 stage 须先选择一个 stage。SVG 函数只返回字符串、不写文件；默认未选择 rows 时教程不生成图。实际动态/静态代码、SVG XML 和 Notebook image/svg+xml 输出已开发验证，未声称浏览器页面截图验收。
