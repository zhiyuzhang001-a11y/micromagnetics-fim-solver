// GPL-3.0-only. Zero-Model regression of the production periodic observer.
#define FIM_USER_LIBRARY 1
#include "../src/user_native.cpp"
#undef FIM_USER_LIBRARY
#include "../src/current_sot.hpp"
#include "../src/current_observe.hpp"
int main(){try{UserConfig u;u.c.n={32,32,1};u.c.count=1024;u.c.h={4e-9,4e-9,3e-9};u.c.pbc={1,1,0};CurrentSOT d;Track track;double last=0,error=0;for(double cx:{30.5,31.5,.5,1.5}){std::vector<V>m(1024);for(int y=0;y<32;y++)for(int x=0;x<32;x++){double dx=x+.5-cx,dy=y+.5-16.5;dx-=std::round(dx/32)*32;dy-=std::round(dy/32)*32;double r=std::hypot(dx,dy),t=acos(-1.)/2*(1-std::tanh((r-6)/1.5)),p=std::atan2(dy,dx);m[x+y*32]={std::sin(t)*std::cos(p),std::sin(t)*std::sin(p),std::cos(t)};}auto o=observe_current(m,u,d,track,true);if(!o.single||!o.continuous)throw std::runtime_error("periodic observer single/continuity");if(last)error=std::max(error,std::abs(o.ux-last-4));last=o.ux;}
 if(error>1e-5)throw std::runtime_error("unwrap seam");std::vector<V>uniform(1024,V{0,0,1});auto o=observe_current(uniform,u,d,track,true);if(std::isfinite(o.x)||o.single||track.continuous)throw std::runtime_error("zero Q invalidation");for(size_t k=0;k<uniform.size();k++)uniform[k]={0,0,k%2?1.:-1.};auto bad=observe_current(uniform,u,d,track,true);if(!bad.singular||bad.single)throw std::runtime_error("singular triangles invalidation");std::cout<<std::setprecision(17)<<"{\"passed\":true,\"Models\":0,\"fields\":0,\"unwrap_step_error_nm\":"<<error<<",\"zero_Q_invalid\":true,\"singular_invalid\":true}\n";return 0;}catch(const std::exception&e){std::cerr<<e.what()<<'\n';return 2;}}
