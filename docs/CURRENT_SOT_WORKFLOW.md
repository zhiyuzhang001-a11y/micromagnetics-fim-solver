# 恒定电流、A/B独立有效SOT（本地首版）

这是固定模长、共址双亚晶格的**现象学有效力矩**功能。首版支持均匀恒定电流与每亚晶格独立的xi、场型比r；不含STT、脉冲/交流、自洽轨道/自旋输运、温度或GPU。不同A/B有效力矩不等于已建立Co/Gd微观轨道流模型。

## 可直接运行的中文例子

使用装有numpy的Python 3.11+。本机已验证解释器如下，系统python3本身缺numpy；其它环境准备见USER_SCRIPT_WORKFLOW.md。

```sh
PY="python3"
"$PY" tools/build.py --out build-sot --current-sot
"$PY" tools/run_user_workflow.py configs/user_case_sot.toml --validate-only
"$PY" tools/run_user_workflow.py configs/user_case_sot.toml
```

`user_case_sot.toml`是已实跑的0.2ps均匀初态示例，含同窗dt/2检查；不含skyrmion，因此不会伪造中心、速度或Hall。输出目录必须不存在。已计算过请复制配置并选择新目录，不覆盖旧证据。

`user_case_sot_skyrmion.toml`展示静态CP→2ps驱动：先已有原user_case.toml的达标静态结果，再明确配置initial中CP及元数据路径。也可指定自己在同一保守模型下已有的合格CP。它是**新驱动阶段的方向交接**，重新计E_origin，驱动时间、∫D/∫P从零开始；保留准备历史/原CP哈希，费用沿袭外部账。不冒充跨二进制exact resume，不以旧动态能量原点混算新驱动做功。

旧`user_case_v1`与relax入口保持原停止/验证语义；当前入口识别v2并分派。非零驱动不能落入静态BB，也不能因残差≤1 A/m提前结束。`workflow.mode="driven_dynamic"`按配置T运行；配置中的静态tol不作为驱动成功门。

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

J是带符号的**传统电流密度**A/m²，电子流方向相反，方向只翻一次。首版要求J_z=0。incident_direction即BORIS的STp/入射自旋流方向d，非直接极化p；非零向量显式归一并记录输入。使用q=d×J，不额外乘|J|，也不将q归一化；倾斜d会改变幅度，d∥J则零力矩。

xi、r按[A,B]排列，均无量纲且可正/负/零。A-only设xi=[非零,0]，B-only设[0,非零]；xi=0关闭相应力矩，不能把Ms或gamma设零。相同xi不表示不同Ms/alpha下响应相同。r=0只是隐式Gilbert式中无独立FL输入，显式方向RHS仍含alpha混合项。

厚度t固定取实际单层`cell_nm[2]`，不另设可独立改的有效厚度。每亚晶格使用自己的Ms、gamma_H、alpha。H单位A/m，gamma_H单位m/(A*s)，来源为rad/(T*s)时须乘mu0，来源为Hz/T还须乘2π；首版不接受交流频率。常数muB/e=5.788381608e−5 m²/s与固定BORIS来源一致。保守半体积归一化保持，方向RHS不再乘1/2。

## 生产RHS及独立验证

定义C_i=xi_i(muB/e)/(Ms_i t)，H_drive,i=−C_i/gamma_H,i [m_i×q+r_i q]。
生产使用现有Gilbert函数一次性计算H_cons+H_drive：

`dm/dt=−gamma_H/(1+alpha²) [m×H_tot+alpha m×(m×H_tot)]`。

独立Python展开驱动为

`C/(1+alpha²)[(1+alpha*r)m×(m×q)+(r−alpha*|m|²)m×q]`。

保留|m|²是因为RK4中间stage不逐级归一化；接受端点才按原方法归一。零电流/零xi直接走原算术，已与34149fd2短回归字节核对。

SOT不计入保守E。瞬时D/P是W=J/s，累计∫D/∫P是J。每亚晶格w_i=mu0 Ms_i V/2，D_i=w_i gamma_H alpha/(1+alpha²)|m×H_cons|²，P_i=−w_i H_cons·f_drive。按四stage RK4权累计，报告`E−E_origin+∫D−∫P`。能量升高可以是外部做功，不要求单调，也不以无驱动静态停止条件判驱动成功。

## 输出、观测与真实恢复

控制台/progress.json给实际接受步、物理时刻、E、双方累计∫D/∫P、场次数与最后CP步号。history.csv逐步保存能量、积分、闭合缺陷、双方残差与raw模长误差。observations.csv在**每个接受态**记录A/B的Q、包裹/unwrap中心、半径、形变及有效性；指定times_ps必须落在整数步，不裁步。共同保存态另存m/H_cons/驱动RHS及能量，支持独立重算。

report.json分列trajectory_reached、independent、step_sensitivity、structure_goal、motion、research_motion_qualification和grid_mirror_convergence。必需文件写失败、独立门/请求目标未过或资源退出均非成功，exit 2；达到时长且所有已请求门通过才exit 0。达到时长不等于平衡、稳态运动或真实材料准确。

J=0时方向、速度/Hall均null/not_applicable，只保留漂移。非零J时，短窗位移未超过10×0.01R0则为unresolved；仅保留带明确名称的fit_velocity诊断，物理velocity及Hall为null。窗口内任何接受态非单核、中心失效、Q奇异或unwrap连续性中断，都会使该窗口无效；失效后即使重新单核也不跨失效态拟合。原生连续性失效标记随CP保存/恢复，只有显式新阶段可重新建立观测历史。共同中心(R_A+R_B)/2独立使用净位移信号门，误差预算取双方中心预算的算术平均，不因A/B分别分辨而自动分辨；A/B抵消时共同速度/Hall为null。unwrap按每个接受步的最近周期分支，研究使用仍须满足足够小的时间步与有效纹理条件。

exact resume设置`resume.checkpoint`和其`.json`，使用新输出目录；T是绝对驱动终点。新CP保留m、全局步、E_origin、每亚晶格∫D/∫P及总量、中心unwrap/连续性状态。相同物理/数值/驱动/二进制/核身份才能精确恢复；改J/xi/r/d/Ms/gamma/alpha/dt须作为明确新阶段，不能冒充续算。resume时不要同时启用fresh dt/2比较。

外部追加费用账与原用户工作流一致，回滚CP不回滚费用。缺/坏账或旧CP缺源运行总账拒绝恢复；branch_fields与累计实际started_fields分开。保存的最后完整CP可能早于最新进度，失败费用保留。

## 初版短窗证据（保留）与最新状态

后续本地完整结果见[本地交付状态](LOCAL_DELIVERY_STATUS.md)和[有限结果摘要](../results/current-sot-campaign-summary.json)。固定125²/M10的0–400ps三档时间验证、M10/20/40有限敏感性及唯一250²早期筛查已完成；后者半径/形变门失败。初版15条短例的原始范围继续保留如下，不作为最新全部状态。

有限验收采用原125²、4×4×3nm、mirror10、指定达标保存态；五组是J=0、对称、A-only、B-only和反向J，各0→2ps、25/12.5/6.25fs三档。这验证首版方程/实现与限定工程精度。不是CoGd材料标定、无限PBC、一般几何/时间尺度或研究级速度/Hall证书。

运动物理结论还需原计划的至少三层时间/网格、域/有限像及初态残余弛豫检查、足够长预先固定拟合窗；目标为速度/半径/非零形变1%、Hall0.1°、中心0.01R0，近零量另用预定绝对尺度。本次2ps信号未分辨，不通过加大J或挑拟合窗造出Hall。

参考：BORIS v3.80 commit6f55516f46f5b6b6ed92bb030d62abab87b4a2f0的SOTField.cpp、DiffEqAFM_Equations.cpp与常数定义；独立xi/r为项目扩展。STT、脉冲与轨道输运没有随此接口获得资格。完整验收成本和失败均在本地交付证据中保留。

2026-10-16独审修复仅涉及以上观测资格与连续性。原15条短轨迹每个接受记录均为单核且连续，原方程、场、积分和三档误差证据继续适用，未重跑；旧运动报告由修订规则的零场重处理旁证取代。新二进制身份变化，旧二进制CP不能冒充跨版本exact resume。
