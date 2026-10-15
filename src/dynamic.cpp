#include "physics_prefix.hpp"
Spins load_state(const std::filesystem::path&p,size_t count){
 if(std::filesystem::file_size(p)!=count*2*3*sizeof(double))throw std::runtime_error("resume state size mismatch");
 std::ifstream f(p,std::ios::binary);Spins m;for(auto&v:m){v.resize(count);for(auto&q:v){double a[3];f.read(reinterpret_cast<char*>(a),sizeof(a));if(!f)throw std::runtime_error("resume state read failure");q={a[0],a[1],a[2]};if(!finite(q)||std::abs(safe_norm(q)-1)>1e-12)throw std::runtime_error("resume state violates inherited input unit constraint");}}return m;
}
int main(int argc,char**argv){
 auto begin=Clock::now();std::filesystem::path out;bool made=false,hasCurrent=false;int accepted=0,lastRawStep=0;double dt=0,startps=0;Spins m,lastRaw;Evaluation current;
 try{
  if(argc!=10)throw std::runtime_error("INPUT KERNEL NEW_OUTPUT DT_FS RESTORE START_PS END_PS E_ORIGINAL_J LOSS_BEFORE_J");
  std::string token(argv[4]);double fs=token=="12.5"?12.5:token=="25"?25:token=="100"?100:token=="200"?200:token=="500"?500:0;if(fs==0)throw std::runtime_error("exact supported dt tokens only");
  std::size_t usedStart=0,usedEnd=0;startps=std::stod(argv[6],&usedStart);double endps=std::stod(argv[7],&usedEnd);if(usedStart!=std::string(argv[6]).size()||usedEnd!=std::string(argv[7]).size()||!std::isfinite(startps)||!std::isfinite(endps)||startps<0||endps<startps||endps>500||endps-startps>100)throw std::runtime_error("bounded frozen global interval");
  double originalE=std::stod(argv[8]),lossBefore=std::stod(argv[9]);if(!std::isfinite(originalE)||!std::isfinite(lossBefore)||lossBefore<0)throw std::runtime_error("invalid energy origin/loss history");
  dt=fs*1e-15;int limit=static_cast<int>((endps-startps)*1000/fs);if(limit*fs!=(endps-startps)*1000)throw std::runtime_error("nonintegral intervalsteps");out=argv[3];if(std::filesystem::exists(out))throw std::runtime_error("no overwrite");std::filesystem::create_directories(out);made=true;
  auto check=[&]{if(std::chrono::duration<double>(Clock::now()-begin).count()>60||rss()>2147483648UL)throw std::runtime_error("shared DYN1 case resource limit");};
  Model model(read(argv[1]),argv[2],{0,0,-.002/mu0});if(std::string(argv[5])=="-"){if(startps!=0)throw std::runtime_error("seed only atglobal0");m=model.c.m;}else m=load_state(argv[5],model.c.count);
  auto evaluate_stage=[&](const Spins&s){state_check(s);auto e=model.eval(s);check();return e;};
  current=evaluate_stage(m);hasCurrent=true;double segmentE=current.E,globalLoss=lossBefore,segmentLoss=0;
  snapshot(out/"step_0.bin",m);save_eval(out,"initial",current);snapshot(out/"initial_rhs.bin",rhs(m,current));
  auto checkpoint=[&](int ps){std::string tag="checkpoint_"+std::to_string(ps)+"ps";snapshot(out/(tag+".bin"),m);save_eval(out,tag,current);snapshot(out/(tag+"_rhs.bin"),rhs(m,current));};checkpoint(static_cast<int>(startps));
  auto residual=[&](int i){double x=0;for(size_t j=0;j<m[i].size();j++)x=std::max(x,norm(project(m[i][j],current.H[i][j])));return x;};
  std::ofstream hist(out/"history.csv");hist<<std::setprecision(17)<<"step,time_s,energy_J,delta_energy_J,residual_A_Apm,residual_B_Apm,raw_A,raw_B,raw_norm_min_A,raw_norm_max_A,raw_norm_min_B,raw_norm_max_B,correction_A,correction_B,max_step_direction_A,max_step_direction_B,dissipation_A_W,dissipation_B_W,rk_stage_dissipated_J,cumulative_rk_dissipated_J,energy_dissipation_defect_J,segment_rk_dissipated_J,segment_energy_dissipation_defect_J\n";
  auto d0=dissipation(m,current,model.c);hist<<"0,"<<startps*1e-12<<','<<current.E<<",0,"<<residual(0)<<','<<residual(1)<<",0,0,1,1,1,1,0,0,0,0,"<<d0[0]<<','<<d0[1]<<",0,"<<globalLoss<<','<<current.E-originalE+globalLoss<<",0,0\n";hist.flush();
  std::array<double,2> rawmax{};
  for(int step=1;step<=limit;step++){
   auto e1=evaluate_stage(m);auto k1=rhs(m,e1);auto d1=dissipation(m,e1,model.c);
   auto s2=add(m,k1,dt/2);auto e2=evaluate_stage(s2);auto k2=rhs(s2,e2);auto d2=dissipation(s2,e2,model.c);
   auto s3=add(m,k2,dt/2);auto e3=evaluate_stage(s3);auto k3=rhs(s3,e3);auto d3=dissipation(s3,e3,model.c);
   auto s4=add(m,k3,dt);auto e4=evaluate_stage(s4);auto k4=rhs(s4,e4);auto d4=dissipation(s4,e4,model.c);
   Spins candidate=m;for(int i=0;i<2;i++)for(size_t j=0;j<m[i].size();j++)candidate[i][j]+=(k1[i][j]+k2[i][j]*2+k3[i][j]*2+k4[i][j])*(dt/6);
   lastRaw=candidate;lastRawStep=step;if(step==1)snapshot(out/"first_raw.bin",candidate);
   std::array<double,2> raw{},lo={INFINITY,INFINITY},hi{},correction{},stepdiff{};
   for(int i=0;i<2;i++)for(size_t j=0;j<m[i].size();j++){double q=safe_norm(candidate[i][j]);if(!finite(candidate[i][j])||!std::isfinite(q)||q==0)throw std::runtime_error("nonfinite/zero raw norm, unsafe normalization");raw[i]=std::max(raw[i],std::abs(q-1));lo[i]=std::min(lo[i],q);hi[i]=std::max(hi[i],q);}
   for(int i=0;i<2;i++)for(size_t j=0;j<m[i].size();j++){V q=candidate[i][j];double n=safe_norm(q);candidate[i][j]={q.x/n,q.y/n,q.z/n};if(!finite(candidate[i][j])||!std::isfinite(safe_norm(candidate[i][j]))||safe_norm(candidate[i][j])==0)throw std::runtime_error("unsafe numerical normalization");correction[i]=std::max(correction[i],safe_norm(candidate[i][j]-q));stepdiff[i]=std::max(stepdiff[i],safe_norm(candidate[i][j]-m[i][j]));rawmax[i]=std::max(rawmax[i],raw[i]);}
   auto endpoint=evaluate_stage(candidate);auto de=endpoint.E-current.E;auto dend=dissipation(candidate,endpoint,model.c);
   double diss=0;for(int i=0;i<2;i++)diss+=(d1[i]+2*d2[i]+2*d3[i]+d4[i])*dt/6;globalLoss+=diss;segmentLoss+=diss;if(!std::isfinite(globalLoss)||!std::isfinite(segmentLoss))throw std::runtime_error("overflow in cumulative dissipation");
   m=std::move(candidate);current=std::move(endpoint);accepted=step;double globalTime=startps*1e-12+step*dt;
   hist<<step<<','<<globalTime<<','<<current.E<<','<<de<<','<<residual(0)<<','<<residual(1)<<','<<raw[0]<<','<<raw[1]<<','<<lo[0]<<','<<hi[0]<<','<<lo[1]<<','<<hi[1]<<','<<correction[0]<<','<<correction[1]<<','<<stepdiff[0]<<','<<stepdiff[1]<<','<<dend[0]<<','<<dend[1]<<','<<diss<<','<<globalLoss<<','<<current.E-originalE+globalLoss<<','<<segmentLoss<<','<<current.E-segmentE+segmentLoss<<'\n';hist.flush();if(!hist)throw std::runtime_error("history output failure");
   for(int ps:{2,4,5,10,20,25,30,38,40,50,98,100,198,200,248,250,298,300,348,350,398,400,448,450,498,500}){if(step==static_cast<int>((ps-startps)*1000/fs)&&ps>startps&&ps<=endps){checkpoint(ps);snapshot(out/("raw_checkpoint_"+std::to_string(ps)+"ps.bin"),lastRaw);}}check();
  }
  snapshot(out/"final.bin",m);save_eval(out,"final",current);snapshot(out/"final_rhs.bin",rhs(m,current));check();
  std::ofstream f(out/"summary.json");f<<std::setprecision(17)<<"{\"status\":\"completed_frozen_segment\",\"accepted_steps\":"<<accepted<<",\"start_time_ps\":"<<startps<<",\"reached_time_ps\":"<<startps+accepted*dt/1e-12<<",\"dt_fs\":"<<fs<<",\"raw_A_max\":"<<rawmax[0]<<",\"raw_B_max\":"<<rawmax[1]<<",\"energy_scale_J\":"<<model.scale<<",\"energy_original_J\":"<<originalE<<",\"energy_start_J\":"<<segmentE<<",\"energy_final_J\":"<<current.E<<",\"loss_before_J\":"<<lossBefore<<",\"cumulative_rk_dissipated_J\":"<<globalLoss<<",\"segment_rk_dissipated_J\":"<<segmentLoss<<",\"energy_dissipation_defect_J\":"<<current.E-originalE+globalLoss<<",\"segment_energy_dissipation_defect_J\":"<<current.E-segmentE+segmentLoss<<",\"field_calls\":"<<model.dip.calls<<",\"wall_s\":"<<std::chrono::duration<double>(Clock::now()-begin).count()<<",\"rss_bytes\":"<<rss()<<"}\n";return 0;
 }catch(const std::exception&e){if(made){if(hasCurrent){snapshot(out/"last_accepted.bin",m);save_eval(out,"last_accepted",current);}if(!lastRaw[0].empty())snapshot(out/"last_complete_raw.bin",lastRaw);std::ofstream f(out/"failure.json");f<<std::setprecision(17)<<"{\"status\":\"safety_stopped\",\"accepted_steps\":"<<accepted<<",\"reached_time_ps\":"<<startps+accepted*dt/1e-12<<",\"last_complete_raw_step\":"<<lastRawStep<<"}\n";std::ofstream reason(out/"failure.txt");reason<<e.what();}std::cerr<<e.what()<<'\n';return 2;}
}
