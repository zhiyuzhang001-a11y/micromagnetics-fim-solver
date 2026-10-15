#pragma once
// Extracted stage and combination order from frozen dynamic/core.cpp.
// State is an array of one (FM) or two (FiM) vector fields. No stage projection.
template<class State> State state_add(const State&a,const State&b,double f){
 State r=a;for(size_t i=0;i<a.size();i++)for(size_t j=0;j<a[i].size();j++)r[i][j]+=b[i][j]*f;return r;
}
template<class State,class Eval,class Rhs,class Loss>
State rk4_raw(const State&m,double dt,Eval eval,Rhs rhs,Loss loss,double&diss){
 auto e1=eval(m);auto k1=rhs(m,e1);auto d1=loss(m,e1);
 auto s2=state_add(m,k1,dt/2);auto e2=eval(s2);auto k2=rhs(s2,e2);auto d2=loss(s2,e2);
 auto s3=state_add(m,k2,dt/2);auto e3=eval(s3);auto k3=rhs(s3,e3);auto d3=loss(s3,e3);
 auto s4=state_add(m,k3,dt);auto e4=eval(s4);auto k4=rhs(s4,e4);auto d4=loss(s4,e4);
 State candidate=m;for(size_t i=0;i<m.size();i++)for(size_t j=0;j<m[i].size();j++)candidate[i][j]+=(k1[i][j]+k2[i][j]*2+k3[i][j]*2+k4[i][j])*(dt/6);
 diss=0;for(size_t i=0;i<m.size();i++)diss+=(d1[i]+2*d2[i]+2*d3[i]+d4[i])*dt/6;return candidate;
}
template<class State> double project_endpoint(State&candidate){
 double raw=0;for(auto&v:candidate)for(auto&q:v){double n=std::hypot(q.x,q.y,q.z);if(!finite(q)||!std::isfinite(n)||n==0)throw std::runtime_error("unsafe raw normalization");raw=std::max(raw,std::abs(n-1));q={q.x/n,q.y/n,q.z/n};if(!finite(q))throw std::runtime_error("unsafe projected state");}return raw;
}
