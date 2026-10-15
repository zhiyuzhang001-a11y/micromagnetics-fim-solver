# Non-GPU acceleration research candidates

This is a research survey, not implemented acceleration or measured speedup for
this package. GPU execution is excluded. Verify precise upstream versions before
using these methods. Existing FFT plans and kernel spectra are already reused.
A cached H(m) at one linearization state does not remove H(v)/Jv demagnetization
work. Implicit stability does not establish fast-mode amplitude/phase accuracy.

## 1. OOMMF：CPU线程、静态CG与嵌入自适应积分

OOMMF的Oxs求解器支持CPU多线程，静态最小化有`Oxs_CGEvolve`，动力学有多种带步长控制的RK。官方对其特定实现的计数是：用整步与两个半步作误差估计的`rk4`每次需要11次RHS；Dormand–Prince家族的嵌入5(4)方法接受步6次、拒绝步7次。后者的计数须按已有起点导数可复用的正常连续步理解，首步、缓存失效及其他实现另计；它不是“所有RK4都要11次”或“所有RK45都要6次”。[官方evolver文档](https://math.nist.gov/oommf/doc/userguide21a3/userguide-xml/sec_oxsEvolvers.html)

可借鉴的是按精度与单位物理时窗比较总RHS/全场次数，而不是只比积分器名称。静态CG只能用于平衡求解，不能代替需要真实时间轨迹的动力学。线程数也不是越大越好：官方排错文档说明超过硬件线程数会引入切换开销。对25²等小网格，线程启动、同步和内存开销可能超过收益；当前125²是否受益仍需专项实测。[官方线程与性能说明](https://math.nist.gov/oommf/doc/userguide21a2/userguide/Troubleshooting.html)

## 2. BORIS：CPU并行与退磁场多项式外推

BORIS原论文说明CPU共享内存并行使用OpenMP，FFT使用启用线程的FFTW3。这证明了其CPU实现路径，并不证明本项目已调用这些线程接口，也不包含M4上的收益结论。论文中的GPU pipelined convolution是另一执行后端，不可拿来支持CPU加速估计。[BORIS原论文，计算性能部分](https://knowledge.lancashire.ac.uk/36281/1/36281%205.0024382.pdf)

BORIS另有已实现的退磁场高阶多项式外推：保存先前完整退磁结果，在显式积分子步近似退磁场；自退磁贡献单独逐子步计算，并需启动历史与阶数匹配。这是增加了可控近似的方法，不是任意跳过RK stage的场。若本项目采用，必须另列退磁近似误差、启动/恢复历史、拒步及变步长语义，重新核快模幅相与纹理观测，不能套用论文倍率。[v3.4发布说明](https://www.boris-spintronics.uk/boris-v3-4-released/)、[退磁场外推原论文](https://clok.uclan.ac.uk/42230/1/Speeding_up_explicit_numerical_evaluation_methods_for_micromagnetic_simulations_using_demagnetizing_field_polynomial_extrapolation.pdf)

## 3. MuMax3：阶数更高不保证更快

MuMax3默认使用Dormand–Prince RK45；官方说明RK56通常不比RK45更快，RK23在少动力学的松弛中可能更合适。该经验支持按具体任务选择方法，不能推出任一高阶法一定省时。其CUDA实现也不能直接作为Mac M4 CPU替代程序；这里只借鉴误差控制与工作量比较。[MuMax3官方API，Running](https://mumax.github.io/api.html)

## 4. MuMax+：多种嵌入求解器的选择

MuMax+的`TimeSolver`提供多种RK方法、误差和自适应步长控制，适合研究不同嵌入对在同一模型下的成本。它与MuMax3应分别记录版本和接口，不能合并成一个实现或默认同一求解器。MuMax+同样属于CUDA路线，本项目没有验证其在M4 CPU运行或与当前共址连续FiM模型直接对应。[TimeSolver官方API](https://mumax.github.io/plus/_api/mumaxplus/mumaxplus.TimeSolver.html)、[官方项目文档](https://mumax.github.io/plus/)

## 5. Fidimag：BDF/Krylov与线性化态场缓存

Fidimag有C/Cython、OpenMP和FFT路径，并提供SD及Hubert静态最小化器。其当前driver文档列出CVODE BDF：Newton非线性迭代配合重启GMRES，并暴露有效场Jacobian相关接口。同一个`t,m`线性化态的完整有效场可在一批Jv中缓存；缓存只在该态保持有效，不能跨状态或RK stage直接沿用。此处值得借鉴的是明确缓存失效条件和矩阵自由算子，而不是只把显式步长换大。[DriverBase文档](https://fidimag.readthedocs.io/en/latest/api/generated/fidimag.common.driver_base.html)、[Hubert minimiser文档](https://fidimag.readthedocs.io/en/latest/api/generated/fidimag.common.hubert_minimiser.html)、[项目说明](https://fidimag.readthedocs.io/en/latest/)

缓存线性化态的H(m)不能消除方向场H(v)/Jv所需的退磁算子工作，不能据此宣称每个Newton批次只需一次退磁；完整成本仍须按具体Jv实现及实际Krylov调用次数核算。[DriverBase的线性化态缓存接口](https://fidimag.readthedocs.io/en/latest/api/generated/fidimag.common.driver_base.html)

迁移仍缺本项目所需的共址连续双亚晶格、ownMs及总体积权映射证据。Fidimag的FMM/Barnes–Hut文档明确讨论atomistic退磁；不能据此宣称已有适配本连续FiM单元平均退磁的即插即用FMM。[官方FMM说明](https://fidimag.readthedocs.io/en/latest/physics_num_methods/demag_fmm.html)

## 6. Nmag：MPI、FEM–BEM与压缩边界矩阵

Nmag的路线是有限元/边界元、MPI网格分区及BDF/Krylov时间步进。官方MPI示例记录ParMETIS分区，HLib用于压缩BEM矩阵；这些解决的是不同层次的空间算子和求解成本。旧文档同时明确：其学术HLib库不并行，存储在master上，其他计算仍可MPI。不能把“支持MPI”概括成所有代价都已并行。[MPI示例](https://nmag-project.github.io/nmag-doc/example_mpi1/doc.html)、[HLib与MPI限制](https://nmag-project.github.io/nmag-doc/example_phi_BEM_hlib/doc.html)、[步进容差示例](https://nmag-project.github.io/nmag-doc/example_tolerances/doc.html)、[官方手册中的BDF/Krylov参数](https://nmag-project.github.io/current/manual/manual.pdf)

这提示隐式线性求解和长程场压缩应分别分析；它不支持直接替换当前规则网格FFT。FEM–BEM离散、边界处理、依赖栈和M4部署均需重新核验，本轮未安装或迁移。

## 7. magnum.np：CPU张量/FFT与隐式接口的边界

magnum.np以PyTorch张量和FFT构造有限差分计算，可使用CPU，并提供SciPy求解器接口，包括BDF包装。不能仅据“有BDF”推断其已使用稀疏Jacobian、解析Jv或可扩展预条件器；这些实现细节本轮尚未逐版本源码核实。CPU设备、dtype、跨框架转换及临时张量开销都属于后续实际成本。[原论文及公开全文入口](https://pmc.ncbi.nlm.nih.gov/articles/PMC10368681/)、[出版方原文](https://doi.org/10.1038/s41598-023-39192-5)

本项目125²、双亚晶格、每格3个笛卡尔分量，共`n=2×125×125×3=93750`个变量。若有人显式形成dense double的`n×n`矩阵，仅元素就需`n²×8=70,312,500,000 bytes≈70.3 GB`，尚不含分解和工作区。这只是条件性尺寸估算，**不是magnum.np实际分配该矩阵的事实**；球面切空间、稀疏或矩阵自由表示会改变问题。必须先查Jacobian/Jv实现再评价隐式可行性。

## 8. magnum.fe：局部预条件与开闭源分支

magnum.fe的LLG资料给出BDF/CVODE和预条件器路线：局部强项可以进入预条件器，非局部退磁不必放入预条件器；这不等于从完整RHS移除退磁。可借鉴的是用便宜的强耦合近似改善Krylov收敛，而不是构造稠密全Jacobian。[官方LLG/CVODE资料](https://micromagnetics.org/magnum.fe/llg.html)

官网2015公告明确区分开源与闭源分支，部分算法加速当时仅在闭源分支。不能把公告性能或后续闭源结果当作当前开源可复制能力。上述预条件器细节还需对准备使用的具体版本源码复核；M4部署和当前FiM映射均未验证。[官方项目公告](https://micromagnetics.org/)

## 9. MicroMagnetic.jl：CPU路径、SD与显式几何方法

MicroMagnetic.jl提供CPU/FFT路线；本次在线`driver.jl`可见SD，以及RungeKutta、DormandPrince、Cayley变体和GPSM等积分器选择。该入口列出的支持方法中未见BDF，这不是对全部扩展库或未来版本的全局否定。Cayley/球面方法仍须验证快模态的幅度、相位和耗散，不能用单位长度保持代替动态精度。[官方项目文档](https://magneticsimulation.github.io/MicroMagnetic.jl/dev/)、[本次读取的driver源码](https://github.com/MagneticSimulation/MicroMagnetic.jl/blob/master/src/driver.jl)

官方AFM skyrmion示例位于atomistic模块。交错原子格点的反铁磁模型不能直接等同于当前每个连续单元共址的两套磁化；即便软件支持两类模型，也必须重新审查交换、退磁、体积与时间尺度映射。[原子AFM示例](https://magneticsimulation.github.io/MicroMagnetic.jl/dev/atomistic/skyrmion_afm)

## 10. magnum.fd：CPU FFTW与可选CVODE

magnum.fd是有限差分/FFT程序，安装文档提供CPU构建、FFTW及可选CVODE接口，可用于了解既有显式/隐式软件组织方式。但文档含旧Python及CVODE 2.7.0时代依赖，不能把历史安装步骤当作当前M4已验证方案，也不能将“可选CVODE”解释成所有松弛/停止语义都兼容。[官方安装与CVODE说明](https://micromagnetics.org/magnum.fd/install.html)、[官方solver接口及限制](https://micromagnetics.org/magnum.fd/solver.html)

## 面向本项目的候选顺序

以下是后续专案顺序建议，不是实施或benchmark授权。先按同物理时窗、同误差门和完整交付成本比较，再决定是否改算法；依据来自上面的官方线程、积分器、外推和隐式实现证据。

1. **先定位。** 优先复用已有记录，另获批准后才添加剖析：分清setup、RHS/局部场、FFT、诊断、写盘、恢复与外层控制，并统计接受/拒绝步在单位物理时窗内的总工作。当前固定步RK4没有嵌入误差控制，不能为它虚构自适应拒步率。FFT调用频繁不等于已测得其独占耗时最大。
2. **先研究等价工程改动。** 可依次核临时数组与内存复制、循环融合、计划策略、线程数及输出组织。保留异常时的完整恢复和必要证据。当前FFTW plan与六个核频谱已经进程内复用，不能把“加入已有缓存”当新优化收益；小网格和线程过量可能负收益。任何收益均未实测。
3. **再比较嵌入自适应。** 在相同方向、幅相、能量与物理时窗门下比较总RHS、拒步、末态/事件和完整outer，不仅比较接受步数。缓存起点导数的有效性、归一化、拒步回滚及真实恢复必须冻结。更高阶不自动更快，且不改变静态与动力学的用途边界。[OOMMF方法/计数](https://math.nist.gov/oommf/doc/userguide21a3/userguide-xml/sec_oxsEvolvers.html)、[MuMax3选择经验](https://mumax.github.io/api.html)
4. **退磁外推单列近似预算。** 只有在完整场参考旁核清局部/长程分离、自项、外推历史、启动与误差传播后再评估；不得跳过不同RK stage的完整场却称完全等价。论文在其它模型/硬件的加速不能转写为M4收益。[外推原论文](https://clok.uclan.ac.uk/42230/1/Speeding_up_explicit_numerical_evaluation_methods_for_micromagnetic_simulations_using_demagnetizing_field_polynomial_extrapolation.pdf)
5. **证实刚性后再审matrix-free BDF/IMEX。** 需要实际谱/步长或拒步证据，并计Newton、Jv、Krylov及每次非局部场成本。候选是保留A/B局部强耦合块的预条件器，而非无依据解耦两亚晶格；IMEX的分裂和退磁处理也需独立误差分析。隐式稳定不免除快模态幅相精度，不能只因能走大步就宣布更快。[Fidimag BDF/Jv机制](https://fidimag.readthedocs.io/en/latest/api/generated/fidimag.common.driver_base.html)、[magnum.fe隐式接口](https://micromagnetics.org/magnum.fe/llg.html)
