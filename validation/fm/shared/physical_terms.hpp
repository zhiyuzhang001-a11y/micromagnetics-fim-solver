#pragma once
// Field uses physical coefficients; weight applies only to energy convention.
struct LocalTerm {double energy; V field;};
LocalTerm exchange_bond(V difference,double volume,double A,double h,double Ms,double weight){
 return {weight*volume*A*dot(difference,difference)/(h*h),difference*(2*A/(mu0*Ms*h*h))};
}
LocalTerm uniaxial(V m,V axis,double volume,double K1,double K2,double Ms,double weight){
 double u=dot(m,axis),s=1-u*u;
 return {weight*volume*(K1*s+K2*s*s),axis*(2*u*(K1+2*K2*s)/(mu0*Ms))};
}
LocalTerm zeeman(V m,V external,double volume,double Ms,double weight){
 return {-weight*mu0*volume*Ms*dot(m,external),external};
}
