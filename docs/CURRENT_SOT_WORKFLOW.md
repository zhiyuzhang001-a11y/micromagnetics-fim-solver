# 恒定电流、A/B独立有效SOT（本地首版）

> **历史固定工具与证据，非当前安装版入门。** 以下命令、解释器路径、门限及结论属于旧CLI复现；不要将其当作现行Notebook/API限制。当前从[模拟Notebook](../examples/notebook_single_sim.ipynb)、[接口参考](API_REFERENCE.md)和[数学说明](MATHEMATICS.md)开始。历史数值与失败结论保留。

这是固定模长、共址双亚晶格的**现象学有效力矩**功能。首版支持均匀恒定电流与每亚晶格独立的xi、场型比r；不含STT、脉冲/交流、自洽轨道/自旋输运、温度或GPU。不同A/B有效力矩不等于已建立Co/Gd微观轨道流模型。

## 历史CLI复现例子（非当前推荐入口）

以下仅保留当时使用numpy/Python 3.11+的历史复现命令；缓存解释器路径属于旧本机环境，不适合作为现行安装步骤。当前Notebook使用专用已验环境，不需要重新构建这些工具。旧环境准备说明见USER_SCRIPT_WORKFLOW.md。

```sh
PY="$HOME/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3"
"$PY" tools/build.py --out build-sot --current-sot
"$PY" tools/run_user_workflow.py configs/user_case_sot.toml --validate-only
"$PY" tools/run_user_workflow.py configs/user_case_sot.toml
```

`user_case_sot.toml`是已实跑的0.2ps均匀初态示例，含同窗dt/2检查；不含skyrmion，因此不会伪造中心、速度或Hall。输出目录必须不存在。已计算过请复制配置并选择新目录，不覆盖旧证据。

`user_case_sot_skyrmion.toml`展示静态CP→2ps驱动：先已有原user_case.toml的达标静态结果，再明确配置initial中CP及元数据路径。也可指定自己在同一保守模型下已有的合格CP。它是**新驱动阶段的方向交接**，重新计E_origin，驱动时间、$\int D\,dt/\int P\,dt$从零开始；保留准备历史/原CP哈希，费用沿袭外部账。不冒充跨二进制exact resume，不以旧动态能量原点混算新驱动做功。

旧`user_case_v1`与relax入口保持原停止/验证语义；当前入口识别v2并分派。非零驱动不能落入静态BB，也不能因残差$\le1\,\mathrm{A/m}$提前结束。`workflow.mode="driven_dynamic"`按配置T运行；配置中的静态tol不作为驱动成功门。

## 参数与符号

```toml
schema = "user_case_v2"
[workflow]
mode = "driven_dynamic"
[drive]
kind = "constant"
Jc_Apm2 = [1e11, 0, 0]
incident_direction = [0, 0, 1]
xi = [0.1, 0.1]
field_like_ratio = [0, 0]
```

$\mathbf J$是带符号的**传统电流密度**A/m²，电子流方向相反，方向只翻一次。首版要求$J_z=0$。incident_direction即BORIS的STp/入射自旋流方向d，非直接极化p；非零向量显式归一并记录输入。使用$\mathbf q=\mathbf d\times\mathbf J$，不额外乘$\lVert\mathbf J\rVert$，也不将q归一化；倾斜d会改变幅度，$\mathbf d\parallel\mathbf J$则零力矩。

$\xi,r$按[A,B]排列，均无量纲且可正/负/零。A-only设xi=[非零,0]，B-only设[0,非零]；$\xi=0$关闭相应力矩，不能把Ms或gamma设零。相同xi不表示不同Ms/alpha下响应相同。$r=0$只是隐式Gilbert式中无独立FL输入，显式方向RHS仍含alpha混合项。

厚度t固定取实际单层`cell_nm[2]`，不另设可独立改的有效厚度。每亚晶格使用自己的Ms、gamma_H、alpha。$\mathbf H$单位$\mathrm{A/m}$，`gamma_H`单位$\mathrm{m/(A\,s)}$，来源为$\mathrm{rad/(T\,s)}$时须乘$\mu_0$，来源为$\mathrm{Hz/T}$还须乘$2\pi$；首版不接受交流频率。常数$\mu_B/e=5.788381608\times10^{-5}\,\mathrm{m^2/s}$与固定BORIS来源一致。保守半体积归一化保持，方向RHS不再乘1/2。

## 生产RHS及独立验证

定义

$$
C_i=\frac{\xi_i(\mu_B/e)}{M_{s,i}t},\qquad
\mathbf H_{{\rm drive},i}=-\frac{C_i}{\gamma_{H,i}}[\mathbf m_i\times\mathbf q+r_i\mathbf q].
$$
生产使用现有Gilbert函数一次性计算$\mathbf H_{\rm cons}+\mathbf H_{\rm drive}$：

$$
\frac{d\mathbf m}{dt}=-\frac{\gamma_H}{1+\alpha^2}[\mathbf m\times\mathbf H_{\rm tot}+\alpha\mathbf m\times(\mathbf m\times\mathbf H_{\rm tot})]
$$

独立Python展开驱动为

$$
\frac{C}{1+\alpha^2}[(1+\alpha r)\mathbf m\times(\mathbf m\times\mathbf q)+(r-\alpha\lVert\mathbf m\rVert^2)\mathbf m\times\mathbf q]
$$

保留$\lVert\mathbf m\rVert^2$是因为RK4中间stage不逐级归一化；接受端点才按原方法归一。零电流/零xi直接走原算术，已与34149fd2短回归字节核对。

SOT不计入保守能量$E$。瞬时D/P的单位为$\mathrm W=\mathrm{J/s}$，累计$\int D\,dt/\int P\,dt$是J。每亚晶格采用

$$
w_i=\mu_0M_{s,i}V/2,\qquad D_i=\frac{w_i\gamma_H\alpha}{1+\alpha^2}\lVert\mathbf m\times\mathbf H_{\rm cons}\rVert^2,
\qquad P_i=-w_i\mathbf H_{\rm cons}\cdot\mathbf f_{\rm drive}.
$$
按四stage RK4权累计，报告$E-E_{\rm origin}+\int D\,dt-\int P\,dt$。能量升高可以是外部做功，不要求单调，也不以无驱动静态停止条件判驱动成功。

## 输出、观测与真实恢复

控制台/progress.json给实际接受步、物理时刻、E、双方累计$\int D\,dt/\int P\,dt$、场次数与最后CP步号。history.csv逐步保存能量、积分、闭合缺陷、双方残差与raw模长误差。observations.csv在**每个接受态**记录A/B的Q、包裹/unwrap中心、半径、形变及有效性；指定times_ps必须落在整数步，不裁步。共同保存态另存m/H_cons/驱动RHS及能量，支持独立重算。

report.json分列trajectory_reached、independent、step_sensitivity、structure_goal、motion、research_motion_qualification和grid_mirror_convergence。必需文件写失败、独立门/请求目标未过或资源退出均非成功，exit 2；达到时长且所有已请求门通过才exit 0。达到时长不等于平衡、稳态运动或真实材料准确。

$J=0$时方向、速度/Hall均null/not_applicable，只保留漂移。非零J时，短窗位移未超过$10\times0.01R_0$则为unresolved；仅保留带明确名称的fit_velocity诊断，物理velocity及Hall为null。窗口内任何接受态非单核、中心失效、Q奇异或unwrap连续性中断，都会使该窗口无效；失效后即使重新单核也不跨失效态拟合。原生连续性失效标记随CP保存/恢复，只有显式新阶段可重新建立观测历史。共同中心$(\mathbf R_A+\mathbf R_B)/2$独立使用净位移信号门，误差预算取双方中心预算的算术平均，不因A/B分别分辨而自动分辨；A/B抵消时共同速度/Hall为null。unwrap按每个接受步的最近周期分支，研究使用仍须满足足够小的时间步与有效纹理条件。

exact resume设置`resume.checkpoint`和其`.json`，使用新输出目录；T是绝对驱动终点。新CP保留m、全局步、E_origin、每亚晶格$\int D\,dt/\int P\,dt$及总量、中心unwrap/连续性状态。相同物理/数值/驱动/二进制/核身份才能精确恢复；改J/xi/r/d/Ms/gamma/alpha/dt须作为明确新阶段，不能冒充续算。resume时不要同时启用fresh dt/2比较。

外部追加费用账与原用户工作流一致，回滚CP不回滚费用。缺/坏账或旧CP缺源运行总账拒绝恢复；branch_fields与累计实际started_fields分开。保存的最后完整CP可能早于最新进度，失败费用保留。

## 初版短窗证据（保留）与最新状态

后续本地完整结果见[本地交付状态](LOCAL_DELIVERY_STATUS.md)和[有限结果摘要](../results/current-sot-campaign-summary.json)。固定125²/M10的0–400ps三档时间验证、M10/20/40有限敏感性及唯一250²早期筛查已完成；后者半径/形变门失败。初版15条短例的原始范围继续保留如下，不作为最新全部状态。

有限验收采用原125²、4×4×3nm、mirror10、指定达标保存态；五组是$J=0$、对称、A-only、B-only和反向J，各0→2ps、25/12.5/6.25fs三档。这验证首版方程/实现与限定工程精度。不是CoGd材料标定、无限PBC、一般几何/时间尺度或研究级速度/Hall证书。

运动物理结论还需原计划的至少三层时间/网格、域/有限像及初态残余弛豫检查、足够长预先固定拟合窗；目标为速度/半径/非零形变1%、Hall0.1°、中心$0.01R_0$，近零量另用预定绝对尺度。本次2ps信号未分辨，不通过加大J或挑拟合窗造出Hall。

参考：BORIS v3.80 commit6f55516f46f5b6b6ed92bb030d62abab87b4a2f0的SOTField.cpp、DiffEqAFM_Equations.cpp与常数定义；独立xi/r为项目扩展。STT、脉冲与轨道输运没有随此接口获得资格。完整验收成本和失败均在本地交付证据中保留。

2026-10-16独审修复仅涉及以上观测资格与连续性。原15条短轨迹每个接受记录均为单核且连续，原方程、场、积分和三档误差证据继续适用，未重跑；旧运动报告由修订规则的零场重处理旁证取代。新二进制身份变化，旧二进制CP不能冒充跨版本exact resume。

See the [current LaTeX formula/code map](MATHEMATICS.md) for notation. Historical numbers, criteria and limitations in this document retain their original scope.
