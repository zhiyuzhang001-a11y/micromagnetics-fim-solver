# 仓库模板：本机日常编辑桌面参数源，用法见 docs/UNIFIED_ENTRY.md。
# 独立使用此模板前需配置已有程序、已验缓存与全新输出目录。

from fimrun import (
    Case,
    Mesh,
    Material,
    Field,
    Initial,
    Dynamics,
    Preparation,
    Drive,
    PreparedState,
    Runtime,
    Budget,
    Output,
    Preview,
    run,
)

case = Case(
    # 运行流程
    workflow='prepare_then_drive',

    # 网格
    mesh=Mesh(
        n=(125, 125, 1),  # 整数网格数
        cell_nm=(4., 4., 3.),  # nm
        pbc=(1, 1, 0),
        mirrors=(10, 10),
    ),

    # 材料（A/B 顺序）
    material=Material(
        Ms_Apm=(300000., 600000.),  # A/m
        A_Jpm=(5e-12, 5e-12),  # J/m
        Ah_Jpm3=-8e6,  # J/m³
        Anh_Jpm=-5e-12,  # J/m
        D_Jpm2=(.00105, .00105),  # J/m²
        K1_Jpm3=(109000., 109000.),  # J/m³
        K2_Jpm3=(0., 0.),  # J/m³
        axes=((0., 0., 1.), (0., 0., 1.)),
        alpha=(.01, .01),
        gamma_H_m_per_As=(221276.1569, 221276.1569),
        active=(1, 1, 1, 1),
    ),

    # 外场
    field=Field(
        mu0_H_T=(0., 0., -.002),  # T
    ),

    # 初始磁化
    initial=Initial(
        kind='canonical_legacy',
    ),

    # 动态与静态弛豫
    preparation=Preparation(
        dynamics=Dynamics(
            dt_fs=100.,  # fs
            T_ps=500.,  # ps
        ),
        tol_Apm=1.,  # A/m
        max_updates=30000,  # 静态更新预算
    ),

    # 电流驱动
    drive=Drive(
        dynamics=Dynamics(
            dt_fs=25.,  # fs
            T_ps=2.,  # ps
        ),
        Jc_Apm2=(1e11, 0., 0.),  # A/m²
        xi=(.1, .1),
        field_like_ratio=(0., 0.),
        times_ps=(0., 2.),  # ps
    ),

    # 程序与缓存路径
    runtime=Runtime(
        bins='build-unified',
        cache='output/kernel-cache',
    ),

    # 整链预算
    budget=Budget(
        new_fields=100000,  # 新求场次数上限
        wall_s=600.,  # 秒
        rss_bytes=2 * 1024 ** 3,  # 字节
        output_bytes=1024 ** 3,  # 字节
    ),

    # 输出
    output=Output(
        directory='output/my-case',
        save_every=100,
        goal='observe',
    ),

    # 预览
    preview=Preview(
        enabled=False,
        port=8766,
        command=(),
    ),
)

if __name__ == '__main__':
    run(case, script=__file__)
