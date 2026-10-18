// GPL-3.0-only. Bind the existing FiM local-field and FFT operators, without CLI budgets.
#define SCRIPT_API_TRACE 1
#define FIM_USER_LIBRARY 1
#include "../user_native.cpp"
#include "../current_sot.hpp"
#include <memory>
#include <cstring>

struct ScriptModel {
 UserConfig u;
 std::unique_ptr<FFT> fft;
 std::array<std::vector<std::array<double,2>>,6> K;
 LocalFieldTeam team;
 unsigned long calls=0,fft_calls=0;std::array<unsigned long,4> local_calls{};
 ScriptModel(UserConfig value,const char*kernel):u(std::move(value)){
  if(!kernel||!*kernel)return;
  fft=std::make_unique<FFT>(u.px,u.py);
  std::ifstream f(kernel,std::ios::binary);std::vector<std::array<double,6>> raw(fft->n);
  f.read(reinterpret_cast<char*>(raw.data()),raw.size()*sizeof(raw[0]));
  if(!f||f.peek()!=EOF)throw std::runtime_error("kernel shape");
  for(int a=0;a<6;a++){std::vector<double>x(fft->n);for(int j=0;j<fft->n;j++){x[j]=-raw[j][a];if(!std::isfinite(x[j]))throw std::runtime_error("nonfinite kernel");}K[a]=fft->fwd(x);}
 }
 Evaluation eval(const Spins&m){
  C cc=u.c;cc.m=m;auto f=team.evaluate_owned(cc);calls++;for(int i=0;i<4;i++)local_calls[i]+=f.script_calls[i];
  Evaluation e;e.H=std::move(f.H);e.Eparts={f.E[0]-f.Ecross,f.Ecross,f.E[1],f.E[2],f.E[3],0,0};
  if(fft){
   auto&c=u.c;std::vector<V>M(c.count);for(size_t j=0;j<c.count;j++)M[j]=(m[0][j]*c.Ms[0]+m[1][j]*c.Ms[1])*.5;
   std::array<std::vector<std::array<double,2>>,3>s;
   for(int a=0;a<3;a++){std::vector<double>x(fft->n);for(int y=0;y<c.n[1];y++)for(int k=0;k<c.n[0];k++)x[k+y*u.px]=M[k+y*c.n[0]][a];s[a]=fft->fwd(x);fft_calls++;}
   e.Hd.resize(c.count);int lut[3][3]={{0,3,4},{3,1,5},{4,5,2}};
   for(int a=0;a<3;a++){std::vector<std::array<double,2>>x(fft->nf);for(int j=0;j<fft->nf;j++)for(int b=0;b<3;b++){auto k=K[lut[a][b]][j],q=s[b][j];x[j][0]+=k[0]*q[0]-k[1]*q[1];x[j][1]+=k[0]*q[1]+k[1]*q[0];}auto real=fft->inv(x);fft_calls++;for(int y=0;y<c.n[1];y++)for(int k=0;k<c.n[0];k++)e.Hd[k+y*c.n[0]][a]=real[k+y*u.px];}
   for(int i=0;i<2;i++)for(size_t j=0;j<c.count;j++)e.H[i][j]+=e.Hd[j];
   for(size_t j=0;j<c.count;j++)e.Eparts[5]-=.5*mu0*c.volume*dot(M[j],e.Hd[j]);
  }
  if(u.external.x!=0||u.external.y!=0||u.external.z!=0){
   for(int i=0;i<2;i++)for(size_t j=0;j<u.c.count;j++)e.H[i][j]+=u.external;
   for(size_t j=0;j<u.c.count;j++){V M=(m[0][j]*u.c.Ms[0]+m[1][j]*u.c.Ms[1])*.5;e.Eparts[6]-=mu0*u.c.volume*dot(M,u.external);}
  }
  for(double part:e.Eparts)e.E+=part;
  if(!std::isfinite(e.E))throw std::runtime_error("nonfinite energy");
  return e;
 }
};
static thread_local std::string script_error;
extern "C" {
const char* mm_error(){return script_error.c_str();}
void* mm_create(const char*config,const char*kernel){try{return new ScriptModel(read_user(config),kernel);}catch(const std::exception&e){script_error=e.what();return nullptr;}}
void mm_destroy(void*p){delete static_cast<ScriptModel*>(p);}
int mm_eval(void*p,const double*m,double*H,double*parts){try{
 auto*model=static_cast<ScriptModel*>(p);Spins s;size_t count=model->u.c.count;
 for(int i=0;i<2;i++){s[i].resize(count);std::memcpy(s[i].data(),m+i*count*3,count*sizeof(V));}
 auto e=model->eval(s);for(int i=0;i<2;i++)std::memcpy(H+i*count*3,e.H[i].data(),count*sizeof(V));for(int k=0;k<7;k++)parts[k]=e.Eparts[k];return 0;
 }catch(const std::exception&e){script_error=e.what();return 1;}}
int mm_rhs(void*p,const double*m,const double*H,const double*spec,double*out,double*power_out){try{
 auto*model=static_cast<ScriptModel*>(p);auto&u=model->u;CurrentSOT drive;drive.J={spec[0],spec[1],spec[2]};drive.d={spec[3],spec[4],spec[5]};drive.xi={spec[6],spec[7]};drive.r={spec[8],spec[9]};Spins s;Evaluation e;size_t count=u.c.count;
 for(int i=0;i<2;i++){s[i].resize(count);e.H[i].resize(count);std::memcpy(s[i].data(),m+i*count*3,count*sizeof(V));std::memcpy(e.H[i].data(),H+i*count*3,count*sizeof(V));}
 bool active=(drive.xi[0]!=0||drive.xi[1]!=0)&&dot(sot_cross(drive.d,drive.J),sot_cross(drive.d,drive.J))!=0;
 auto k=active?current_rhs(s,e,u,drive):user_rhs(s,e,u);auto D=power(s,e,u);std::array<double,2>P{};if(active)P=current_work(s,e,u,drive);
 for(int i=0;i<2;i++){std::memcpy(out+i*count*3,k[i].data(),count*sizeof(V));power_out[i]=D[i];power_out[2+i]=P[i];}return 0;
 }catch(const std::exception&e){script_error=e.what();return 1;}}
unsigned long mm_calls(void*p){return static_cast<ScriptModel*>(p)->calls;}
unsigned long mm_fft_calls(void*p){return static_cast<ScriptModel*>(p)->fft_calls;}
int mm_subfields(void*){return 2;}
unsigned long mm_local_calls(void*p,int term){return static_cast<ScriptModel*>(p)->local_calls.at(term);}
int mm_sd(const double*m,const double*H,const double*prev,const double*gp,unsigned long count,double*controls,const double*Ms,double*out,double*gn){try{
 Spins s,h,p,g;for(int i=0;i<2;i++){s[i].resize(count);h[i].resize(count);p[i].resize(count);g[i].resize(count);std::memcpy(s[i].data(),m+i*count*3,count*sizeof(V));std::memcpy(h[i].data(),H+i*count*3,count*sizeof(V));std::memcpy(p[i].data(),prev+i*count*3,count*sizeof(V));std::memcpy(g[i].data(),gp+i*count*3,count*sizeof(V));}
 auto nextg=gradient_sd(s,h);BB b;if(controls[0])b=bb_sd(s,nextg,p,g);int resets=static_cast<int>(controls[1]);double dt=controls[0]?choose_sd(b,static_cast<int>(controls[0]),resets):MIN_SD;
 for(int i=0;i<2;i++){for(size_t j=0;j<count;j++)s[i][j]=rational_sd(s[i][j],h[i][j],dt,Ms[i]);std::memcpy(out+i*count*3,s[i].data(),count*sizeof(V));std::memcpy(gn+i*count*3,nextg[i].data(),count*sizeof(V));}
 controls[0]++;controls[1]=resets;controls[3]+=dt;controls[4]=dt;return 0;
 }catch(const std::exception&e){script_error=e.what();return 1;}}

}
