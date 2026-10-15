// Fixed-eight Gaussian surface-integral reference; historical numerical qualification is documented separately.
// Independent Gaussian surface formula. No Newell/production source includes.
#include "gaussian.hpp"
#include <chrono>
#include <filesystem>
#include <iostream>
#include <sys/resource.h>
struct Result {std::array<I,6> tensor,face_absolute,tail_error;I geometry_M,quad_error;};
Result formal_point(int s,int rx,int ry,const std::vector<Node>&nodes){
 if((rx!=0&&rx!=1)||(ry!=0&&ry!=1))throw std::runtime_error("fixed8 points only");
 auto h=shape(s);I pi=pii(),rootpi=sqrti(pi),C=I(1)/(I(2)*pi*rootpi*h[0]*h[1]*h[2]);
 std::array<bool,3>r={bool(rx),bool(ry),false};int aa[6]={0,1,2,0,0,1},bb[6]={0,1,2,1,2,2};Result z;
 I volume=h[0]*h[1]*h[2],complex_gaussian_bound=expi(I(9)/I(256)*(I(8)+h[2]*h[2]));
 for(int k=0;k<6;k++){I bound=C*I(4)*(volume/h[aa[k]])*(volume/h[bb[k]])*complex_gaussian_bound;
  if(mpfr_greater_p(bound.hi,z.geometry_M.hi))mpfr_set(z.geometry_M.hi,bound.hi,MPFR_RNDU);}
 if(mpfr_cmp_ui(z.geometry_M.hi,3)>0)throw std::runtime_error("geometry M proof failed");
 z.quad_error=I(8)*I(3)*I(16)/I(0x1p64);
 auto start=std::chrono::steady_clock::now();
 for(int panel=0;panel<32;panel++)for(const auto&node:nodes){
  I t=I(2*panel+1)/I(4)+node.x/I(4),weight=node.w/I(4);
  std::array<ABD,3>q={abd(t,h[0],r[0]),abd(t,h[1],r[1]),abd(t,h[2],r[2])};
  for(int k=0;k<6;k++){
   int i=aa[k],j=bb[k];I value,absolute;
   if(i==j){int u=(i+1)%3,v=(i+2)%3;value=q[i].D*q[u].A*q[v].A;absolute=q[i].faceD*q[u].A*q[v].A;}
   else{int u=3-i-j;value=-q[i].B*q[j].B*q[u].A;absolute=q[i].faceB*q[j].faceB*q[u].A;}
   z.tensor[k]=z.tensor[k]+C*weight*value;z.face_absolute[k]=z.face_absolute[k]+C*weight*absolute;
  }
  rusage usage{};getrusage(RUSAGE_SELF,&usage);if(std::chrono::duration<double>(std::chrono::steady_clock::now()-start).count()>25||usage.ru_maxrss>2147483648L)throw std::runtime_error("point soft25 RSS2GiB");
 }
 I T(16);std::array<I,3>a,b,beta,beta_abs,d,da;
 for(int i=0;i<3;i++){
  a[i]=r[i]?I(0):rootpi*h[i];b[i]=r[i]?I(1)/I(2):I(-1);
  beta[i]=r[i]?-rootpi/I(2):I(0);beta_abs[i]=r[i]?rootpi/I(2):rootpi;
  d[i]=r[i]?I(-1):I(2);da[i]=r[i]?I(1):I(2);
 }
 // Exact integrated algebraic tails. Do not discard these at T=16.
 for(int k=0;k<6;k++){
  int i=aa[k],j=bb[k];I tail,absolute_tail;
  if(i==j){int u=(i+1)%3,v=(i+2)%3;I polynomial=a[u]*a[v]/T+(a[u]*b[v]+b[u]*a[v])/(I(2)*T*T)+b[u]*b[v]/(I(3)*T*T*T);tail=C*d[i]*polynomial;absolute_tail=C*da[i]*polynomial;}
  else{int u=3-i-j;I polynomial=a[u]/(I(2)*T*T)+b[u]/(I(3)*T*T*T);tail=-C*beta[i]*beta[j]*polynomial;absolute_tail=C*beta_abs[i]*beta_abs[j]*polynomial;}
  // Explicit per-component erfc remainder. Uniform a=.59 is certified by shape().
  // A<=4/t,A*<=3/t; |deltaA|<=2e/t²; B_abs<=3/t, B_abs*<=2/t,
  // |deltaB|<=2e/t²; |deltaD|<=3e and |D*|<=2.
  // Diag telescoping <=e(48/t²+28/t³); offdiag <=48e/t⁴.
  // These also bound the absolute face integrand; no trace completion.
  I amin=I(59)/I(100),decay=expi(-(amin*amin*T*T));
  z.tail_error[k]=i==j?C*decay/(I(2)*amin*amin*T)*(I(48)/(T*T)+I(28)/(T*T*T))
                          :C*decay*I(48)/(I(2)*amin*amin*T*T*T*T*T);
  if(mpfr_cmp_d(z.tail_error[k].hi,1e-24)>0)throw std::runtime_error("tail proof budget exceeded");
  I analytic=z.quad_error+z.tail_error[k];
  I uncertainty;mpfr_neg(uncertainty.lo,analytic.hi,MPFR_RNDD);mpfr_set(uncertainty.hi,analytic.hi,MPFR_RNDU);
  z.tensor[k]=z.tensor[k]+tail+uncertainty;z.face_absolute[k]=z.face_absolute[k]+absolute_tail+uncertainty;
  if(i!=j&&(!r[i]||!r[j]))z.tensor[k]=I(0); // Independent exact reflection, no trace repair.
  I width=z.tensor[k]-I::dyadic("0",0,"0",0);mpfr_sub(width.hi,z.tensor[k].hi,z.tensor[k].lo,MPFR_RNDU);
  if(mpfr_cmp_d(width.hi,2e-12)>0)throw std::runtime_error("reference total radius exceeds1e-12");
 }
 return z;
}
int main(int argc,char**argv){try{
 if(argc!=7||std::string(argv[1])!="formal-point")throw std::runtime_error("formal-point ROOTS SHAPE RX RY NEW_OUTPUT; fixed-eight reference only");
 std::filesystem::path out=argv[6];if(std::filesystem::exists(out))throw std::runtime_error("no overwrite");
 int s=std::stoi(argv[3]),x=std::stoi(argv[4]),y=std::stoi(argv[5]);auto nodes=load_nodes(argv[2]);auto value=formal_point(s,x,y,nodes);
 std::ofstream f(out);f<<"component\tN_lo\tN_hi\tabs_face_integral_lo\tabs_face_integral_hi\n";const char*names[]={"xx","yy","zz","xy","xz","yz"};
 for(int k=0;k<6;k++)f<<names[k]<<'\t'<<value.tensor[k]<<'\t'<<value.face_absolute[k]<<"\ttail_error\t"<<value.tail_error[k]<<'\n';
 f<<"#geometry_M_bound\t"<<value.geometry_M<<"\n#finite_Gauss_error\t"<<value.quad_error<<'\n';
 f.close();if(!f)throw std::runtime_error("output");return 0;
 }catch(const std::exception&e){std::cerr<<e.what()<<'\n';return 2;}}
