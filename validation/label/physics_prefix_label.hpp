#include "accepted_model_label.hpp"
#include "../../src/gilbert.hpp"
double safe_norm(V q){return std::hypot(q.x,q.y,q.z);}
void state_check(const Spins&m){for(const auto&v:m)for(auto q:v)if(!finite(q))throw std::runtime_error("nonfinite stage state");}
Spins rhs(const Spins&m,const Evaluation&e){Spins k=m;for(int i=0;i<2;i++)for(size_t j=0;j<m[i].size();j++){if(!finite(e.H[i][j]))throw std::runtime_error("nonfinite combined field");k[i][j]=gilbert(m[i][j],e.H[i][j],1,.01);if(!finite(k[i][j]))throw std::runtime_error("nonfinite RHS");}return k;}
std::array<double,2> dissipation(const Spins&m,const Evaluation&e,const C&c){
 std::array<double,2> d{};for(int i=0;i<2;i++){long double sum=0;for(size_t j=0;j<m[i].size();j++){auto a=m[i][j],b=e.H[i][j];V cross={a.y*b.z-a.z*b.y,a.z*b.x-a.x*b.z,a.x*b.y-a.y*b.x};sum+=dot(cross,cross);}d[i]=static_cast<double>(sum)*mu0*c.volume*c.Ms[i]*2.212761569e5*.01/(2*(1+.01*.01));if(!std::isfinite(d[i]))throw std::runtime_error("overflow in dissipation diagnostic");}return d;
}
