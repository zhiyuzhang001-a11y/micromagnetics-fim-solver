#pragma once
// Same production arithmetic order as phase2d_entry/gilbert.hpp.
// gamma_G is explicit SI Gilbert coefficient; grel remains a material parameter.
V gilbert_gamma(V m,V H,double grel,double alpha,double gamma_G){
 V a={m.y*H.z-m.z*H.y,m.z*H.x-m.x*H.z,m.x*H.y-m.y*H.x};
 V b={m.y*a.z-m.z*a.y,m.z*a.x-m.x*a.z,m.x*a.y-m.y*a.x};
 return (a+b*alpha)*(-gamma_G*grel/(1+alpha*alpha));
}
V gilbert(V m,V H,double grel,double alpha){return gilbert_gamma(m,H,grel,alpha,2.212761569e5);}
