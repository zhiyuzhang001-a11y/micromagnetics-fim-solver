# 数学、单位与代码对照

本文解释当前离散实现，不更改算法或校准。模拟与离线后处理分别见[模拟教程](../examples/notebook_single_sim.ipynb)、[后处理教程](../examples/notebook_skyrmion_postprocess.ipynb)。完整默认值、允许选择与支持组合见[接口参考](API_REFERENCE.md)及[参数表](interface-v01/PARAMETERS.md)。历史固定案例见[原模型](MODEL_AND_UNITS.md)，其数值不是新实验默认值。

## 1. 网格与独立子晶格

单元中心、磁化和体积为

$$
\mathbf r_{j}=\mathbf o+(\mathbf j+\tfrac12)\odot\mathbf h,
\qquad V=h_xh_yh_z,
\qquad \mathbf M_i=M_{s,i}\mathbf m_i,\quad |\mathbf m_i|=1.
$$

$\mathbf o,\mathbf h$ 用 $\mathrm m$，$M_{s,i}$ 用 $\mathrm{A/m}$，$\mathbf m_i$ 无量纲。`Grid.origin/cell_size/cells`对应几何；数组每子晶格形状为`(nz,ny,nx,3)`，x最快；当前仅nz=1。FiM的A/B是同网格内两个方向场，各有自己的Ms，不是上下两层。

FM使用完整体积；FiM采用固定等半体积约定：

$$
\overline{\mathbf M}=\tfrac12(M_{s,A}\mathbf m_A+M_{s,B}\mathbf m_B).
$$

对应`FiMMaterial.convention='equal_half_volume'`，不能替换成未除2的净磁化。单位方向OVF无需物理Ms；A/m OVF必须提供各自正Ms，才能核对方向。来源：`model.py`、`postprocess/io.read_ovf`。

## 2. 能量和有效场

以下是实际正向邻接键定义，$\Delta_d\mathbf m=\mathbf m(\mathbf r+\mathbf h_d)-\mathbf m(\mathbf r)$。能量用$\mathrm J$，$\mu_0\mathbf H$用$\mathrm T$；场参数`H_ext`是$\mathrm{A/m}$，`B_ext`是$\mathrm T$，二者互斥。

$$
\mathbf H_i=-\frac{1}{\mu_0 w_i M_{s,i}V}\frac{\partial E}{\partial\mathbf m_i},
\qquad w_{\rm FM}=1,\quad w_A=w_B=\tfrac12.
$$

离散导数、开放边界和有限镜像以原实现为准，不把连续公式当作网格收敛保证。

| 项 | 当前离散能量 | 代码/参数及限制 |
|---|---|---|
| FM交换 | $E_{\rm ex}=\sum_{j,d}VA\lVert\Delta_d\mathbf m\rVert^2/h_d^2$ | `Exchange.A`，J/m；FM开放边界 |
| FiM自交换及交叉梯度 | $E_{\rm ex}=\sum_{j,d,i}VA_i\lVert\Delta_d\mathbf m_i\rVert^2/(2h_d^2)+\sum_{j,d}VA_{nh}\Delta_d\mathbf m_A\cdot\Delta_d\mathbf m_B/(2h_d^2)$ | `FiMExchange.A_A/A_B/Anh`，J/m；非零Anh仅periodic_xy，保持原稳定域 |
| 均匀耦合 | $E_h=-2A_hV\sum_j\mathbf m_A\cdot\mathbf m_B$ | `OnsiteCoupling.Ah`，J/m³；负值倾向反平行 |
| FiM DMI | $E_D=\sum_{j,d\in\{x,y\},i}VD_i[m_{i,d}m'_{i,z}-m_{i,z}m'_{i,d}]/(2h_d)$ | `DMI.D_A/D_B`，J/m²；FM DMI不支持 |
| 单轴各向异性 | $E_K=\sum_{j,i}w_iV[K_{1,i}s_i+K_{2,i}s_i^2],\ s_i=1-(\mathbf m_i\cdot\mathbf a_i)^2$ | FM仅K1；FiM支持K1/K2，J/m³；轴归一 |
| 退磁 | $E_d=-\mu_0 V\sum_j\overline{\mathbf M}_j\cdot\mathbf H_{d,j}/2$ | FiM共享Mbar；FM替换为自身M；有限镜像不是无限PBC |
| Zeeman | $E_Z=-\mu_0 V\sum_j\overline{\mathbf M}_j\cdot\mathbf H_{\rm ext}$ | FM用自身M；`Zeeman`未加入即无该项 |

能量/场来源为`src/user_native.cpp`、`src/grid_fields.cpp`、`validation/fm/fm.hpp`，参数分组见`model.py`和[合同](interface-v01/CONTRACT.md)。关闭某能量项意味着不执行其贡献；关闭能量曲线输出不等于关闭求场所需能量 bookkeeping。材料或能量结构变化需branch/new model。

## 3. Gilbert动力学、SOT与采样

现有固定步RK4调用Gilbert H约定：

$$
\dot{\mathbf m}_i=-\frac{\gamma_{H,i}}{1+\alpha_i^2}
\left[\mathbf m_i\times\mathbf H_i+\alpha_i\mathbf m_i\times(\mathbf m_i\times\mathbf H_i)\right].
$$

`Sublattice.gamma_H`单位$\mathrm{m/(A\,s)}$，alpha无量纲，不是以T为单位的gamma。对应`src/gilbert.hpp`、`Simulation._rhs/_rk4_step`。当前只有固定dt，duration及保存间隔须为dt整数倍，不静默裁短。

FiM显式恒定电流的原有效场扩展为

$$
\mathbf q=\mathbf d\times\mathbf J,\quad C_i=\frac{\xi_i(\mu_B/e)}{M_{s,i}h_z},\quad
\mathbf H_{{\rm SOT},i}=-\frac{C_i}{\gamma_{H,i}}[\mathbf m_i\times\mathbf q+r_i\mathbf q].
$$

`FiMSOT.J`为传统电流密度A/m²，d=`incident_direction`，r=`field_like_A/B`。此场加入同一Gilbert RHS；它是已实现的现象学映射，不是输运求解，FM SOT/STT/AC不支持。`None`关闭电流。来源`src/current_sot.hpp`；不改变原符号或系数。

## 4. 静态停止与物理时间

$$
R_i=\max_j\left|\mathbf H_{i,j}-(\mathbf m_{i,j}\cdot\mathbf H_{i,j})\mathbf m_{i,j}\right|,
\qquad X_i=R_i/M_{s,i}.
$$

R用A/m，X无量纲。Notebook API1.3 `relax(mxh=..., residual=..., consecutive=...)`要求A/B在同一接受态同时满足两门，并计数不同接受态；初态只算一次。对应`Simulation._residual`、`ResidualAndMxh.satisfied`、`NotebookSimulation.relax`。接近零净磁化时也不能用净Ms归一。

静态接受迭代k不是物理时间t；静态不增加时钟、不产生动态速度或虚构耗散。`save_every_steps`用于静态，`save_interval`用于动态。保存与strict checkpoint实现身份限制见[状态](interface-v01/STATE_AND_CONTINUITY.md)。

## 5. 有符号拓扑与周期局部图

每个有向三角形贡献

$$
\Omega(\mathbf a,\mathbf b,\mathbf c)=2\operatorname{atan2}\!\left(\mathbf a\cdot(\mathbf b\times\mathbf c),\ 1+\mathbf a\cdot\mathbf b+\mathbf b\cdot\mathbf c+\mathbf c\cdot\mathbf a\right),
\qquad Q=\frac{1}{4\pi}\sum_T\Omega_T.
$$

`A/B_Q`无量纲，保留符号；奇异三角形或近零拓扑不能用除Q造正常中心。拓扑中心是原算法局部周期图中的有符号一阶矩：先按网格邻接展开三角形，再给整体重心选周期像。`geometry.measure`→`topo_x/y`、`valid_topology`；不以Q符号替代相位绕数n。

周期最近像为

$$
\operatorname{image}(\Delta,L)=\Delta-L\left\lfloor\Delta/L+\tfrac12\right\rfloor.
$$

对应`geometry.image`。PBC必须有来源；缺boundary整帧测量失败，不能自动选open。有限mirrors缺失保持未知。

## 6. 轮廓面积、半径与形状

唯一可缩的$m_z=0$轮廓取CCW顶点$(x_j,y_j)$，令$c_j=x_jy_{j+1}-x_{j+1}y_j$：

$$
A=\tfrac12\sum_jc_j,\quad
\mathbf r_A=\frac{1}{6A}\sum_j(\mathbf v_j+\mathbf v_{j+1})c_j,\quad R=\sqrt{A/\pi}.
$$

对应`geometry.moments/measure`→`area_m2`、`area_x/y`、`radius_m`。A为m²，其余长度m；显示可用nm，CSV仍SI。主面积协方差为

$$
S=\frac{1}{A}\int_{\mathcal A}(\mathbf r-\mathbf r_A)(\mathbf r-\mathbf r_A)^T\,dA,\quad
 a=2\sqrt{\lambda_{\max}},\quad b=2\sqrt{\lambda_{\min}},\quad
 \rho=a/b,\quad\epsilon=(a-b)/(a+b).
$$

`major_m/minor_m`是**半轴**，不是全轴长；`axis_ratio`、`ellipticity`无量纲。`axis_rad`主轴模π；近圆或矩不可分辨时无效，不能画成0方向。面积有效与拓扑/方向有效分开。

## 7. 螺旋度与A/B参考

沿轮廓等物理弧长采样，$\psi=\operatorname{atan2}(m_y,m_x)$、$\phi=\operatorname{atan2}(y-y_A,x-x_A)$。CCW相位增量给绕数n，随后

$$
Z=\frac1N\sum_{k=1}^{N}e^{\mathrm{i}(\psi_k-n\phi_k)},\quad
\chi_{\rm raw}=\arg Z,\quad C=|Z|,\quad
\delta_k=\operatorname{wrap}(\psi_k-n\phi_k-\chi_{\rm raw}).
$$

`geometry.phase`→`n/chi_raw/coherence/phase_rms/phase_p95`，rms为$\sqrt{\sum\delta_k^2/N}$，p95为$|\delta|$的95%分位。当前有效螺旋度还须现有n=1、极性、几何、相干及校准门；只有`chi_rad`配合`valid_helicity`是有效测量。强相位调制不能只报圆均值作“正常螺旋度”。

仅声明`ab_reference='antiparallel'`且原有效门通过时：

$$
\chi_{B,\rm corrected}=\operatorname{wrap}(\chi_B-\pi),\qquad
\Delta\chi_{AB}=\operatorname{wrap}(\chi_{B,\rm corrected}-\chi_A).
$$

对应`B_chi_corrected_rad/AB_chi_difference_rad`。不自动猜材料参考关系。

## 8. 轨迹与速度

wrapped中心折回盒内；unwrapped满足

$$
\mathbf r^{\rm unwrapped}=\mathbf r^{\rm wrapped}+\mathbf n\odot\mathbf L.
$$

整数像`*_image_x/y`来自公开wrapped坐标，包括B初始对齐；它不是丢帧历史的圈数恢复。启用`assume_temporal_sampling=True`表示用户确认每次实际位移小于半盒；算法不能认证漏掉整圈。相对B−A的最近像诊断不自动成为唯一连续分支。

同run/segment、三连续有效动态帧，以实际时间戳（等间隔或非等间隔）定义局部二次插值：

$$
\mathbf v(t_1)=\sum_{k=0}^{2}\mathbf r(t_k)\ell'_k(t_1),\qquad
\ell_k(t)=\prod_{j\ne k}\frac{t-t_j}{t_k-t_j}.
$$

对应`pipeline._analyze_rows`→`*_area/topo_vx/vy_mps`。端点NaN；非递增时间、失效或分段断轨。`valid_velocity`是双方**面积中心**导数资格，拓扑还需其值有限。窗口线性拟合仅显式`velocity_window_s=(lo,hi)`请求，不是默认平滑。

缺动态time时新界面按来源输入索引画散点并明确“非物理时间”，不连成时间曲线、不造速度；静态只用接受迭代或明确标识索引。

## 9. 有效性、误差与来源

训练位置包络传播为$e_v=\sum_k|\ell'_k(t_1)|e_{r,k}$，对应`*_v_position_envelope_mps`；不包含模型、时间未知或时间截断误差，不是置信区间。冻结校准不重训，域外、不唯一轮廓、多对象、半盒歧义、相位无效均保留NaN和原因。

`valid_pair`只表示A/B解析成功。逐指标geometry/topology/axis/helicity/tracking/velocity/relative分别判断；raw仅诊断。`source_bindings`保留输入字节、mapping/evidence、实现身份、校准与选项；显示筛选不修改SI审计底稿。[来源/拒绝合同](interface-v01/SKYRMION_POSTPROCESSING.md)说明最新segment限制与历史state拒绝。

## 缓存能量CSV映射（Notebook1.4）

七分项及总能量、旧energy_J别名、共享项只计一次、FM缓存重排见[输出列与源码索引](interface-v01/NOTEBOOK_OUTPUTS.md#标量与能量列)。列值来自已接受态缓存，输出不增加求场；SOT功与阻尼耗散单列。
