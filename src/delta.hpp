struct Sum {double s=0,c=0;void add(double x){double y=x-c,t=s+y;c=(t-s)-y;s=t;}};
double bilinear_delta(double an,double ao,double bn,double bo){return .5*((an-ao)*(bn+bo)+(bn-bo)*(an+ao));}
double stable_delta(Model&model,const Spins&old,const Spins&next,const Evaluation&eo,const Evaluation&en){
 const auto&c=model.c;std::array<Sum,7>s;double vol=c.volume;
 for(size_t j=0;j<c.count;j++){
  for(int d=0;d<2;d++){size_t stride=d==0?1:125;int pos=d==0?static_cast<int>(j%125):static_cast<int>(j/125);size_t q=pos+1<125?j+stride:j-124*stride;V da0=old[0][q]-old[0][j],da1=next[0][q]-next[0][j],db0=old[1][q]-old[1][j],db1=next[1][q]-next[1][j];double h=c.h[d];s[0].add(.5*c.volume*(c.A[0]*dot(da1-da0,da1+da0)+c.A[1]*dot(db1-db0,db1+db0))/(h*h));s[1].add(.25*c.volume*c.Anh*(dot(da1-da0,db1+db0)+dot(db1-db0,da1+da0))/(h*h));
   for(int i=0;i<2;i++){auto a=old[i][j],b=old[i][q],an=next[i][j],bn=next[i][q];double value=bilinear_delta(an[d],a[d],bn.z,b.z)-bilinear_delta(an.z,a.z,bn[d],b[d]);s[3].add(.5*c.volume*c.D[i]*value/h);}
  }
  auto u0=old[0][j]+old[1][j],u1=next[0][j]+next[1][j];s[2].add(-c.Ah*c.volume*dot(u1-u0,u1+u0));
  for(int i=0;i<2;i++){auto a=old[i][j],n=next[i][j];s[4].add(.5*c.volume*c.K1[i]*((n.x-a.x)*(n.x+a.x)+(n.y-a.y)*(n.y+a.y)));}
  auto M0=(old[0][j]*c.Ms[0]+old[1][j]*c.Ms[1])*.5,M1=(next[0][j]*c.Ms[0]+next[1][j]*c.Ms[1])*.5;s[5].add(-.5*mu0*vol*dot(M1-M0,en.Hd[j]+eo.Hd[j]));s[6].add(-mu0*vol*dot(M1-M0,model.external));
 }
 Sum all;for(auto q:s)all.add(q.s);if(!std::isfinite(all.s))throw std::runtime_error("nonfinite stable energy difference");return all.s;
}
