# 本地安装版恢复候选 · P2 修订

适用范围：已验证的 macOS 27 arm64、系统 `/bin/sh`、`/bin/bash`、`/usr/bin/openssl`（本机 LibreSSL 3.3.6）及随系统提供的基本工具/框架。不要求 Xcode Python、系统 Python、Homebrew Python 或原 Conda。候选仍待独审。

归档包含固定 SHA256 的 arm64 Miniconda 引导安装器、全部 72 个精确 Conda 档案、程序 wheel/sdist、源码、许可证和 SHA 清单。引导器和全部科学载荷沿用已验证字节。先确认归档来源可信，保留许可与 notice。示例目标和工作路径必须不存在；WORK 不得含空格。恢复只在新目录安装，不初始化 shell，不更新原 base，不覆盖旧内核或数据。

## B：没有可用 Python 或 Conda

在 Recovery 目录打开终端，执行以下系统 shell 命令（替换两个新目录）：

```sh
/bin/sh ./bootstrap.sh /tmp/micromagnetics-restored-B /tmp/micromagnetics-restore-work-B micromagnetics-restored-b
```

这个入口先由系统 OpenSSL 对照脚本内固定的官方 SHA256 校验实际归档安装器，随后调用其 shell 安装器离线安装独立临时 bootstrap。**直到这个已验证安装器自己的 Python 可用后，才解析并逐文件核对归档清单，再执行 recover.py。** 不会先调用 `/usr/bin/python3` 或原 Conda。归档校验失败则不创建目标科学环境；已有目录一律拒绝。BOOTSTRAP.json 和 restore/RESTORED.json 记录解释器、校验及安装来源。直接用外部 Python 启动 recover.py 的旧 B 演练仅是历史证据，不再作为无 Python 恢复入口。

## A：现有 Conda 可用

显式使用该管理器自己的 Python（路径按实际安装位置填写），不使用开发者 Python：

```sh
/path/to/project/miniconda3/bin/python -I ./recover.py --branch A --manager /path/to/project/miniconda3 --prefix /tmp/micromagnetics-restored-A --work /tmp/micromagnetics-restore-work-A --kernel micromagnetics-restored-a
```

两条分支最终都从归档档案离线创建空 prefix，使用独立 Conda/pip/fimrun 缓存和本次自有配置，调用已验证 Conda 25.9 显式事务 API，不进行依赖求解或下载；其他管理器版本拒绝。程序从本地 wheel 非 editable 安装，执行 pip check、注册 prefix 内的新内核和零场原生装载自检。注册内核不代表启动新内核或完成科学回归；安装收据仍注明科学检查等级。需要正常内核发现时，另用新 prefix 的 `python -m ipykernel install --user --name <未使用名称>`，不要覆盖已有名称。

## 检查安装与环境缺失

日常只使用已有 `.py` / Notebook，并选择正确内核；不需要 .command 启动器。需要诊断时，在终端执行：

```sh
/bin/sh ./check-install.sh
# 恢复到其他位置时可明确传入 prefix 与内核名称：
/bin/sh ./check-install.sh /tmp/micromagnetics-restored-B micromagnetics-restored-b
```

脚本先检测解释器是否存在；缺失时明确给出本归档的 RECOVERY.md 和不需要外部 Python 的 bootstrap.sh 命令，退出 2，不尝试启动 doctor。解释器存在时才运行 `python -I -m fimrun doctor --native --kernel ...`，零求场、不联网修复或编译。Notebook 不加入安装单元或 sys.path 修改。

## 边界与证据

旧 c4 strict 的就地回退仍以其原 Codex Python/Homebrew 依赖完整为前提；新完整长期恢复只覆盖本归档与已验 OS/ABI。物理 state 恢复需显式选择，跨实现 strict 继续拒绝。未来系统、架构、长时间/任意材料精度均不由短回归保证。第二份备份在同一 Mac 的另一目录，不是离机灾备。

上一轮候选已在 OS 隔离下完成 A/B 重建与短回归。独审实际复跑短链和 .py，共新增 50 场，确认 51 数组与 QA 一致、32 原生文件未改、31 次零场测试通过；VS Code 五行表格/四幅 SVG 已目视通过。独审的新内核/HTTP 服务启动被执行器权限拒绝，该范围没有独立复跑，3D 预览前台仍未核实。本轮只修复恢复入口，不尝试绕过这些拒绝、不重新进行科学计算；P2 新故障分支以专门零场收据为准。

## Notebook1.4状态兼容

更新后选择新内核，不热重载已有模拟。普通state可恢复物理状态并重建私有历史；strict checkpoint仍要求同实现指纹，旧版本strict不能绕过校验，可用普通state分支。纯静态state的solver为unconfigured、dt=null，恢复后首次run显式dt。首次新构造默认打开viewer；旧构造传dt时保留旧默认。频率与新旧别名详见docs/interface-v01/NOTEBOOK_OUTPUTS.md。
