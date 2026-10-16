#pragma once
#include "hp.hpp"
#include <array>
#include <algorithm>
#include <cmath>
#include <stdexcept>
HP newell_f(HP x,HP y,HP z){
    x=abs(x);y=abs(y);z=abs(z);HP R=sqrt(x*x+y*y+z*z);
    if(R==0)return 0;
    HP out=(2*x*x-y*y-z*z)*R/6;
    if(x*x+z*z>0)out+=y*(z*z-x*x)*asinh(y/sqrt(x*x+z*z))/2;
    if(x*x+y*y>0)out+=z*(y*y-x*x)*asinh(z/sqrt(x*x+y*y))/2;
    if(x>0)out-=x*y*z*atan(y*z/(x*R));
    return out;
}
HP newell_g(HP x,HP y,HP z){
    if(x==0||y==0)return 0;
    HP sign=(x<0?-1.:1.)*(y<0?-1.:1.);x=abs(x);y=abs(y);z=abs(z);
    HP R=sqrt(x*x+y*y+z*z);
    HP out=-x*y*R/3;
    out+=x*y*z*asinh(z/sqrt(x*x+y*y));
    out+=y*(3*z*z-y*y)*asinh(x/sqrt(y*y+z*z))/6;
    out+=x*(3*z*z-x*x)*asinh(y/sqrt(x*x+z*z))/6;
    if(z>0)out-=z*z*z*atan(x*y/(z*R))/6;
    out-=y*y*z*atan(x*z/(y*R))/2;
    out-=x*x*z*atan(y*z/(x*R))/2;
    return sign*out;
}
using Tensor=std::array<double,6>; // xx yy zz xy xz yz
Tensor original_double_tensor_at(std::array<HP,3> h,std::array<HP,3> r){
    HP scale=std::max({h[0],h[1],h[2]});
    if(!isfinite(scale)||scale<=0)throw std::runtime_error("invalid cell shape");
    for(int a=0;a<3;a++){if(h[a]<=0||!isfinite(h[a])||!isfinite(r[a]))throw std::runtime_error("invalid tensor point");h[a]/=scale;r[a]/=scale;}
    std::array<HP,6> sums{},comp{};
    auto add=[&](int a,HP value){HP t=sums[a]+value;if(abs(sums[a])>=abs(value))comp[a]+=(sums[a]-t)+value;else comp[a]+=(value-t)+sums[a];sums[a]=t;};
    const int weights[3]={-1,2,-1};
    for(int i=-1;i<=1;i++)for(int j=-1;j<=1;j++)for(int k=-1;k<=1;k++){
        HP x=r[0]+i*h[0],y=r[1]+j*h[1],z=r[2]+k*h[2];HP w=weights[i+1]*weights[j+1]*weights[k+1];
        add(0,w*newell_f(x,y,z));add(1,w*newell_f(y,x,z));add(2,w*newell_f(z,x,y));
        add(3,w*newell_g(x,y,z));add(4,w*newell_g(x,z,y));add(5,w*newell_g(y,z,x));
    }
    HP denominator=4*acos(HP(-1))*h[0]*h[1]*h[2];
    for(int a=0;a<6;a++)sums[a]=(sums[a]+comp[a])/denominator;
    // These off-diagonal values are mathematically zero by exact reflection symmetry.
    if(r[0]==0||r[1]==0)sums[3]=0;
    if(r[0]==0||r[2]==0)sums[4]=0;
    if(r[1]==0||r[2]==0)sums[5]=0;
    Tensor out{};for(int a=0;a<6;a++)out[a]=static_cast<double>(sums[a]);return out;
}

