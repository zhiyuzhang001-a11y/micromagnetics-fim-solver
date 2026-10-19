# Fixed model and units

> **Historical fixed-tool evidence.** Commands, limits and results below describe the archived entry, not the current installed Notebook API. Start with the [current simulation Notebook](../examples/notebook_single_sim.ipynb), [API reference](API_REFERENCE.md) and [current mathematics](MATHEMATICS.md). Historical values and verdicts are retained.

Geometry: $125\times125\times1$ cells of $(4,4,3)\,\mathrm{nm}$, XY periodic local stencils and a
frozen demagnetization tensor with finite mirror count 10. No infinite-periodic
limit is asserted. Texture arrays are unit directions, ordered A then B with
x fastest. H is A/m, energy J, material coefficients SI.

$M_{s,A}=300000\,\mathrm{A/m}$, $M_{s,B}=600000\,\mathrm{A/m}$; $A_A=A_B=5\times10^{-12}\,\mathrm{J/m}$;
$A_h=-8\times10^6\,\mathrm{J/m^3}$; $A_{nh}=-5\times10^{-12}\,\mathrm{J/m}$; $D_A=D_B=0.00105\,\mathrm{J/m^2}$;
$K_{1,A}=K_{1,B}=109000\,\mathrm{J/m^3}$, $K_2=0$, easy axis $+z$.
Applied $\mu_0 H_z=-0.002\,\mathrm T$; Gilbert $\gamma_G=221276.1569$ (H convention) and $\alpha=0.01$.
These synthetic research parameters do not establish CoGd material fidelity.

Demagnetization and Zeeman energy use $\overline{\mathbf M}=(M_{s,A}\mathbf m_A+M_{s,B}\mathbf m_B)/2$.
The selected implementation retains the overall energy factor and own-Ms field
mapping. Do not substitute another code's summed-magnetization convention.
Energy output parts are self gradient, cross gradient, homogeneous exchange,
DMI, anisotropy, demagnetization and Zeeman, in that order. The energy origin is
an actual model evaluation, not zero by convention.

The archived fixed-model public entry had fixed guards, not a parameter tuning interface. Nondefault
spatial alpha/gamma, compensation, driving, temperature and general spatial K2
are unsupported here. The separate label target tests swapped material identity
for precisely 16+16 updates at 12.5 fs; it does not generalize the static entry.
The independent reader rejects noncanonical config headers and nonmatching kernel
hashes, and recomputes fields with the same fixed material constants.

See the [current LaTeX formula/code map](MATHEMATICS.md) for notation. Historical numbers, criteria and limitations in this document retain their original scope.
