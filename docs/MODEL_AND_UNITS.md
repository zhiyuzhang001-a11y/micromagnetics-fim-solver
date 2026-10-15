# Fixed model and units

Geometry: 125×125×1 cells of 4×4×3 nm, XY periodic local stencils and a
frozen demagnetization tensor with finite mirror count 10. No infinite-periodic
limit is asserted. Texture arrays are unit directions, ordered A then B with
x fastest. H is A/m, energy J, material coefficients SI.

Ms_A=300000 A/m, Ms_B=600000 A/m; A_A=A_B=5e-12 J/m;
Ah=-8e6 J/m³; Anh=-5e-12 J/m; D_A=D_B=0.00105 J/m²;
K1_A=K1_B=109000 J/m³, K2=0, easy axis +z.
Applied mu0 H_z=-0.002 T; Gilbert gamma_G=221276.1569 and alpha=0.01.
These synthetic research parameters do not establish CoGd material fidelity.

Demagnetization and Zeeman energy use Mbar=(Ms_A*m_A+Ms_B*m_B)/2.
The selected implementation retains the overall energy factor and own-Ms field
mapping. Do not substitute another code's summed-magnetization convention.
Energy output parts are self gradient, cross gradient, homogeneous exchange,
DMI, anisotropy, demagnetization and Zeeman, in that order. The energy origin is
an actual model evaluation, not zero by convention.

The public main has fixed guards, not a parameter tuning interface. Nondefault
spatial alpha/gamma, compensation, driving, temperature and general spatial K2
are unsupported here. The separate label target tests swapped material identity
for precisely 16+16 updates at 12.5 fs; it does not generalize the static entry.
The independent reader rejects noncanonical config headers and nonmatching kernel
hashes, and recomputes fields with the same fixed material constants.
