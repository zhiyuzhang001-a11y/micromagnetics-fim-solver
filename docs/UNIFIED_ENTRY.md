> Historical Case compatibility guide. The desktop and repository template have migrated to the sequential SI interface. Use [Quickstart](interface-v01/QUICKSTART.md), [parameters](interface-v01/PARAMETERS.md) and [migration](interface-v01/MIGRATION.md) for the current daily script. The Case workflow, defaults, resource limits and old regression totals below describe the preserved legacy path. Its template is now [legacy_case.py](../examples/script_api/legacy_case.py). Historical sealed evidence is unchanged.

# 可编辑 Python 入口（固定案例非零整链与失败阻断已验）

在本机桌面 `微磁模拟/my_case.py` 修改并保存 `Case(...)`；标准 dataclass、Literal 和单位注释提供编辑器可用的类型信息。需要 Python 3.11+ / numpy，沿用原依赖，不自动安装、编译或生成新核。

本机日常参数入口是 `/path/to/project/Desktop/微磁模拟/my_case.py`，桌面“打开项目”“检查参数”“运行计算”均使用这份文件。仓库根的 `my_case.py` 是模板，不是本机日常执行源；请勿改错文件。以下命令同样使用桌面参数源及本次真实T=0和非零整链都实际使用过的解释器，可从任意cwd调用：

```sh
/path/to/project/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 "/path/to/project/Desktop/微磁模拟/my_case.py" --check
/path/to/project/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 "/path/to/project/Desktop/微磁模拟/my_case.py"
```

仓库模板 `my_case.py` 仍是需填写现有bins/cache及全新输出目录的示例；桌面入口已配置本机路径并为每次运行选择新输出目录，物理参数仍须按研究核对。独立控制脚本已验证相同物理时长的canonical125²/M10、500ps准备＋2ps驱动整链，但保存频率、结构目标和路径按冻结回归配置设置，不能称默认`my_case.py`逐字段已执行。实际验收脚本是[case_A.py](../../unified-entry-nonzero-control/case_A.py)，它是封存证据，不是用户默认入口；已封存输出不得覆盖或直接重复运行，复用配置须另设新输出并明确本次预算。100fs、1A/m及材料值也不是任意输入的科学精度保证。

若从仓库模板新建独立入口，先配置三处再check：Runtime.bins须指向实际已有二进制目录（本机已验值可填`../current_sot_fine250_execution_20261016/bins`）；Output.directory必须全新，其父目录须已存在；Runtime.cache指向与所选几何匹配的已验缓存。本例canonical125允许使用随包已验核，cache缺失时也不会生成新核；其它几何缺合格cache会拒绝。`build-unified`只是占位，不表示已经构建。修改网格时同时检查初猜模式与核资格；OVF只能先准备。PreparedState必须给现格式合格report，保留其原单位及身份表示，不手改CP/报告。

先只改Case中的值，保留__main__调用；dt_fs用fs、T_ps和times_ps用ps、cell_nm用nm、场二选一（H_Apm为A/m，mu0_H_T为T）、Jc_Apm2为A/m²，其余单位见逐字段注释。数字不要加引号，整数/向量维度保持类型；例如`dt_fs="25"`会在启动Model前拒绝。check失败先按字段/缺依赖提示纠正；运行失败查看root/report.json和阶段stderr，费用与完整CP保持，不清账或降低阈值重试。路径已有、静态不达标、预算不足及科学/输出错误均非零退出；preview故障只警告。当前设置不会自动修改或复跑。

- `relax`：初猜进入静态；保留后端 T=0 初始化/独立检查。
- `prepare_then_drive`：有限预动力学→通过原静态/独立/目标门→fresh驱动阶段。
- `drive`：设置 `prepared=PreparedState(report="已有准备目录/report.json")`；实际CP、元数据、配置、源二进制、核和费用账均需绑定。OVF仅是准备初猜。准备/驱动dt可以不同；fresh交接不是exact resume。

所有用户IO路径相对脚本真实目录，库资源相对包目录；不改变调用者cwd、环境变量或浏览器默认设置。源码物理实现和原工作流保持原样。库导入不启动进程。Python用户脚本自身仍会执行顶层代码，`--check`不是任意Python代码沙箱。

`--check`只读取/校验/forecast，不创建输出root、账、锁、run.json，不启动原生程序、编译器、核生成器、viewer或浏览器。未来准备CP显示pending，drive_ready=false；独立drive缺源报告是错误。运行前重新预检、核对输入hash并独占创建root，禁止覆盖/隐式恢复/重试。

`Budget(new_fields=F,wall_s=W,rss_bytes=R,output_bytes=O)`作用于整链。实际源账S0冻结后，所有后端共用累计cap C=S0+F（不得超过既有1000000上限）。原工作流自己reserve/settle；入口不重复扣费，新增量=最终账−S0。损坏/回退/未结账拒绝续跑；失败保留保守预留。lineage锁排斥其他统一入口，不能阻止绕过入口的旧脚本。

单一monotonic墙钟含预检、IO、阶段交接、preview和最终报告；阶段只获得真实剩余时间/整root剩余输出。科学owned RSS采样口径为入口及当前科学后代，排除自己创建的preview树；容量失败非零退出。采样不是连续瞬时峰值保证。若系统拒绝进程检查，入口在启动科学前失败，不降级为无监督运行。仅监督自己创建的科学进程组。

preview开启时，预检额外要求整链forecast加`Preview.log_bytes`（默认64KiB，最多1MiB）不超过整root上限O；科学输出预先分配O−log_bytes，后续不因日志增长缩减已发出的额度。stdout/stderr通过PIPE按有界块采集，最多写log_bytes，达到上限告警并关闭本次viewer。实际整root仍按O检查，日志没有被排除出磁盘总限额。

`run.json`单写者原子替换；固定binding分别绑定prepare/drive的配置身份，可变状态和阶段不影响binding hash。原生完成但独立门未通过时不报completed；旧running记录不证明进程活跃。核复制到本次root缓存并计入root容量，工作流只能命中已验证核；不自动生成新核。

缓存资格逐项读取既有原门：工程误差≤1e−10、参考精度漂移/互易误差≤1e−12，必需样本/零位移覆盖/计数及来源须有效；缺失、非有限、失败、未知来源均拒绝，不补跑参考。canonical历史来源只认可既知geometry/SHA；已审细核保留独立生成器身份及回归依据。私有复制原样保留资格记录，不用新标签取代。旧准备报告缺mandatory_outputs_written等严格字段时安全拒绝，不自动补True迁移；方向输入的整数/浮点表示也必须遵守原身份hash，入口不擅自改写。

preview默认关闭。显式开启需要`Preview(command=(解释器绝对路径,viewer/server.py绝对路径),enabled=True,port=8766)`。实际viewer的`--manifest/--port/--instance`合成协议互通已获独审验证；固定驱态的真实Chrome前台跟随也已实测通过，下文保留单次BA性能数值和资源监测偏离。stdout ready和HTTP ready均需绑定本次实例/运行/不可变binding，阶段分别绑定；HTTP200不够。显式端口冲突不复用/杀旧服务。正确等待状态可开页，只尝试一次；阶段切换不重开。缺命令、超时、viewer退出、浏览器失败只告警，不改变科学结果。

preview的自身进程树RSS在启动和运行期采样，超限只停止自己创建的服务。启动时间/ready请求次数/响应字节/RSS另记，不计科学场；未测HTTP请求字节、共享Chrome/GPU/首帧CPU。运行结束停止本次服务，浏览器标签不关闭；本版不提供计算后常驻历史服务。握手协议详见父线程转交的 `VIEWER_ENTRY_PROTOCOL_V1.md`。`protocol.frame_matches`和测试规定旧帧拒绝规则，实际浏览器实现归viewer侧，不能把入口mock通过说成viewer产品已通过。

## 非零整链与失败阻断：保存证据独审通过

在已审实现480ea5f上，实际用户脚本`run(case,script=__file__)`完成固定canonical125×125×1、4×4×3nm、pbc110、mirrors10回归，preview关闭，无executor替换。A使用原canonical初猜，100fs步长进行500ps动力学（5000更新），随后静态13380更新，双方独立切向残差为0.9939089816427905／0.9936944284675523 A/m，原1 A/m及single_skyrmion门通过。准备CP方向与fresh驱动seed／step0逐字节一致；驱动以该准备态能量为新的origin，时刻、耗散及做功从0开始，25fs步长推进2ps（80更新），13个保存态独立检查通过。当前162条A/B观测均single且continuous。121项保存科学对照严格一致，其中二进制按字节、JSON/科学CSV按精确值比较；结果对照排除墙钟和RSS，驱动CP只比较物理前缀，不将旧observer状态当成新资格。

B实际完成1步动力学后以静态更新预算0结束，残差未达标；数值一致性独立检查通过但static_criterion_met=false。入口退出2、run.json为failed，保留实际10场费用且未启动驱动。R因额度低于整链预检最低值而退出2，未创建输出或账，未启动科学计算。这些预期拒绝是回归验收通过，不是把未达标科学运行报成功。

A实际38799场、B实际10场，整包共38809完整场（原生38790＋独立19）、5原生Models、5081动力学更新及13380静态更新。B剩余414场额度未使用，不计实际费用。外层整包47.467904209秒，owned RSS采样峰156631040 B，科学输出与控制证据约89.79 MB；无重试、编译、新核生成或推送。模型数量根据5份真实native request/result及已审每main一次构造计数；采样RSS不代表连续瞬时峰值。独立复核277项封存绑定、128项黄金来源绑定及全部121项严格对照均一致。

[交付收据](../../unified-entry-nonzero-control/DELIVERY_RECEIPT.json)、[A保存态审计](../../unified-entry-nonzero-control/A_SAVED_AUDIT.json)、[B预期失败审计](../../unified-entry-nonzero-control/B_SAVED_AUDIT.json)和[封存检查](../../unified-entry-nonzero-control/POSTSEAL_CHECK.json)保留完整证据。独立最终复核见task-3/unified_entry_nonzero_final_review/REVIEW.md。

验收支持这个固定案例的可编辑入口、只读预检、非零动态→静态→fresh驱动、保存独立检查、身份与同账预算，以及静态不达标时拒绝驱动。T=0证据继续保留。该工程回归不新增任意材料/网格/镜像、时间精度、运动速度/Hall或长期稳定资格；既有科学结论和失败门保持原范围。固定驱态的真实Chrome前台跟随与科学文件等价已实测通过；单次BA性能数值及监测偏离见下一节，不宣称全协议或绝对无开销。默认示例的保存/目标/路径组合不自动继承逐字段执行资格。

项目[只追加完整场汇总账](../../PROJECT_COMPLETE_FIELD_ACCOUNT.jsonl)已保持T=0的7场与非零回归38809场各一次，并只追加本次正式BA8000的实际80024场一次；当前项目总数**1217024场**。原1068173场锚点、viewer旧AB20010场及未完成BA的B10001场保留，不退费、不把派生lineage803936当项目总数。见[本次去重回执](../../unified-entry-final-closure/PROJECT_ACCOUNT_APPEND_RECEIPT.json)。文档与保存证据核对本身新增科学场为0。

## 真实前台跟随通过；性能仅为一次有限BA观测

正式BA8000从同一400ps/step16000 CP、同一现有motion-fix binary/kernel/config，B→A各执行8000更新至600ps/step24000，preview产品与科学代码未改。B原生wall **61.422471792s**，A **61.772944833s**，B−A=−0.350473041s，本样本差**−0.5673569%**。这不是绝对无开销证明，也不表示viewer加速求解；顺序、缓存、温度和噪声未估计。

B在原生存活期有12次有效state检查和10个不同已提交真帧（step16000…23200），默认5秒/stride4自然跟随，原生期无UI/debug操作，前后原生证据同页、无visibilitychange；结束后的24000帧不补计。A关闭观察页、Chrome空白前台，原生期间页面请求为0。63份共同保存科学文件一致，22项原保存态独立检查通过。新增80024完整场=80002原生+22独立、2原生Models、16000更新；旧偏离AB及未完成BA单列保留，不合并成前台性能统计。

**限制必须随结果保留：** 整包294.055s<420s，但臂间准备64.292s超过30s分配，核验后清理41.377s超过30s分配。观测charged owned RSS峰359858176B（约360MB）不是整包完整峰值：临时A18775服务未完整登记，sampler在DONE后结束，未覆盖约41秒清理；共享Chrome基线1970192384B另列。未发现已观测超限，不等于完整RSS协议通过；不宣称全阶段预算分项通过、长期RSS/FPS或零开销。不得为补这些管理采样缺口重跑科学计算。

[原报告](../../../task-3/performance_ba_8000_once/REPORT.md)、[正式收据](../../../task-3/performance_ba_8000_once/FINAL_RECEIPT.json)及[本轮只读核对](../../unified-entry-final-closure/BA8000_READONLY_VERIFICATION.json)保留185项封存绑定、63文件比较和计时内访问证据。实时跟随及固定案例本地使用有据；剩余是这些监测/协议解释局限，不是自动补跑任务。此BA不等于默认my_case.py所有参数组合或三阶段+浏览器逐字段端到端均已实跑，也不新增材料/精度/运动科学资格。

## 本地预览怎么启动

使用当前实际源码 `/path/to/project`。想在**新计算**中自动开一次页，可在my_case.py里显式设置：

```python
preview=Preview(enabled=True, port=8766, command=(
    "/path/to/project/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3",
    "/path/to/project",
))
```

先配已有bins与全新输出，再check；端口冲突只警告，不复用旧8765历史实例。自动preview的自有服务随本次计算结束停止，浏览器不关闭。若只是继续看**已经完成**的整链结果，可在终端运行以下只读服务（不启动求解器），再手动打开http://127.0.0.1:8766；Ctrl+C停止这一前台服务：

```sh
BORIS_VIEWER_INSTANCE=$(/path/to/project/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 -c 'import uuid; print(uuid.uuid4())')
/path/to/project/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 /path/to/project --manifest /path/to/project --port 8766 --instance "$BORIS_VIEWER_INSTANCE"
```

这个run.json是已完成结果，页面应显示已结束，不能称正在计算。查看另一运行须明确换其manifest并使用新实例/空闲显式端口。旧`preview.py start`是runs.json历史样本模式，不是新运行的manifest绑定入口；不会因为HTTP200就自动换成当前运行。当前没有发现阻断上述本地使用的路径/来源问题。本轮仅核对路径和既有元数据，没有开服务/浏览器或新求场。

## 零物理验证与边界

下列是开发者回归命令，已经通过，不是用户日常入口，也不要求用户为运行案例重跑测试。日常仅编辑my_case.py并使用上方check/运行命令。

```sh
python -B -m unittest discover -s tests -p test_fimrun.py -v
```

33项零物理测试通过，覆盖失败核记录/已审细核保留、固定日志预留、正确ready后4MiB日志。测试中的阶段executor、费用token、CP、报告是合成夹具，不是微磁科学证据。task-3另独立验证实际viewer的stdout/HTTP/ps、跨阶段协议和真实PIPE有界日志（REAL_VIEWER_INTEROP.json、REAL_PIPE_RESULT.json）。实际HTTP frame为抽稀JSON及身份头，磁盘保存态才是paired-f64。这些接口证据与下面的真实T=0科学worker证据分开保留。

## 真实 T=0：一次执行完成，保存证据独审通过

已经由[实际用户入口脚本](../../unified-entry-t0-control/my_case_t0.py)执行一次prepare_then_drive：canonical125×125×1、4×4×3nm、pbc110、mirrors10；默认Material、mu0H=(0,0,-.002)T，uniform A=+z/B=−z；准备100fs/T=0、tol=1A/m、max_updates=0；驱动25fs/T=0、J=0、xi=(0,0)、times=(0,)，save_every100、goal=none、preview关闭、无dt/2。实现身份为536a548；check与run真实退出均0。

真实静态保存态的独立A/B残差均为0A/m，原1A/m门通过；驱动step0独立检查通过。准备CP方向与drive seed、step0、drive CP方向逐字节一致，fresh交接来源hash正确，驱动时刻、耗散D和做功P均为0。原native先判断残差再判断更新上限，实际以residual_tolerance结束，没有放宽门。

实际调用：准备dynamic初场1+static初场1，独立initial/dynamic-final/static-final各1，共5完整场；drive初场1+step0独立1，共2完整场。整链**7完整场（3原生+4独立）、3原生Models、0ODE/静态更新、0编译/新核生成、0重试**。Models依据3份真实native request/result和已审每main一次构造计数；18是原生构造核FFT，不包括独立NumPy的所有FFT。七笔reserve全部settled，共用外部账且没有重复扣费。

冻结预算F=C=7/S0=0、60s、2GiB sampled owned、128MiB整root。实际外层0.898077709s、workflow0.578621250s，整尝试owned RSS采样峰129892352B；科学root＋control共26237084B。首次--check正确显示未来CP pending；真实prepare通过后才进行合格交接及drive预检，最后run.json为completed、drive阶段。实际输出与[保存证据审计](../../unified-entry-t0-control/SAVED_OUTPUT_AUDIT.json)、[封存回执](../../unified-entry-t0-control/POSTSEAL_CHECK.json)保留，116项长度/SHA绑定无差异。

实际使用既有 `current_sot_fine250_execution_20261016/bins` 的两个软链（目录名不改变125网格）：fim_user SHA cad3e301cbc0e0819b7786423552eda1f925ff8fb446d96c2318679972d0b7c7；fim_drive SHA 7e1f396c6f37473bba3e9fe2b0bd642dc372ee89287e2d1994a528cda34e6c40；canonical核SHA db71f379e2bea728a475d9e0c6e5e1183c7830ee1ba91e6909f84c532ec012b6。来源hash及实际请求已保存，科学源码未改、未推送。

task-3/unified_entry_t0_final_review/REVIEW.md已独立只读验收本节的T=0证据；非零500ps→静态→2ps衔接及失败阻断已另获上节独审。**固定驱态真实前台跟随已实测通过，单次BA数值及资源/阶段分配偏离见上节；不能据此宣称全协议通过或绝对无开销。** 任意材料/网格/镜像、时间精度、运动与长期稳定仍保留原科学限制，不是本轮必须自动补跑的清单。默认my_case.py的保存/目标/路径组合未逐字段执行，使用前必须先配置并check。
