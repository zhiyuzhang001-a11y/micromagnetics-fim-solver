# 本地交付状态与复现范围

2026-10-16。本轮计算结束；当前候选仅本地提交，未公开推送。程序工作流可用与科学目标通过分别报告。机器可读状态和原证据摘要哈希见 [campaign summary](../results/current-sot-campaign-summary.json)。完整原始轨迹、二进制、checkpoint、资源账和独审保存在本地证据包；本仓库不捆绑这些运行产物。

## 已完成

- TOML→合格核缓存→独立静态准备→恒流动态→实际保存态独立检查、追加费用账和真实checkpoint恢复，在已验证环境/输入下可用。CPU采用C1及局部双owner，FFT串行，固定RK4保持。
- 固定125²、h4×4×3nm、M10、同一准备态的25/12.5/6.25fs完整0–400ps时间比较通过原门。200–400ps拟合是固定模型候选，不是材料真值、严格稳态或连续空间结果。
- M10/20/40各自准备态及400ps驱动/零流齐全。所测有限M范围速度向量/Hall角、半径/中心目标通过；最大共同窗向量差0.4301%、角差0.02604°。不构成无限镜像尾界。
- 去map的G0/G1同实现小夹具和125²/M10载荷、samples字节回归通过。唯一250²/M10、h2×2×3nm细核完成有限独立资格；精度/场/能量/残差/SOT-only门保持。
- 细档独立准备22019次更新，独立A/B残差0.999628/0.999490A/m；同准备态25/12.5fs在13个保存时刻0–2ps通过原时间门。之后按预算续到50ps并完成匹配零流；没有400ps。

## 未通过及保留诊断

- 有限M形变相对1%失败；10→40最大绝对差1.31543e−4超过1e−4。20→40绝对差虽减至4.74047e−5，相对1%仍失败。形变为mz=0轮廓面积二阶矩轴比减一，不测所有形状失真；近零分母会放大百分比，但不据此改门。
- 两网格早期0–50ps半径、形变目标失败：最大半径差5.39565nm=细档参考的9.5591%，形变最大绝对差1.30907e−4。中心位移差标记通过不替代其它失败。
- A的50ps驱动终点差5.3955749971nm，分解为准备态5.3870352625nm、零流漂移差0.0026157712nm、同网格驱动−零流响应差0.0059239635nm。约99.84%在准备态已存在；不能称为电流引发9.56%的响应差。映射半径约51.013nm，细档独立静态后56.407nm；积分磁化面积旁证也增长，不能只归因轮廓显示误差。
- 粗准备经过原500ps预演化和BB，细准备从插值粗平衡态直接BB。映射有损、吸引域/极小值分支未隔离。局部残差≤1A/m不是状态误差或径向曲率界；细档不自动是真值。
- 细档50ps运动位移约2.68nm低于固定5.64nm信号门，物理速度/Hall为null；原固定模型长窗候选不能包装成真实材料速度。
- 历史L/G载荷byte不同（11249个double）永久保留。L精确无量纲(1,1,.75)/整数坐标，G使用SI double导入MPFR/浮点坐标；不是去map失败。跨历史两核完整Gilbert+SOT敏感性标记1.79448564e−12超过1e−12也保留；独审明确该新增量不适用于原同态SOT-only一致性门，且不阻断去map。没有把它改报PASS。

## 后续研究与停止状态

连续空间极限、收敛阶、准备分支与纯h影响的分离、材料/CoGd标定、无限PBC、细档50/400ps时间收敛未认证。0–2ps时间门通过不迁移到长窗。没有必要为本轮程序交付扩400ps、第三网格、M80、调材料或放宽科学门。GPU、STT/脉冲、轨道输运、PDF/Atlas及已收尾静态尖峰专题不在本次新增范围。

项目累计1068173完整场；最后细档新增42871（native42827、独立44），8个native Models，4160动态接受更新、22019静态更新。完整核资格已用6/16，余额10不是新授权。全记录见本地回执；本轮收尾只有静态/文档及零求场适配器验证，不重跑轨迹。

## 去map候选的准确代码状态

[补丁](../patches/kernel-builder-no-map.patch)只移除无命中的map并显式计数，保留带符号坐标、公式精度、循环/Kahan顺序、parity和输出样本。**默认src/kernel_builder.cpp仍为map版本**；补丁待审阅采用，历史核及求解器未替换。不把解析范围n≤256等同于任意网格已获资格。

## 可复现启动与限制

使用有NumPy的Python≥3.11。以下是日后显式复现步骤，本次收尾不执行构建或数值运行。先按[安装](INSTALL.md)构建已有程序，再建立只含已构建fim_user/fim_drive的运行目录；不要把kernel_builder放进该目录，细档缓存缺失会显式停止。

已有`PY`选择会保留；未设置时，本机使用已验证的Codex运行时。其它机器请先明确设置，例如`PY="$PWD/.venv/bin/python"`，并为该环境安装NumPy。先执行零Model依赖预检；失败即停，不继续构建或计算。

```sh
PY="${PY:-python3}"
"$PY" -c 'import sys, numpy; print(sys.executable); print("NumPy", numpy.__version__)'
```

仅在预检成功、且明确要进行日后复现时，才执行以下构建和目录准备；本次收尾未执行：

```sh
"$PY" tools/build.py --out build-sot --current-sot
mkdir -p output/reviewed-runtime-bins
ln -s "$PWD/build-sot/fim_user" output/reviewed-runtime-bins/fim_user
ln -s "$PWD/build-sot/fim_drive" output/reviewed-runtime-bins/fim_drive
```

原125²准备工作流见[用户指南](USER_SCRIPT_WORKFLOW.md)，其`report.json`必须独立达标。映射适配器检查CP绑定/形状/单位向量，但不代替源态平衡核验。输出必须是新目录。

```sh
"$PY" tools/reviewed_spatial_inputs.py map \
  --checkpoint output/user-case/static/checkpoint.bin \
  --output output/reviewed-spatial-mapping
```

细核须为本地已合格载荷fa09e930…f6784e。从原证据包或一次单独审定的生成/资格流程取得它；导入仅重核字节/finite/reciprocity，**不声称重做465参考或native场资格**。既有历史粗核原字节不动。下面FINE_KERNEL是用户明确指定的本地文件，不自动生成或下载：

```sh
"$PY" tools/reviewed_spatial_inputs.py cache \
  --config configs/reviewed/fine-preparation.toml \
  --payload "$FINE_KERNEL" --cache output/reviewed-fine-kernel-cache
"$PY" tools/run_user_workflow.py configs/reviewed/fine-preparation.toml --validate-only
# 明确有独立新预算时才去掉 --validate-only；核/准备未过不可继续。
```

[六份已审参数模板](../configs/reviewed/)使用真实材料/几何/驱动值、可替换的本地IO路径；不捆绑CP。依次为粗短窗参考、细准备、同细CP的25/12.5fs各2ps、只从25fs2ps CP续到50ps、匹配零流50ps。两条2ps必须按原方向max A/B1e−4/4e−5、RMS7e−6/2.5e−6、E/累计D/P差1e−7E*、闭合2e−7E*联合通过，不能仅看一般step_sensitivity开关。模板不自动裁定这组严格门；原执行控制脚本及完整检查在本地证据包。

不同dt是同准备态的新分支，不能exact resume。50ps配置的T是绝对终点，沿用2ps CP，不重跑前缀。每份模板的作业墙钟不能当整个阶段预算重新计时：复现需额外维护阶段3600s、50862场（含已有资格2场的历史方案口径）、RSS2GiB、输出4GiB总账；单工作流输出接口上限1GiB。新复现的源账/预算必须另行明确，不能把本轮余额当授权。

需要复核去map源补丁时先`git apply --check patches/kernel-builder-no-map.patch`。可复制原src/kernel_builder.cpp到隔离目录的src/后在那里`patch -p1`，按C++17/O2及MPFR/GMP原参数、`-I`指向仓库src编译；不要为复核补丁重编求解器。细核生成参数文本为`250 250 2e-09 2e-09 3.0000000000000004e-09 1 10 10 NEW_OUTPUT WALL RSS`，主查询27562500+输出12，独立参考465另计。跨编译环境不保证字节相同；未知载荷不能借用该已知hash的资格或被导入器放行。上述步骤均不自动运行，当前交付已停止计算。
