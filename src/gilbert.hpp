#pragma once
// Shared production LLG RHS. Conservative H already assembled, A/m.
V gilbert(V m,V H,double grel,double alpha){
 V a={m.y*H.z-m.z*H.y,m.z*H.x-m.x*H.z,m.x*H.y-m.y*H.x};
 V b={m.y*a.z-m.z*a.y,m.z*a.x-m.x*a.z,m.x*a.y-m.y*a.x};
 return (a+b*alpha)*(-2.212761569e5*grel/(1+alpha*alpha));
}
