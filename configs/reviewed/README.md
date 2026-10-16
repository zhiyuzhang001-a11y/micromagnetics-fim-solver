# 已审协议模板

阅读[本地交付状态与操作顺序](../../docs/LOCAL_DELIVERY_STATUS.md)。这六份配置保留实际材料/几何/SOT参数，仅将绝对IO地址替换为仓库内可编辑路径；它们是显式复现模板，不是新的运行授权。

1. coarse-25fs-2ps：已有125²合格CP的粗短窗。
2. fine-preparation：独立250²静态准备，输入为零求场映射适配器生成的两个OVF。
3. fine-25fs-2ps、fine-12p5fs-2ps：同一细CP的两个新分支，联合原严格门检查。
4. fine-drive50-resume2：仅在两条短窗通过后，从25fs2ps检查点续到50ps。
5. fine-zero50：相同细准备态的匹配零流。

缓存缺失应停止。runtime-bins只放fim_user/fim_drive；不要放生成器让cache-miss悄悄启动计算。源码原默认map生成器未被补丁自动替换。单作业上限、阶段总预算与科学目标分别检查，execution_completed不等于空间资格。当前科学结果中的半径/形变失败、速度/Hall null不能由这些模板改写。
