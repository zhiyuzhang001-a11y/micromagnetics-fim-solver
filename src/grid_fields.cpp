// P-Anh isolated extension of B1 static field/energy kernel. No integrator, demag, drive or other 2C+ work.
#include <array>
#include <algorithm>
#include <chrono>
#include <cmath>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <stdexcept>
#include <string>
#include <sys/resource.h>
#include <vector>

struct V {
    double x=0,y=0,z=0;
    double& operator[](int a){return a==0?x:(a==1?y:z);}
    double operator[](int a)const{return a==0?x:(a==1?y:z);}
    V operator+(V b)const{return {x+b.x,y+b.y,z+b.z};}
    V operator-(V b)const{return {x-b.x,y-b.y,z-b.z};}
    V operator*(double c)const{return {x*c,y*c,z*c};}
    V& operator+=(V b){x+=b.x;y+=b.y;z+=b.z;return *this;}
};
double dot(V a,V b){return a.x*b.x+a.y*b.y+a.z*b.z;}
double norm(V a){return std::sqrt(dot(a,a));}
bool finite(V v){return std::isfinite(v.x)&&std::isfinite(v.y)&&std::isfinite(v.z);}
const double mu0=4*std::acos(-1.)*1e-7;
using Clock=std::chrono::steady_clock;
unsigned long rss(){rusage r{};if(getrusage(RUSAGE_SELF,&r))throw std::runtime_error("RSS query failed");
#ifdef __APPLE__
    return static_cast<unsigned long>(r.ru_maxrss);
#else
    return static_cast<unsigned long>(r.ru_maxrss)*1024;
#endif
}
struct C {
    std::string name,origin;
    std::array<int,3> n,pbc;
    std::array<double,3> h;
    std::array<double,2> Ms,A,D,K1,K2;
    double Ah,Anh,volume,wall;
    V axis;
    bool individual_axes=false;std::array<V,2> axes{};
    std::array<int,4> active;
    int repeats;
    unsigned long memory;
    std::size_t count;
    std::array<std::vector<V>,2> m;
};
template<class T,std::size_t N> void take(std::istream& f,std::array<T,N>& v){for(auto&x:v)if(!(f>>x))throw std::runtime_error("malformed input");}
C read(const std::filesystem::path& path){
    if(std::filesystem::file_size(path)>64UL*1024*1024)throw std::runtime_error("input exceeds bounded parser size");
    std::ifstream f(path);C c;std::string schema;
    if(!(f>>schema>>c.name>>c.origin)||schema!="P-Anh-v1")throw std::runtime_error("bad schema");
    for(auto s:{c.name,c.origin})if(s.size()>100||s.find_first_not_of("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_.-")!=std::string::npos)throw std::runtime_error("bad label");
    take(f,c.n);take(f,c.h);take(f,c.pbc);take(f,c.Ms);take(f,c.A);
    std::array<double,2> ah,anh;take(f,ah);take(f,anh);take(f,c.D);take(f,c.K1);take(f,c.K2);
    if(!(f>>c.axis.x>>c.axis.y>>c.axis.z))throw std::runtime_error("malformed easy axis");
    take(f,c.active);
    if(!(f>>c.repeats>>c.wall>>c.memory))throw std::runtime_error("missing budgets");
    c.count=1;
    for(int d=0;d<3;d++){
        if(c.n[d]<1||c.n[d]>1024||!std::isfinite(c.h[d])||c.h[d]<=0||c.pbc[d]<0||c.pbc[d]>1)throw std::runtime_error("invalid grid");
        if(c.pbc[d]&&c.n[d]<3)throw std::runtime_error("periodic dimension needs >=3 cells");
        c.count*=c.n[d];
    }
    if(c.count>1048576)throw std::runtime_error("grid exceeds frozen implementation bound");
    if(!std::isfinite(ah[0])||!std::isfinite(ah[1])||ah[0]!=ah[1])throw std::runtime_error("nonreciprocal Ah unsupported");
    if(!std::isfinite(anh[0])||!std::isfinite(anh[1])||anh[0]!=anh[1])throw std::runtime_error("nonreciprocal Anh unsupported");
    c.Anh=anh[0];
    if(c.Anh!=0 && (c.n[2]!=1 || c.pbc!=std::array<int,3>{1,1,0}))throw std::runtime_error("nonzero Anh requires complete XY positive periodic nz1");
    c.Ah=ah[0];c.volume=c.h[0]*c.h[1]*c.h[2];
    for(int i=0;i<2;i++)if(c.Ms[i]<=0||c.A[i]<=0||!std::isfinite(c.Ms[i])||!std::isfinite(c.A[i])||!std::isfinite(c.D[i])||!std::isfinite(c.K1[i])||!std::isfinite(c.K2[i]))throw std::runtime_error("invalid SI material coefficients");
    if(!(std::abs(c.Anh)<2*std::sqrt(c.A[0]*c.A[1])))throw std::runtime_error("gradient energy not strictly positive definite");
    for(int flag:c.active)if(flag!=0&&flag!=1)throw std::runtime_error("invalid module flag");
    if(!finite(c.axis)||std::abs(norm(c.axis)-1)>1e-12)throw std::runtime_error("easy axis must be unit");
    if(!std::isfinite(c.volume)||c.volume<=0||!std::isfinite(c.wall)||c.wall<=0||c.wall>30||c.memory==0||c.memory>2147483648UL||c.repeats<1||c.repeats>1000)throw std::runtime_error("invalid resource budget");
    for(auto&v:c.m)v.resize(c.count);
    for(std::size_t j=0;j<c.count;j++)for(int i=0;i<2;i++){
        auto&v=c.m[i][j];if(!(f>>v.x>>v.y>>v.z)||!finite(v)||std::abs(norm(v)-1)>1e-12)throw std::runtime_error("invalid or nonunit state");
    }
    std::string trailing;if(f>>trailing)throw std::runtime_error("extra unsupported input");return c;
}
V easy_axis(const C&c,int i){return c.individual_axes?c.axes[i]:c.axis;}
struct Field {
#ifdef SCRIPT_API_TRACE
 std::array<unsigned long,4> script_calls{};
#endif
 std::array<std::vector<V>,2> H;std::array<double,4> E{}; double Ecross=0; std::array<std::array<std::vector<V>,2>,5> parts;};
Field evaluate(const C&c,bool record_parts=true){
    Field out;for(auto&v:out.H)v.resize(c.count);if(record_parts)for(auto&part:out.parts)for(auto&v:part)v.resize(c.count);
    std::array<std::size_t,3> stride={1,static_cast<std::size_t>(c.n[0]),static_cast<std::size_t>(c.n[0]*c.n[1])};
    for(std::size_t j=0;j<c.count;j++){
        std::array<int,3> pos={static_cast<int>(j%c.n[0]),static_cast<int>((j/c.n[0])%c.n[1]),static_cast<int>(j/(c.n[0]*c.n[1]))};
        for(int d=0;d<3;d++){
            if(c.n[d]==1)continue;
            std::size_t other;
            if(pos[d]+1<c.n[d])other=j+stride[d];
            else if(c.pbc[d])other=j-(c.n[d]-1)*stride[d];
            else continue;
            if(c.active[0]){
                V da=c.m[0][other]-c.m[0][j],db=c.m[1][other]-c.m[1][j];
                double e=.5*c.volume*c.Anh*dot(da,db)/(c.h[d]*c.h[d]);out.E[0]+=e;out.Ecross+=e;
                for(int i=0;i<2;i++){
                    V value=(i==0?db:da)*(c.Anh/(mu0*c.Ms[i]*c.h[d]*c.h[d]));
                    out.H[i][j]+=value;out.H[i][other]+=value*(-1);
                    if(record_parts){out.parts[1][i][j]+=value;}if(record_parts){out.parts[1][i][other]+=value*(-1);}
                }
            }
            for(int i=0;i<2;i++){
                V q=c.m[i][j],r=c.m[i][other],difference=r-q;
                if(c.active[0]){
                    out.E[0]+=.5*c.volume*c.A[i]*dot(difference,difference)/(c.h[d]*c.h[d]);
                    V value=difference*(2*c.A[i]/(mu0*c.Ms[i]*c.h[d]*c.h[d]));
                    out.H[i][j]+=value;out.H[i][other]+=value*(-1);
                    if(record_parts){out.parts[0][i][j]+=value;}if(record_parts){out.parts[0][i][other]+=value*(-1);}
                }
                if(d<2&&c.active[2]){
                    out.E[2]+=.5*c.volume*c.D[i]*(q[d]*r.z-q.z*r[d])/c.h[d];
                    double k=c.D[i]/(mu0*c.Ms[i]*c.h[d]);
                    out.H[i][j][d]-=k*r.z;out.H[i][j].z+=k*r[d];
                    out.H[i][other][d]+=k*q.z;out.H[i][other].z-=k*q[d];
                    if(record_parts){out.parts[3][i][j][d]-=k*r.z;}if(record_parts){out.parts[3][i][j].z+=k*r[d];}
                    if(record_parts){out.parts[3][i][other][d]+=k*q.z;}if(record_parts){out.parts[3][i][other].z-=k*q[d];}
                }
            }
        }
        if(c.active[1]){
            out.E[1]+=-2*c.Ah*c.volume*dot(c.m[0][j],c.m[1][j]);
            for(int i=0;i<2;i++){V value=c.m[1-i][j]*(4*c.Ah/(mu0*c.Ms[i]));out.H[i][j]+=value;if(record_parts){out.parts[2][i][j]+=value;}}
        }
        if(c.active[3])for(int i=0;i<2;i++){
            double u=dot(c.m[i][j],easy_axis(c,i)),s=1-u*u;
            out.E[3]+=.5*c.volume*(c.K1[i]*s+c.K2[i]*s*s);
            V value=easy_axis(c,i)*(2*u*(c.K1[i]+2*c.K2[i]*s)/(mu0*c.Ms[i]));out.H[i][j]+=value;if(record_parts){out.parts[4][i][j]+=value;}
        }
    }
    for(double e:out.E)if(!std::isfinite(e))throw std::runtime_error("nonfinite energy");
    for(auto&v:out.H)for(auto h:v)if(!finite(h))throw std::runtime_error("nonfinite field");
    return out;
}
void vec(std::ostream&f,V v){f<<','<<v.x<<','<<v.y<<','<<v.z;}
int main(int argc,char**argv){
    std::filesystem::path output;bool created=false;
    try{
        if(argc!=3)throw std::runtime_error("usage: grid_fields INPUT NEW_OUTPUT");
        auto begin=Clock::now();C c=read(argv[1]);output=argv[2];
        if(std::filesystem::exists(output))throw std::runtime_error("refusing to overwrite evidence");
        std::filesystem::create_directories(output);created=true;std::filesystem::copy_file(argv[1],output/"input.dat");
        auto check=[&]{if(std::chrono::duration<double>(Clock::now()-begin).count()>c.wall)throw std::runtime_error("wall budget exceeded");if(rss()>c.memory)throw std::runtime_error("memory budget exceeded");};check();
        Field result;double core=0;volatile double checksum=0;
        for(int pass=0;pass<c.repeats;pass++){
            auto t=Clock::now();result=evaluate(c);double sum=0;
            for(auto&v:result.H)for(auto h:v)sum+=h.x+h.y+h.z;
            checksum=sum;core+=std::chrono::duration<double>(Clock::now()-t).count();check();
        }
        std::ofstream f(output/"fields.csv");f<<std::setprecision(17)<<"cell,m_Ax,m_Ay,m_Az,m_Bx,m_By,m_Bz,H_Ax,H_Ay,H_Az,H_Bx,H_By,H_Bz\n";
        for(std::size_t j=0;j<c.count;j++){f<<j;vec(f,c.m[0][j]);vec(f,c.m[1][j]);vec(f,result.H[0][j]);vec(f,result.H[1][j]);f<<'\n';}
        f.flush();if(!f)throw std::runtime_error("CSV output failure");check();
        std::ofstream pf(output/"module_fields.csv");pf<<std::setprecision(17)<<"cell";for(auto label:{"self","cross","Ah","DMI","anis"})for(auto sub:{"A","B"})for(auto axis:{"x","y","z"})pf<<','<<label<<'_'<<sub<<axis;pf<<'\n';
        for(std::size_t j=0;j<c.count;j++){pf<<j;for(auto&part:result.parts){vec(pf,part[0][j]);vec(pf,part[1][j]);}pf<<'\n';}pf.flush();if(!pf)throw std::runtime_error("part field output failure");check();
        std::ofstream ep(output/"energy_parts.json");ep<<std::setprecision(17)<<"{\"self_J\":"<<result.E[0]-result.Ecross<<",\"cross_J\":"<<result.Ecross<<",\"Ah_J\":"<<result.E[1]<<",\"DMI_J\":"<<result.E[2]<<",\"anis_J\":"<<result.E[3]<<"}\n";ep.flush();if(!ep)throw std::runtime_error("part energy output failure");check();
        std::ofstream summary(output/"native_summary.json");summary<<std::setprecision(17)<<"{\"status\":\"completed\",\"case\":\""<<c.name<<"\",\"origin\":\""<<c.origin<<"\",\"precision\":\"double\",\"mu0\":"<<mu0<<",\"cells\":"<<c.count<<",\"energy_parts_J\":[";
        for(int k=0;k<4;k++){if(k)summary<<',';summary<<result.E[k];}
        summary<<"],\"repeats\":"<<c.repeats<<",\"field_update_seconds\":"<<core/c.repeats<<",\"wall_seconds\":"<<std::chrono::duration<double>(Clock::now()-begin).count()<<",\"peak_rss_bytes\":"<<rss()<<",\"checksum\":"<<checksum<<"}\n";summary.flush();if(!summary)throw std::runtime_error("summary output failure");
        std::cout<<"completed "<<c.name<<" cells="<<c.count<<'\n';return 0;
    }catch(const std::exception&e){std::cerr<<"FAILED: "<<e.what()<<'\n';if(created){std::ofstream f(output/"failure.txt");f<<e.what()<<'\n';}return 2;}
}
