#pragma once
#include <mpfr.h>
#ifndef HP_BITS
#define HP_BITS 128
#endif
struct HP {
 mpfr_t v;
 HP(){mpfr_init2(v,HP_BITS);mpfr_set_zero(v,0);}
 HP(double x){mpfr_init2(v,HP_BITS);mpfr_set_d(v,x,MPFR_RNDN);}
 HP(const HP&x){mpfr_init2(v,HP_BITS);mpfr_set(v,x.v,MPFR_RNDN);}
 ~HP(){mpfr_clear(v);}
 HP&operator=(const HP&x){mpfr_set(v,x.v,MPFR_RNDN);return *this;}
 explicit operator double()const{return mpfr_get_d(v,MPFR_RNDN);}
 HP&operator+=(const HP&x){mpfr_add(v,v,x.v,MPFR_RNDN);return *this;}
 HP&operator-=(const HP&x){mpfr_sub(v,v,x.v,MPFR_RNDN);return *this;}
 HP&operator/=(const HP&x){mpfr_div(v,v,x.v,MPFR_RNDN);return *this;}
};
inline HP operator+(const HP&a,const HP&b){HP r;mpfr_add(r.v,a.v,b.v,MPFR_RNDN);return r;}
inline HP operator-(const HP&a,const HP&b){HP r;mpfr_sub(r.v,a.v,b.v,MPFR_RNDN);return r;}
inline HP operator-(const HP&a){HP r;mpfr_neg(r.v,a.v,MPFR_RNDN);return r;}
inline HP operator*(const HP&a,const HP&b){HP r;mpfr_mul(r.v,a.v,b.v,MPFR_RNDN);return r;}
inline HP operator/(const HP&a,const HP&b){HP r;mpfr_div(r.v,a.v,b.v,MPFR_RNDN);return r;}
inline bool operator<(const HP&a,const HP&b){return mpfr_less_p(a.v,b.v);}
inline bool operator>(const HP&a,const HP&b){return mpfr_greater_p(a.v,b.v);}
inline bool operator<=(const HP&a,const HP&b){return mpfr_lessequal_p(a.v,b.v);}
inline bool operator>=(const HP&a,const HP&b){return mpfr_greaterequal_p(a.v,b.v);}
inline bool operator==(const HP&a,const HP&b){return mpfr_equal_p(a.v,b.v);}
inline HP abs(const HP&a){HP r;mpfr_abs(r.v,a.v,MPFR_RNDN);return r;}
inline HP sqrt(const HP&a){HP r;mpfr_sqrt(r.v,a.v,MPFR_RNDN);return r;}
inline HP asinh(const HP&a){HP r;mpfr_asinh(r.v,a.v,MPFR_RNDN);return r;}
inline HP atan(const HP&a){HP r;mpfr_atan(r.v,a.v,MPFR_RNDN);return r;}
inline HP acos(const HP&a){HP r;mpfr_acos(r.v,a.v,MPFR_RNDN);return r;}
inline bool isfinite(const HP&a){return mpfr_number_p(a.v);}
