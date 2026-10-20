// The existing tensor equations; script entry has no experiment-derived resource caps.
// GPL-3.0-only. MPFR Newell plus BORIS/OOMMF-credited finite-volume asymptotics.
#include <filesystem>
#include <fstream>
#include <iostream>
#include "../grid_capacity.hpp"
#include <iomanip>
#include <sys/resource.h>
#include <chrono>
#include "../user_kernel/newell_mpfr.hpp"
#include "../user_kernel/DemagTFunc_Asympt.cpp"
#ifdef __APPLE__
constexpr unsigned long rss_multiplier=1;
#else
constexpr unsigned long rss_multiplier=1024;
#endif
struct PhysicalTensor {
 std::array<double,3>h;double scale;DemagAsymptoticDiag xx,yy,zz;DemagAsymptoticOffDiag xy;
 PhysicalTensor(std::array<double,3>v):h(v),scale(std::max({v[0],v[1],v[2]})),xx(v[0]/scale,v[1]/scale,v[2]/scale),yy(v[1]/scale,v[0]/scale,v[2]/scale),zz(v[2]/scale,v[0]/scale,v[1]/scale),xy(v[0]/scale,v[1]/scale,v[2]/scale){}
 Tensor at(int i,int j){double x=i*h[0]/scale,y=j*h[1]/scale;Tensor t{};if(std::hypot(x,y)>=40){t[0]=xx.AsymptoticLdia(x,y,0);t[1]=yy.AsymptoticLdia(y,x,0);t[2]=zz.AsymptoticLdia(0,x,y);t[3]=xy.AsymptoticLodia(x,y,0);}else t=original_double_tensor_at({HP(h[0]),HP(h[1]),HP(h[2])},{HP(i)*HP(h[0]),HP(j)*HP(h[1]),HP(0)});if(i==0||j==0)t[3]=0;for(double x:t)if(!std::isfinite(x))throw std::runtime_error("tensor nonfinite");return t;}
};
int main(int argc,char**argv){try{
 if(argc!=10)throw std::runtime_error("NX NY HX HY HZ PERIODIC MX MY NEW_OUTPUT");int nx=std::stoi(argv[1]),ny=std::stoi(argv[2]),periodic=std::stoi(argv[6]),mx=std::stoi(argv[7]),my=std::stoi(argv[8]);std::array<double,3>h={std::stod(argv[3]),std::stod(argv[4]),std::stod(argv[5])};std::filesystem::path out=argv[9];if(std::filesystem::exists(out)||nx<1||ny<1||mx<0||my<0||mx>40||my>40||(periodic!=0&&periodic!=1))throw std::runtime_error("kernel arguments");for(double q:h)if(q<=0||!std::isfinite(q))throw std::runtime_error("cell");if(*std::max_element(h.begin(),h.end())/ *std::min_element(h.begin(),h.end())>4||(!periodic&&(mx||my))||(periodic&&(nx<3||ny<3)))throw std::runtime_error("kernel geometry domain");auto start=std::chrono::steady_clock::now();PhysicalTensor tensor(h);auto layout=grid_capacity::check(nx,ny,periodic,mx,my);grid_capacity::memory(96*layout.real,"kernel capacity");std::uint64_t points_evaluated=0;auto at=[&](int x,int y){++points_evaluated;return tensor.at(x,y);};int px=layout.px,py=layout.py;auto parent=out.parent_path();if(parent.empty())parent=".";if(std::filesystem::space(parent).available<48*layout.real)throw std::runtime_error("kernel capacity: insufficient disk for payload");std::vector<Tensor>raw(px*py),effective(px*py);
 if(periodic){for(int y=0;y<ny;y++){for(int x=0;x<nx;x++){Tensor sum{},correction{};for(int ix=-mx;ix<=mx;ix++)for(int iy=-my;iy<=my;iy++){auto t=at(x+ix*nx,y+iy*ny);for(int a=0;a<6;a++){double q=t[a]-correction[a],next=sum[a]+q;correction[a]=(next-sum[a])-q;sum[a]=next;}}raw[x+y*nx]=sum;}}for(int y=0;y<ny;y++)for(int x=0;x<nx;x++){int q=x+y*nx,a=(nx-x)%nx+y*nx,b=x+(ny-y)%ny*nx,c=(nx-x)%nx+(ny-y)%ny*nx;for(int k=0;k<6;k++)effective[q][k]=.25*(raw[q][k]+(k==3?-1:1)*raw[a][k]+(k==3?-1:1)*raw[b][k]+raw[c][k]);}}
 else{for(int y=1-ny;y<ny;y++){for(int x=1-nx;x<nx;x++)effective[(x+px)%px+((y+py)%py)*px]=at(x,y);}}
 auto temp=out;temp+=".tmp";std::ofstream f(temp,std::ios::binary);f.write((char*)effective.data(),effective.size()*sizeof(Tensor));f.close();if(!f)throw std::runtime_error("kernel write");std::filesystem::rename(temp,out);std::ofstream samples(out.string()+".samples.json");int cx=int(std::ceil(40*tensor.scale/h[0])),cy=int(std::ceil(40*tensor.scale/h[1]));std::vector<std::pair<int,int>> points={{0,0},{1,0},{1,1},{cx-1,0},{cx,0},{cx+1,0},{0,cy-1},{0,cy},{0,cy+1},{29,28},{-1,1},{1,-1}};samples<<std::setprecision(17)<<"[";bool first=true;for(auto q:points){if(!first)samples<<",";first=false;auto t=tensor.at(q.first,q.second);samples<<"{\"i\":"<<q.first<<",\"j\":"<<q.second<<",\"tensor\":[";for(int a=0;a<6;a++){if(a)samples<<",";samples<<t[a];}samples<<"]}";}samples<<"]\n";samples.close();if(!samples)throw std::runtime_error("sample write");rusage measured{};getrusage(RUSAGE_SELF,&measured);std::cout<<"{\"elapsed_s\":"<<std::chrono::duration<double>(std::chrono::steady_clock::now()-start).count()<<",\"peak_rss_bytes\":"<<static_cast<unsigned long>(measured.ru_maxrss)*rss_multiplier<<",\"tensor_points\":"<<points_evaluated<<",\"MPFR_bits\":"<<HP_BITS<<",\"physical_convergence\":\"not_checked\"}\n";return 0;
 }catch(const std::exception&e){std::cerr<<e.what()<<'\n';return 2;}}
