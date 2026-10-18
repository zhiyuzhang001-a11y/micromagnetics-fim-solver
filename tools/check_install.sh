#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-only
# Optional terminal diagnostic, not a daily launcher or a Notebook install cell.
set -eu
[ "$#" -le 2 ] || { printf '%s\n' 'Usage: /bin/sh check-install.sh [ENV_PREFIX [KERNEL_NAME]]' >&2; exit 2; }
release_dir=$(CDPATH= cd "$(/usr/bin/dirname "$0")" && pwd -P)
prefix=${1:-"$HOME/miniconda3/envs/micromagnetics"}
kernel=${2:-micromagnetics}
if [ ! -x "$prefix/bin/python" ]; then
    printf '%s\n' "micromagnetics 环境缺失或解释器不可执行：$prefix/bin/python" "恢复说明：$release_dir/RECOVERY.md" '不需要系统 Python 或现有 Conda。请在终端执行以下恢复命令，并把 PREFIX/WORK 换成不存在的绝对路径：' >&2
    printf '  /bin/sh "%s/bootstrap.sh" PREFIX WORK micromagnetics-restored\n' "$release_dir" >&2
    exit 2
fi
exec "$prefix/bin/python" -I -m fimrun doctor --native --kernel "$kernel"
