// I1 isolated integration of accepted P-Anh and periodic FFT field.
#define main accepted_local_cli_unused
#include "../../src/grid_fields.cpp"
#undef main
#include "../../src/periodic_fft.hpp"
#include <limits>
using Spins=std::array<std::vector<V>,2>;
struct Dip {
 FFT fft{125,125};std::array<std::vector<std::array<double,2>>,6> K;double bound=0;unsigned long calls=0;
 explicit Dip(const std::filesystem::path&p){
  std::ifstream f(p,std::ios::binary);std::vector<std::array<double,6>>t(15625);f.read(reinterpret_cast<char*>(t.data()),t.size()*sizeof(t[0]));if(!f||f.peek()!=EOF)throw std::runtime_error("invalid qualified kernel");
  for(auto q:t)bound+=std::sqrt(q[0]*q[0]+q[1]*q[1]+q[2]*q[2]+2*(q[3]*q[3]+q[4]*q[4]+q[5]*q[5]));
  for(int a=0;a<6;a++){std::vector<double>v(15625);for(int j=0;j<15625;j++)v[j]=-t[j][a];K[a]=fft.fwd(v);}
 }
 std::vector<V>field(const std::vector<V>&M){
  calls++;std::array<std::vector<std::array<double,2>>,3>s;for(int a=0;a<3;a++){std::vector<double>v(15625);for(int j=0;j<15625;j++)v[j]=M[j][a];s[a]=fft.fwd(v);}
  std::vector<V>H(15625);int lookup[3][3]={{0,3,4},{3,1,5},{4,5,2}};
  for(int a=0;a<3;a++){std::vector<std::array<double,2>>v(fft.nf);for(int j=0;j<fft.nf;j++)for(int b=0;b<3;b++){auto k=K[lookup[a][b]][j],m=s[b][j];v[j][0]+=k[0]*m[0]-k[1]*m[1];v[j][1]+=k[0]*m[1]+k[1]*m[0];}auto real=fft.inv(v);for(int j=0;j<15625;j++)H[j][a]=real[j];}return H;
 }
};
V project(V m,V h){return h-m*dot(m,h);}
struct Evaluation {Spins H,p;std::array<double,7>Eparts{};double E=0,residual=0;std::vector<V>Hd;};
struct Model {
 C c;Dip dip;V external;double scale,omega,gradientScale=0;std::array<int,2> canonical_identity;
 Model(C cc,const std::filesystem::path&kernel,V ext):c(std::move(cc)),dip(kernel),external(ext){
  if(c.n!=std::array<int,3>{125,125,1}||c.h!=std::array<double,3>{4e-9,4e-9,3e-9}||c.pbc!=std::array<int,3>{1,1,0})throw std::runtime_error("I1 fixed geometry only");
  canonical_identity=c.Ms==std::array<double,2>{3e5,6e5}?std::array<int,2>{0,1}:std::array<int,2>{1,0};
  if((c.Ms!=std::array<double,2>{3e5,6e5}&&c.Ms!=std::array<double,2>{6e5,3e5})||c.A!=std::array<double,2>{5e-12,5e-12}||c.Ah!=-8e6||c.Anh!=-5e-12||c.D!=std::array<double,2>{.00105,.00105}||c.K1!=std::array<double,2>{109000,109000}||c.K2!=std::array<double,2>{0,0}||c.active!=std::array<int,4>{1,1,1,1}||c.axis.x!=0||c.axis.y!=0||c.axis.z!=1)throw std::runtime_error("I1 fixed user material only");
  if(!finite(external))throw std::runtime_error("nonfinite external H");
  scale=mu0*c.volume*c.count*6e5*6e5/2;omega=0;
  for(int i=0;i<2;i++){double Hbound=(16*c.A[i]+8*std::abs(c.Anh))/(mu0*c.Ms[i]*c.h[0]*c.h[0])+4*std::abs(c.Ah)/(mu0*c.Ms[i])+4*std::sqrt(2.)*std::abs(c.D[i])/(mu0*c.Ms[i]*c.h[0])+2*c.K1[i]/(mu0*c.Ms[i])+norm(external)+.5*(c.Ms[0]+c.Ms[1])*dip.bound;omega=std::max(omega,2.212761569e5*Hbound);gradientScale+=c.count*mu0*c.Ms[i]*c.volume/2.212761569e5*std::pow(2.212761569e5*6e5/2,2);}
 }
 Evaluation eval(const Spins&m){
  C cc=c;cc.m=m;auto f=evaluate(cc);Evaluation v;v.H=std::move(f.H);v.Eparts={f.E[0]-f.Ecross,f.Ecross,f.E[1],f.E[2],f.E[3],0,0};std::vector<V>M(c.count);
  for(std::size_t k=0;k<c.count;k++)M[k]=(m[0][k]*c.Ms[0]+m[1][k]*c.Ms[1])*.5;v.Hd=dip.field(M);
  for(int i=0;i<2;i++){v.p[i].resize(c.count);for(std::size_t k=0;k<c.count;k++){v.H[i][k]+=v.Hd[k]+external;auto ph=project(m[i][k],v.H[i][k]);v.p[i][k]=ph*(2.212761569e5/2);v.residual=std::max(v.residual,norm(ph)/6e5);}}
  for(std::size_t k=0;k<c.count;k++){v.Eparts[5]-=.5*mu0*c.volume*dot(M[k],v.Hd[k]);v.Eparts[6]-=mu0*c.volume*dot(M[k],external);}for(auto e:v.Eparts)v.E+=e;
  if(!std::isfinite(v.E)||!std::isfinite(v.residual))throw std::runtime_error("nonfinite combined evaluation");return v;
 }
 double inner(const Spins&a,const Spins&b){long double sum=0;for(int i=0;i<2;i++){double w=mu0*c.Ms[i]*c.volume/2.212761569e5;for(std::size_t k=0;k<c.count;k++)sum+=static_cast<long double>(w)*dot(a[i][k],b[i][k]);}return static_cast<double>(sum);}
};
Spins transport(const Spins&m,const Spins&d){Spins r=d;for(int i=0;i<2;i++)for(std::size_t k=0;k<m[i].size();k++)r[i][k]=project(m[i][k],d[i][k]);return r;}
Spins add(const Spins&a,const Spins&b,double f){Spins r=a;for(int i=0;i<2;i++)for(std::size_t k=0;k<a[i].size();k++)r[i][k]+=b[i][k]*f;return r;}
Spins exponential(const Spins&m,const Spins&d,double tau,double&raw){Spins r=m;raw=0;for(int i=0;i<2;i++)for(std::size_t k=0;k<m[i].size();k++){auto t=project(m[i][k],d[i][k]);double q=norm(t);V v=q==0?m[i][k]:m[i][k]*std::cos(tau*q)+t*(std::sin(tau*q)/q);double n=norm(v);raw=std::max(raw,std::abs(n-1));if(!finite(v)||n==0||raw>1e-8)throw std::runtime_error("raw drift");r[i][k]=v*(1/n);}return r;}
void blob(const std::filesystem::path&p,const std::vector<V>&v){std::ofstream f(p,std::ios::binary);for(auto q:v){double x[3]={q.x,q.y,q.z};f.write(reinterpret_cast<char*>(x),sizeof(x));}if(!f)throw std::runtime_error("write field failure");}
void snapshot(const std::filesystem::path&p,const Spins&m){std::ofstream f(p,std::ios::binary);for(int i=0;i<2;i++)for(auto q:m[i]){double v[3]={q.x,q.y,q.z};f.write(reinterpret_cast<char*>(v),sizeof(v));}if(!f)throw std::runtime_error("write spins failure");}
void save_eval(const std::filesystem::path&out,const std::string&tag,const Evaluation&v){blob(out/(tag+"_H_A.bin"),v.H[0]);blob(out/(tag+"_H_B.bin"),v.H[1]);blob(out/(tag+"_Hd.bin"),v.Hd);std::ofstream f(out/(tag+"_energy.json"));f<<std::setprecision(17)<<"{\"total_J\":"<<v.E<<",\"parts_J\":[";for(int i=0;i<7;i++){if(i)f<<',';f<<v.Eparts[i];}f<<"],\"residual_scaled\":"<<v.residual<<"}\n";}
