#pragma once
// Independent MPFR interval arithmetic. No production/Newell includes.
#include <mpfr.h>
#include <algorithm>
#include <array>
#include <string>
#include <stdexcept>
#include <ostream>
struct I {
 mpfr_t lo,hi;
 I(){mpfr_init2(lo,192);mpfr_init2(hi,192);mpfr_set_zero(lo,0);mpfr_set_zero(hi,0);}
 explicit I(double x):I(){mpfr_set_d(lo,x,MPFR_RNDD);mpfr_set_d(hi,x,MPFR_RNDU);}
 I(const I&x):I(){mpfr_set(lo,x.lo,MPFR_RNDD);mpfr_set(hi,x.hi,MPFR_RNDU);}
 I&operator=(const I&x){if(this!=&x){mpfr_set(lo,x.lo,MPFR_RNDD);mpfr_set(hi,x.hi,MPFR_RNDU);}return *this;}
 ~I(){mpfr_clear(lo);mpfr_clear(hi);}
 void check()const{if(!mpfr_number_p(lo)||!mpfr_number_p(hi)||mpfr_greater_p(lo,hi))throw std::runtime_error("invalid interval");}
 static I dyadic(const std::string&l,long lq,const std::string&u,long uq){I a;
  if(lq<0||uq<0||lq>256||uq>256||l.size()>100||u.size()>100)throw std::runtime_error("bounded dyadic");
  if(mpfr_set_str(a.lo,l.c_str(),10,MPFR_RNDD)||mpfr_set_str(a.hi,u.c_str(),10,MPFR_RNDU))throw std::runtime_error("dyadic integer parse");
  mpfr_div_2si(a.lo,a.lo,lq,MPFR_RNDD);mpfr_div_2si(a.hi,a.hi,uq,MPFR_RNDU);a.check();return a;}
 static I from_decimal(const std::string&l,const std::string&u){I r;
  if(l.size()>256||u.size()>256||mpfr_set_str(r.lo,l.c_str(),10,MPFR_RNDD)||mpfr_set_str(r.hi,u.c_str(),10,MPFR_RNDU))throw std::runtime_error("certified decimal interval parse");r.check();return r;}
 bool contains_zero()const{return mpfr_sgn(lo)<=0&&mpfr_sgn(hi)>=0;}
 std::string decimal(bool upper)const{mpfr_exp_t e;char*s=mpfr_get_str(nullptr,&e,10,80,upper?hi:lo,upper?MPFR_RNDU:MPFR_RNDD);if(!s)throw std::runtime_error("format");std::string v(s);mpfr_free_str(s);std::string sign;if(v[0]=='-'){sign="-";v.erase(0,1);}return sign+v.substr(0,1)+"."+v.substr(1)+"e"+std::to_string(e-1);}
};
inline I operator+(const I&a,const I&b){I r;mpfr_add(r.lo,a.lo,b.lo,MPFR_RNDD);mpfr_add(r.hi,a.hi,b.hi,MPFR_RNDU);r.check();return r;}
inline I operator-(const I&a,const I&b){I r;mpfr_sub(r.lo,a.lo,b.hi,MPFR_RNDD);mpfr_sub(r.hi,a.hi,b.lo,MPFR_RNDU);r.check();return r;}
inline I operator-(const I&a){I r;mpfr_neg(r.lo,a.hi,MPFR_RNDD);mpfr_neg(r.hi,a.lo,MPFR_RNDU);return r;}
inline I operator*(const I&a,const I&b){I r;mpfr_t d,u;mpfr_init2(d,192);mpfr_init2(u,192);bool first=true;
 for(auto x:{a.lo,a.hi})for(auto y:{b.lo,b.hi}){mpfr_mul(d,x,y,MPFR_RNDD);mpfr_mul(u,x,y,MPFR_RNDU);if(first||mpfr_less_p(d,r.lo))mpfr_set(r.lo,d,MPFR_RNDD);if(first||mpfr_greater_p(u,r.hi))mpfr_set(r.hi,u,MPFR_RNDU);first=false;}
 mpfr_clear(d);mpfr_clear(u);r.check();return r;}
inline I operator/(const I&a,const I&b){if(b.contains_zero())throw std::runtime_error("interval division zero");I inv;mpfr_ui_div(inv.lo,1,b.hi,MPFR_RNDD);mpfr_ui_div(inv.hi,1,b.lo,MPFR_RNDU);inv.check();return a*inv;}
inline I expi(const I&a){I r;mpfr_exp(r.lo,a.lo,MPFR_RNDD);mpfr_exp(r.hi,a.hi,MPFR_RNDU);r.check();return r;}
inline I erfi(const I&a){I r;mpfr_erf(r.lo,a.lo,MPFR_RNDD);mpfr_erf(r.hi,a.hi,MPFR_RNDU);r.check();return r;}
inline I sqrti(const I&a){if(mpfr_sgn(a.lo)<0)throw std::runtime_error("negative sqrt");I r;mpfr_sqrt(r.lo,a.lo,MPFR_RNDD);mpfr_sqrt(r.hi,a.hi,MPFR_RNDU);r.check();return r;}
inline I pii(){I r;mpfr_const_pi(r.lo,MPFR_RNDD);mpfr_const_pi(r.hi,MPFR_RNDU);return r;}
inline std::ostream&operator<<(std::ostream&s,const I&a){return s<<a.decimal(false)<<'\t'<<a.decimal(true);}
