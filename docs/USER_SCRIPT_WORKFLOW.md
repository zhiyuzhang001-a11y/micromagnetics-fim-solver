# 参数化脚本工作流（本地 v1）

> **历史固定工具与证据，非当前安装版入门。** 以下命令、解释器路径、门限及结论属于旧CLI复现；不要将其当作现行Notebook/API限制。当前从[模拟Notebook](../examples/notebook_single_sim.ipynb)、[接口参考](API_REFERENCE.md)和[数学说明](MATHEMATICS.md)开始。历史数值与失败结论保留。

编辑 `configs/user_case.toml`，从一份配置串行完成预检、初态/核准备、固定RK4动态、SD/BB静态、保存态独立场检查和报告。保留原固定案例CLI；本入口继续使用C1、局部双线程和串行FFTW。没有GPU、电流、DP54、退磁外推或自动调参。

## 安装与运行

所有命令须使用同一个已安装numpy的Python解释器；系统`python3`若缺numpy会在启动Model前给出提示，不会静默换解释器。需要Python 3.11+、numpy、C++17编译器、pkg-config、FFTW3；新几何核的首次构建另需MPFR/GMP头文件与库。不会自动下载或安装依赖。依赖不齐时先补本机环境；核准备失败不会降级为另一个网格。

```sh
python3 tools/build.py --out build --user-workflow
python3 tools/run_user_workflow.py configs/user_case.toml --validate-only
python3 tools/run_user_workflow.py configs/user_case.toml
```

`--validate-only`检查配置、初态、依赖路径、恢复身份和输出预测，0 Model、0新核；不宣称缓存已通过实时校验。实际执行时再次校验缓存清单/校验和。串行局部场回退：构建到另一目录并加`--serial-local`，然后更新`output.bins`。这里的本机验收使用Python构建；CMake未新增用户工作流目标，也未验证其它平台。

默认配置是原125²案例；先复制到新文件并修改`output.directory`。相对路径均相对TOML所在目录。输出目录已存在会拒绝，包含失败证据也不会覆盖。配置语法重复键、未知键、非法单位/维度、非有限值和超支持域在Model前拒绝。`--validate-only`通过不等于所选物理参数、步长或网格合格。

## 本机可直接使用的解释器与一次性环境准备

本机系统`python3`缺numpy。交付回执已经验证下述解释器；`$HOME`展开为本机用户目录。所有命令用同一解释器：

```sh
PY="$HOME/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3"
"$PY" -c 'import sys,numpy; print(sys.version); print(numpy.__version__)'
"$PY" tools/build.py --out build --user-workflow
"$PY" tools/run_user_workflow.py configs/user_case.toml --validate-only
"$PY" tools/run_user_workflow.py configs/user_case.toml
```

其它机器可先安装Python 3.11+，再一次性创建独立环境（以下由用户明确执行，工作流不会自动安装）：

```sh
python3 -m venv .venv
.venv/bin/python -m pip install numpy
.venv/bin/python tools/build.py --out build --user-workflow
.venv/bin/python tools/run_user_workflow.py configs/user_case.toml --validate-only
```

C++17、pkg-config、FFTW3及新核所需MPFR/GMP是另需准备的系统构建依赖；检查失败先补环境，不要换用缺numpy的解释器启动作业。

## 支持范围和物理约定

支持均匀材料、共址双亚晶格、单层矩形网格。$n_x,n_y\le256$，$n_z=1$，总 cell $\le65536$，单元长宽厚最大/最小$\le4$。完整XY周期须$n_x,n_y\ge3$、有限镜像每轴0…40；完整XY开边须镜像0且$A_{nh}=0$。混合边界、3D、多层、空间/时变参数、脉冲与bulk DMI明确不支持。

材料每个亚晶格独立$M_s>0$、$A\ge0$、D/K1/K2、易轴、$\alpha\ge0$、$\gamma_H>0$；Ah/Anh各为一个互易系数。轴显式归一并保留输入。恒场仅接受H（A/m）或mu0H（T）之一。内部保持$\overline{\mathbf M}=(M_{s,A}\mathbf m_A+M_{s,B}\mathbf m_B)/2$，own-Ms场映射及半体积能量权。每条正向边的梯度能量：

$$
E=\frac{V}{2h^2}[A_A\lVert\Delta\mathbf m_A\rVert^2+A_B\lVert\Delta\mathbf m_B\rVert^2+A_{nh}\Delta\mathbf m_A\cdot\Delta\mathbf m_B]
$$

矩阵为

$$
\begin{pmatrix}A_A&A_{nh}/2\\A_{nh}/2&A_B\end{pmatrix},\qquad A_{nh}^2<4A_AA_B\quad(A_{nh}\ne0).
$$
$A=0$且$A_{nh}=0$是合法半正定分支。$M_s$相等、$\alpha=0$、零场和零交换等分支合法；不把$M_s=0$当作FM模式。

固定RK4允许任意正dt；$T\ge0$且$T/\Delta t$必须整数。$T=0$只跳过动态更新，仍求初/末场。输出按接受步记录，不裁步凑输出。100fs只复现原预弛豫，改参数后应显式启用同窗dt/2检查。静态aux是优化器辅助时间，不是物理时间。

## 初态与OVF

`uniform`使用A向量和antiparallel或independent关系（后者B为独立均匀方向）。`smooth`的A为$\mathbf m_A=(a\cos\theta,0,\sqrt{1-a^2\cos^2\theta})$，其中$\theta=2\pi(x/L_x+y/L_y)$，要求$\lvert a\rvert<1$；B按关系指定。`skyrmion`使用径向tanh壁，中心nm为绝对位置，helicity为平面角，polarity为中心$m_z$符号；不保证它是平衡态或经过物理分辨率认证。`canonical_legacy`只用于原125²几何及公开解析初态。

`ovf2`必须分别提供A/B的单段OVF2矩形vector3文件。支持Text、Binary4和Binary8及二进制端序哨兵；节点、cell、中心base/原点必须匹配，不插值或裁切。`direction`显式提取单位方向，保留原模长/单位/哈希；`magnetization_Apm`要求A/m及各自Ms匹配，Binary4相对容限1e-5，Text/Binary8为1e-12；归一后的double方向仍须满足1e-12模长门。零/非有限向量、OVF1、6分量或非矩形mesh不支持。验收仅使用公开合成数据。

## 核与首次费用

精确原几何复用已验证的mirror10核原字节。其它几何使用MPFR128 Newell近场及BORIS/OOMMF来源渐近远场，按有限周期像求和并作互易投影，或开边2nx×2ny嵌入。首次生成可能较慢，进度显示kernel阶段；生成和独立Decimal参考计入wall/kernel预算。失败保留不完整目录，需检查后选择新cache目录，不静默接受半成品。

缓存绑定几何、生成版本/源码、六分量/符号、布局及精度并检查SHA；命中省生成费用，**不证明网格或镜像物理收敛**。新核报告分开给出有限/互易检查、张量样本与零位移块参考误差及覆盖。测试另作小格显式卷积/能量梯度旁核；这些是工程验证，不是全核严格误差上界。

## 进度、结果和恢复

控制台JSON heartbeat和`progress.json`显示最近读取的阶段、接受步/物理时间、能量、双方耗散/残差、可恢复checkpoint步号。采样时间与求解器elapsed单列；机器繁忙时观测可能滞后。不会为更新显示多求场。只有完整CP可恢复，最新进度不必已经落入CP。

主要输出：`resolved_case.json`、`manifest.json`、`initial.json`、`kernel.json`、分阶段history/接受态CP/快照、独立检查、`ledger.json`、`report.json`、`magnetic_final.npz`及A/B的m_z SVG快照。初态、动态末态、静态末态都独立检查；恢复检查和所有求场计费。NPZ以A/B、z/y/x、xyz分量存储，x最快；SVG颜色只显示m_z，不能代替完整向量分析。

`report.json`分列：

| 字段 | 解释 |
|---|---|
| execution_completed | 独立静态门、请求的步长/结构门及全部必需输出均完成；预算/异常/目标未过为false |
| static_criterion | 保存态双方max切向H独算是否$\le$请求`tol`；不要求中间单调/连续20步 |
| dynamic_step_sensitivity | 未检查、同窗dt/2工程门通过或未过；不是证明真解 |
| structure_goal | 默认none不设结构门；observe只观测；single_skyrmion单独检查 |
| grid_mirror_convergence | 本入口未自动作物理细化/镜像扫描，报告not_checked |

独立组合场相对误差门1e-10、残差差1e-6 A/m、归一能量误差1e-10、unit偏差1e-12；均不会为通过放宽。static tol由用户明确给出，原1 A/m不认证任意材料的物理精度。exit 0要求完成且已请求的步长/结构门未失败；exit 2须查看真实停止原因，不把未收敛或失败目录当成果。

精确恢复填写`resume.checkpoint`和对应`.json`，选择新输出目录。配置的T是绝对动态终点、max_updates是绝对静态更新上限；动态CP可继续动力学再重新开始静态，static CP保持BB prev/Gprev、dt/resets/aux并继续静态。材料/网格/核/恒场/alpha/gamma/dt/二进制身份不符拒绝。允许调整资源/保存间隔；tol变更写入策略沿袭。费用分开记录：`branch_fields`是当前CP分支沿袭的费用，`started_fields`是外部追加账的累计实际费用，`new_fields`仅本次新增。`resource_ledger`位于运行目录旁，路径随CP侧证沿袭；其哈希链JSONL使用POSIX文件锁、追加和fsync（本机macOS已验，Windows首版不支持），回滚CP不会回滚该账。native启动前预留其场额度，结束后以实际计数结算；控制器硬中断而未结算的预留保持保守收费，不能静默清零。丢失/损坏外部账会拒绝恢复。

旧版CP首次接入时，外部账导入`max(CP费用,源运行report总费用)`，例如源运行181场而动态CP为163场，继承至少181场。后续从同一旧CP重复恢复仍读同一外部账。缺少源运行report时拒绝迁移，不仅凭CP费用快照重建账。迁移仅能导入源运行已有的记录，迁移前其它位置未登记的分支仍须在外部实验总账单列，不声称已自动发现所有历史分支。旧证据不重写。旧无shape/身份CP不支持exact resume；先用原入口恢复并导出明确几何的A/B OVF方向，再作为fresh seed导入，耗散/BB历史不会自动继承。没有足够canonical侧证时不会声称精确迁移。resume不同时启用dt/2比较。

## 异常与调整

| 观察 | 先核对与可选择的后续动作 |
|---|---|
| 非有限/模长/耗散异常 | 列实际步、参数单位与原始方向；同参数缩dt作有预算同窗对照，核alpha/gamma，勿先调物理材料 |
| residual未达tol或有尖峰 | 看A/B末态与停止原因；增加合理预算后精确恢复；不自动放宽tol，中间峰值不否定达标末态 |
| 结构缩小/消失或目标不符 | 可能是真实弛豫；先核单位和身份，再分别做步长、网格/镜像或初态敏感性，不自动增D改K/场 |
| 半径只有几cell | 仅分辨率提示；同物理尺寸细化网格并重建核，不能由本次运行宣称物理合格 |
| cache/CP身份、校验和不符 | 停止，检查输入/版本；选择新目录重建有验证核，勿删失败费用或降级到旧几何 |
| wall/RSS/场/输出额度不足 | resource状态表示未完成；保留最后完整CP，显式加合理资源或降低保存频率后恢复 |
| 缺依赖或不支持输入 | 首次Model前拒绝；按范围改配置或补依赖，不静默安装/改模型 |

验收入口：`python3 tests/user_workflow.py --mode contract|small|canonical|interrupted --out NEW_EVIDENCE --bins build`（small可加`--serial-bins build-serial`）。模式按contract→small→canonical顺序，同一证据根；每种模式只在相应运行目录不存在时执行。canonical是唯一完整原案例回归，不是性能benchmark。

## 恒定电流扩展

需要 A/B 独立有效 SOT 时使用 `user_case_v2` 的 `driven_dynamic`，见 [中文恒流指南](CURRENT_SOT_WORKFLOW.md) 与 [短例子](../configs/user_case_sot.toml)。旧 v1 保持原语义；驱动结果按到时长、独立检查、步长敏感性及结构目标分别报告，不以静态残差提前结束。
