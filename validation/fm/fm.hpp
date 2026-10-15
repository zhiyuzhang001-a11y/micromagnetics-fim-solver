#pragma once
#include <array>
#include <algorithm>
#include <chrono>
#include <cmath>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <map>
#include <memory>
#include <sstream>
#include <stdexcept>
#include <string>
#include <sys/resource.h>
#include <vector>
struct V{
 double x=0,y=0,z=0; double&operator[](int a){return a==0?x:a==1?y:z;} double operator[](int a)const{return a==0?x:a==1?y:z;}
 V operator+(V b)const{return{x+b.x,y+b.y,z+b.z};} V operator-(V b)const{return{x-b.x,y-b.y,z-b.z};}
 V operator*(double c)const{return{x*c,y*c,z*c};} V&operator+=(V b){x+=b.x;y+=b.y;z+=b.z;return *this;}
};
double dot(V a,V b){return a.x*b.x+a.y*b.y+a.z*b.z;}
bool finite(V v){return std::isfinite(v.x)&&std::isfinite(v.y)&&std::isfinite(v.z);}
double norm(V v){return std::hypot(v.x,v.y,v.z);}
const double mu0=4*std::acos(-1.)*1e-7;
const double Gamma=2.212761569e5;
#include "shared/gilbert.hpp"
#include "shared/physical_terms.hpp"
#include "shared/rk4.hpp"
#include "demag.hpp"
using State=std::array<std::vector<V>,1>;
using Clock=std::chrono::steady_clock;
unsigned long rss(){rusage r{};if(getrusage(RUSAGE_SELF,&r))throw std::runtime_error("RSS query failure");
#ifdef __APPLE__
 return r.ru_maxrss;
#else
 return r.ru_maxrss*1024UL;
#endif
}
struct Config{
 int nx=0,ny=0,steps=0,stride=0;std::array<double,3>h{};double Ms=0,A=0,K=0,alpha=0,grel=0,dt=0,wall=0;
 double gamma_G=Gamma;unsigned long memory=0;std::array<int,4>active{};V axis,H;State m;std::string mode,kernel_path,kernel_sha256,initial_sha256,protocol_sha256;std::vector<int> fixed;
 size_t count()const{return static_cast<size_t>(nx)*ny;}double volume()const{return h[0]*h[1]*h[2];}
 std::string signature()const{std::ostringstream s;s<<std::setprecision(17)<<nx<<' '<<ny<<' ';for(auto q:h)s<<q<<' ';s<<Ms<<' '<<A<<' '<<K<<' '<<alpha<<' '<<grel<<' '<<dt<<' '<<axis.x<<' '<<axis.y<<' '<<axis.z<<' '<<H.x<<' '<<H.y<<' '<<H.z;for(auto q:active)s<<' '<<q;s<<" gamma_G:"<<gamma_G;s<<" kernel:"<<kernel_sha256<<" initial:"<<initial_sha256<<" protocol:"<<protocol_sha256;s<<" fixed:";for(auto q:fixed)s<<q;return s.str();}
};
double scalar(const std::string&s){size_t used=0;double q=std::stod(s,&used);if(used!=s.size()||!std::isfinite(q))throw std::runtime_error("nonfinite or malformed number");return q;}
Config read_config(const std::filesystem::path&p){
 if(std::filesystem::file_size(p)>64UL*1024*1024)throw std::runtime_error("input too large");std::ifstream f(p);std::string line;std::map<std::string,std::vector<std::string>>kv;State m;bool state=false;
 while(std::getline(f,line)){if(line.empty())continue;std::istringstream l(line);std::string key;l>>key;if(key=="state"){if(state)throw std::runtime_error("duplicate state");state=true;continue;}
  if(state){V q;std::string a,b,c,extra;if(!(l>>b>>c)||l>>extra)throw std::runtime_error("bad state row");a=key;q={scalar(a),scalar(b),scalar(c)};if(std::abs(norm(q)-1)>1e-12)throw std::runtime_error("nonunit input");m[0].push_back(q);}
  else{if(kv.count(key))throw std::runtime_error("duplicate key");std::vector<std::string>v;std::string t;while(l>>t)v.push_back(t);kv[key]=v;}}
 const std::map<std::string,size_t> expected={{"schema",1},{"units",1},{"mode",1},{"n",2},{"h",3},{"Ms",1},{"A",1},{"K1",1},{"axis",3},{"H",3},{"alpha",1},{"grel",1},{"active",4},{"dt",1},{"steps",1},{"stride",1},{"wall",1},{"memory",1}};
 if(kv.size()!=expected.size()+(kv.count("fixed")?1:0)+(kv.count("gamma_G")?1:0)+(kv.count("gamma_convention")?1:0)+(kv.count("kernel_path")?1:0)+(kv.count("kernel_sha256")?1:0)+(kv.count("initial_sha256")?1:0)+(kv.count("protocol_sha256")?1:0)||!state)throw std::runtime_error("missing/unknown key");for(auto [key,n]:expected)if(kv[key].size()!=n)throw std::runtime_error("missing/invalid field");
 if(kv["schema"][0]!="FM-SI-v1"||kv["units"][0]!="m_Apm_Jpm_Jpm3_s")throw std::runtime_error("schema/units mismatch");
 Config c;auto val=[&](std::string k,int i=0){return scalar(kv[k][i]);};auto integer=[&](std::string k,int i=0){double q=val(k,i);if(q!=std::floor(q)||q<0||q>10000000)throw std::runtime_error("invalid integer");return static_cast<int>(q);};
 c.mode=kv["mode"][0];if(c.mode!="field"&&c.mode!="trajectory")throw std::runtime_error("unknown mode");c.nx=integer("n");c.ny=integer("n",1);for(int i=0;i<3;i++)c.h[i]=val("h",i);c.Ms=val("Ms");c.A=val("A");c.K=val("K1");c.alpha=val("alpha");c.grel=val("grel");c.dt=val("dt");c.steps=integer("steps");c.stride=integer("stride");c.wall=val("wall");double mem=val("memory");if(mem!=std::floor(mem)||mem<=0||mem>2147483648.)throw std::runtime_error("memory bound");c.memory=static_cast<unsigned long>(mem);
 c.axis={val("axis"),val("axis",1),val("axis",2)};c.H={val("H"),val("H",1),val("H",2)};for(int i=0;i<4;i++){c.active[i]=integer("active",i);if(c.active[i]>1)throw std::runtime_error("module switch");}
 if(c.nx<1||c.ny<1||c.nx>4096||c.ny>4096||c.count()>65536||c.Ms<=0||c.A<0||c.alpha<0||c.grel<=0||c.dt<=0||c.steps<1||c.stride<1||c.wall<=0||c.wall>30||std::abs(norm(c.axis)-1)>1e-12)throw std::runtime_error("invalid FM parameters");for(double h:c.h)if(h<=0)throw std::runtime_error("invalid spacing");if(!std::isfinite(c.volume())||c.volume()<=0)throw std::runtime_error("invalid volume");if(m[0].size()!=c.count())throw std::runtime_error("wrong-size state");if(kv.count("gamma_G")!=kv.count("gamma_convention"))throw std::runtime_error("gamma convention/value pair required");if(kv.count("gamma_G")){if(kv["gamma_G"].size()!=1||kv["gamma_convention"].size()!=1||kv["gamma_convention"][0]!="Gilbert")throw std::runtime_error("explicit Gilbert gamma required");c.gamma_G=scalar(kv["gamma_G"][0]);if(c.gamma_G<=0)throw std::runtime_error("positive gamma required");}for(auto pair:{std::pair<const char*,std::string*>{"kernel_path",&c.kernel_path},{"kernel_sha256",&c.kernel_sha256},{"initial_sha256",&c.initial_sha256},{"protocol_sha256",&c.protocol_sha256}}){if(kv.count(pair.first)){if(kv[pair.first].size()!=1)throw std::runtime_error("kernel/provenance field");*pair.second=kv[pair.first][0];}}if(c.kernel_path.empty()!=c.kernel_sha256.empty())throw std::runtime_error("kernel path/hash pair");c.m=std::move(m);c.fixed.assign(c.count(),0);if(kv.count("fixed")){if(kv["fixed"].size()!=c.count())throw std::runtime_error("fixed mask size");for(size_t j=0;j<c.count();j++){double q=scalar(kv["fixed"][j]);if(q!=0&&q!=1)throw std::runtime_error("fixed mask flag");c.fixed[j]=static_cast<int>(q);}}return c;
}
struct Evaluation{State H;std::vector<V> Hd;std::array<double,4>parts{};double E=0;};
inline std::string spin_sha256(const std::vector<V>&m){std::vector<double>data;for(auto q:m){data.push_back(q.x);data.push_back(q.y);data.push_back(q.z);}unsigned char digest[CC_SHA256_DIGEST_LENGTH];CC_SHA256(data.data(),static_cast<CC_LONG>(data.size()*sizeof(double)),digest);std::ostringstream o;o<<std::hex<<std::setfill('0');for(auto x:digest)o<<std::setw(2)<<int(x);return o.str();}
struct Model{
 Config c;std::unique_ptr<Demag>dip;unsigned long calls=0;
 explicit Model(Config x):c(std::move(x)){if(!c.initial_sha256.empty()&&spin_sha256(c.m[0])!=c.initial_sha256)throw std::runtime_error("initial state sha mismatch");if(c.active[3])dip=std::make_unique<Demag>(c.nx,c.ny,c.h,c.kernel_path,c.kernel_sha256);}
 Evaluation eval(const State&m){
  if(m[0].size()!=c.count())throw std::runtime_error("wrong-size stage");for(V q:m[0])if(!finite(q)||norm(q)==0)throw std::runtime_error("unsafe stage");calls++;Evaluation e;e.H[0].resize(c.count());double vol=c.volume();std::array<double,4>energy_sum{},energy_comp{};auto accumulate_energy=[&](int a,double value){double next=energy_sum[a]+value;if(std::abs(energy_sum[a])>=std::abs(value))energy_comp[a]+=(energy_sum[a]-next)+value;else energy_comp[a]+=(value-next)+energy_sum[a];energy_sum[a]=next;};
  for(size_t j=0;j<c.count();j++){
   int x=j%c.nx,y=j/c.nx;if(c.active[0])for(int d=0;d<2;d++){if((d==0?x+1<c.nx:y+1<c.ny)){size_t k=j+(d==0?1:c.nx);auto a=exchange_bond(m[0][k]-m[0][j],vol,c.A,c.h[d],c.Ms,1);accumulate_energy(0,a.energy);e.H[0][j]+=a.field;e.H[0][k]+=a.field*(-1);}}
   if(c.active[1]){auto a=uniaxial(m[0][j],c.axis,vol,c.K,0,c.Ms,1);accumulate_energy(1,a.energy);e.H[0][j]+=a.field;}
   if(c.active[2]){auto a=zeeman(m[0][j],c.H,vol,c.Ms,1);accumulate_energy(2,a.energy);e.H[0][j]+=a.field;}
  }
  if(dip){std::vector<V>M=m[0];for(auto&q:M)q=q*c.Ms;auto Hd=dip->field(M);e.Hd=Hd;for(size_t j=0;j<c.count();j++){e.H[0][j]+=Hd[j];accumulate_energy(3,-.5*mu0*vol*dot(M[j],Hd[j]));}}
  for(int a=0;a<4;a++)e.parts[a]=energy_sum[a]+energy_comp[a];double total=0,comp=0;for(double a:e.parts){double next=total+a;if(std::abs(total)>=std::abs(a))comp+=(total-next)+a;else comp+=(a-next)+total;total=next;}e.E=total+comp;if(!std::isfinite(e.E))throw std::runtime_error("nonfinite energy");for(auto q:e.H[0])if(!finite(q))throw std::runtime_error("nonfinite field");return e;
 }
 State rhs(const State&m,const Evaluation&e){State k=m;for(size_t j=0;j<c.count();j++){k[0][j]=gilbert_gamma(m[0][j],e.H[0][j],c.grel,c.alpha,c.gamma_G);if(!finite(k[0][j]))throw std::runtime_error("nonfinite RHS");}return k;}
 std::array<double,1>loss(const State&m,const Evaluation&e){long double sum=0;for(size_t j=0;j<c.count();j++){V a=m[0][j],b=e.H[0][j];V cross={a.y*b.z-a.z*b.y,a.z*b.x-a.x*b.z,a.x*b.y-a.y*b.x};sum+=dot(cross,cross);}double q=double(sum)*mu0*c.volume()*c.Ms*c.gamma_G*c.grel*c.alpha/(1+c.alpha*c.alpha);if(!std::isfinite(q))throw std::runtime_error("nonfinite loss");return {q};}
};
void write_state(const std::filesystem::path&p,const Config&c,const State&m,int step,double loss){std::ofstream f(p);f<<"FM-STATE-v1\n"<<c.signature()<<'\n'<<std::setprecision(17)<<step<<' '<<loss<<'\n';for(V q:m[0])f<<q.x<<' '<<q.y<<' '<<q.z<<'\n';f.flush();if(!f)throw std::runtime_error("state write failure");}
State read_state(const std::filesystem::path&p,const Config&c,int&step,double&loss){std::ifstream f(p);std::string header,signature;std::getline(f,header);std::getline(f,signature);if(header!="FM-STATE-v1"||signature!=c.signature())throw std::runtime_error("resume schema/physics mismatch");if(!(f>>step>>loss)||step<0||step>c.steps||!std::isfinite(loss)||loss<0)throw std::runtime_error("bad resume history");State m;for(size_t j=0;j<c.count();j++){V q;if(!(f>>q.x>>q.y>>q.z)||!finite(q)||std::abs(norm(q)-1)>1e-12)throw std::runtime_error("bad resume state");m[0].push_back(q);}std::string extra;if(f>>extra)throw std::runtime_error("wrong-size resume");return m;}
