#pragma once
#include "interval192.hpp"
#include <fstream>
#include <filesystem>
#include <vector>
struct ABD {I A,B,D,faceB,faceD;};
inline ABD abd(const I&t,const I&h,bool contact){
 if(mpfr_sgn(t.lo)<=0)throw std::runtime_error("positive t only");
 I r=contact?h:I(0),rootpi=sqrti(pii());
 auto g=[&](const I&x){return expi(-(t*t*x*x));};
 auto f=[&](const I&x){return rootpi*erfi(t*x)/(I(2)*t);};
 auto G=[&](const I&x){return x*f(x)+g(x)/(I(2)*t*t);};
 ABD q;q.A=G(r+h)-I(2)*G(r)+G(r-h);
 q.B=contact?f(r+h)-I(2)*f(r)+f(r-h):I(0);
 q.D=I(2)*g(r)-g(r+h)-g(r-h);
 q.faceB=f(r+h)-f(r-h);q.faceD=I(2)*g(r)+g(r+h)+g(r-h);
 return q;
}
inline std::array<I,3> shape(int id){
 if(id!=0&&id!=1)throw std::runtime_error("only original shapes0/1");
 I hx(id==0?5e-9:2.5e-9),hz(3e-9);std::array<I,3>h={I(1),I(1),hz/hx};
 I lower=I(59)/I(100),upper=I(121)/I(100);
 if(mpfr_less_p(h[2].lo,lower.hi)||mpfr_greater_p(h[2].hi,upper.lo))throw std::runtime_error("geometry proof domain");
 return h;
}
inline I legendre_derivative32(const I&x){
 I prev(1),current=x;
 for(int n=2;n<=32;n++){I next=(I(2*n-1)*x*current-I(n-1)*prev)/I(n);prev=current;current=next;}
 return I(32)*(x*current-prev)/(x*x-I(1));
}
struct Node {I x,w;};
inline std::vector<Node> load_nodes(const std::string&path){
 // Reuse exact Q0 roots and certified outward positive weights; no root/weight qualification rerun.
 std::ifstream f(path);int count;f>>count;if(!f||count!=32)throw std::runtime_error("certified32 roots");
 auto weight_path=std::filesystem::path(path).parent_path()/"certified_weights.tsv";
 std::ifstream wf(weight_path);std::string line;std::getline(wf,line);if(line!="index\tx_lo\tx_hi\tw_lo\tw_hi")throw std::runtime_error("certified weights header");
 std::vector<Node>result;I previous(-2);
 for(int k=0;k<32;k++){
  std::string l,u,xl,xu,wl,wu;long lq,uq;int index;
  f>>l>>lq>>u>>uq;wf>>index>>xl>>xu>>wl>>wu;
  if(!f||!wf||index!=k)throw std::runtime_error("certified root/weight layout");
  I x=I::dyadic(l,lq,u,uq),outer=I::from_decimal(xl,xu),w=I::from_decimal(wl,wu);
  if(mpfr_lessequal_p(x.lo,previous.hi)||mpfr_cmp_si(x.lo,-1)<=0||mpfr_cmp_si(x.hi,1)>=0||mpfr_greater_p(outer.lo,x.lo)||mpfr_less_p(outer.hi,x.hi)||mpfr_sgn(w.lo)<=0)throw std::runtime_error("certified root/weight enclosure");
  result.push_back({x,w});previous=x;
 }
 std::string extra;if(f>>extra)throw std::runtime_error("root trailing data");return result;
}
