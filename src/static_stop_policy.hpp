#pragma once
#include <climits>
#include <memory>
#include <sstream>

constexpr const char* POST_PH_POLICY="FIM_POST_PH_MAX_V1";
struct PolicyResidual {double A=0,B=0;bool valid=false;std::string error;};
bool valid_policy_tolerance(double x){return std::isfinite(x)&&x>0;}
PolicyResidual policy_residual(const Spins&m,const Spins&H,const std::array<double,2>&Ms,std::size_t count=0){
 PolicyResidual r;
 for(int i=0;i<2;i++){
  if(!std::isfinite(Ms[i])||Ms[i]<=0||m[i].empty()||m[i].size()!=H[i].size()||(count&&m[i].size()!=count)){r.error="invalid_sublattice_or_material";return r;}
  for(std::size_t j=0;j<m[i].size();j++){
   if(!finite(m[i][j])||!finite(H[i][j])){r.error="nonfinite_state_or_field";return r;}
   if(std::abs(norm(m[i][j])-1)>1e-12){r.error="nonunit_state";return r;}
   double q=norm(project(m[i][j],H[i][j]));
   if(!std::isfinite(q)){r.error="nonfinite_projected_field";return r;}
   (i==0?r.A:r.B)=std::max(i==0?r.A:r.B,q);
  }
 }
 if(m[0].size()!=m[1].size()){r.error="sublattice_size_mismatch";return r;}
 r.valid=true;return r;
}
// At a completed current H: invalid -> external time/field overrun -> residual.
// Step/next-field limits are considered only when another update is needed.
std::string policy_decide(const PolicyResidual&r,double eps,bool timeout,bool field_overrun,int updates,int cap,bool next_field_available){
 if(!r.valid)return r.error;
 if(timeout)return "wall_budget";
 if(field_overrun)return "field_budget";
 if(r.A<=eps&&r.B<=eps)return "residual_tolerance";
 if(updates>=cap)return "step_budget";
 if(!next_field_available)return "field_budget";
 return "continue";
}
std::string policy_json_number(double x){if(!std::isfinite(x))return "null";std::ostringstream s;s<<std::setprecision(17)<<x;return s.str();}
std::string policy_json_string(const std::string&s){std::string r="\"";for(char c:s){if(c=='\\'||c=='\"')r+='\\';if(c=='\n')r+="\\n";else r+=c;}return r+'\"';}
double policy_double(const char*s){std::size_t used=0;double x=std::stod(s,&used);if(used!=std::string(s).size()||!std::isfinite(x))throw std::runtime_error("invalid_finite_argument");return x;}
int policy_int(const char*s,int maximum){std::size_t used=0;long long n=std::stoll(s,&used);if(used!=std::string(s).size()||n<0||n>maximum)throw std::runtime_error("invalid_integer_argument");return static_cast<int>(n);}
std::string policy_exception_reason(const std::string&prior,bool current){return prior=="wall_budget"?prior:(current?"native_error":"invalid_input");}
void policy_save_eval(const std::filesystem::path&out,const Evaluation&e){
 blob(out/"final_H_A.bin",e.H[0]);blob(out/"final_H_B.bin",e.H[1]);blob(out/"final_Hd.bin",e.Hd);
 bool bad=!std::isfinite(e.E)||!std::isfinite(e.residual);for(double x:e.Eparts)bad=bad||!std::isfinite(x);for(auto&v:e.H)for(auto q:v)bad=bad||!finite(q);
 std::ofstream f(out/"final_energy.json");f<<"{\"total_J\":"<<policy_json_number(e.E)<<",\"parts_J\":[";for(int k=0;k<7;k++){if(k)f<<',';f<<policy_json_number(e.Eparts[k]);}f<<"],\"residual_scaled\":"<<policy_json_number(e.residual)<<",\"contains_nonfinite\":"<<(bad?"true":"false")<<"}\n";if(!f)throw std::runtime_error("energy_output_failure");
}

int run_policy(int argc,char**argv){
 auto start=Clock::now();std::filesystem::path out;std::unique_ptr<Model> model;SD s;Evaluation e;bool current=false,made=false;int local=0,initial_global=0;double eps=0,budget=0;int max_updates=0,max_fields=0;std::string reason="invalid_input",detail;PolicyResidual residual;V external;
 try{
  if(argc!=14)throw std::runtime_error("CONFIG KERNEL SEED OUT run_policy RESTORE_OR_DASH BUDGET TOL MAX_UPDATES MAX_FIELDS Hx Hy Hz");
  eps=policy_double(argv[8]);budget=policy_double(argv[7]);max_updates=policy_int(argv[9],30000);max_fields=policy_int(argv[10],1000000);
  if(!valid_policy_tolerance(eps)||budget<=0||budget>180||max_fields<1)throw std::runtime_error("invalid_policy_budget_or_tolerance");
  external={policy_double(argv[11]),policy_double(argv[12]),policy_double(argv[13])};
  out=argv[4];if(std::filesystem::exists(out))throw std::runtime_error("no_overwrite");std::filesystem::create_directories(out);made=true;
  model=std::make_unique<Model>(read(argv[1]),argv[2],external);
  if(std::string(argv[6])!="-")s=sd_restore(argv[6],true);
  else{
   s.m=model->c.m;std::ifstream f(argv[3],std::ios::binary);
   for(auto&v:s.m)for(auto&q:v){double x[3];f.read(reinterpret_cast<char*>(x),sizeof(x));q={x[0],x[1],x[2]};if(!finite(q)||std::abs(norm(q)-1)>1e-12)throw std::runtime_error("invalid_seed_state");}
   if(!f||f.peek()!=EOF)throw std::runtime_error("invalid_seed_size");
   // SD-v380-v1 retains its fixed three-array layout even for a zero-update CP.
   // These history placeholders are ignored by advance_sd while updates==0.
   s.prev=s.m;s.Gprev=s.m;for(auto&v:s.Gprev)for(auto&q:v)q={};
  }
  initial_global=s.updates;
  for(auto&v:s.m)for(auto q:v)if(!finite(q)||std::abs(norm(q)-1)>1e-12)throw std::runtime_error("invalid_restored_state");
  auto elapsed=[&]{return std::chrono::duration<double>(Clock::now()-start).count();};
  if(elapsed()>=budget){reason="wall_budget";throw std::runtime_error("initial_budget_expired");}
  e=model->eval(s.m);current=true;
  std::ofstream hist(out/"history.csv");hist<<std::setprecision(17)<<"local_update,global_update,post_A_Apm,post_B_Apm,field_calls\n";
  while(true){
   residual=policy_residual(s.m,e.H,model->c.Ms,model->c.count);
   reason=policy_decide(residual,eps,elapsed()>=budget||rss()>512UL*1024*1024,model->dip.calls>static_cast<unsigned>(max_fields),local,max_updates,model->dip.calls<static_cast<unsigned>(max_fields));
   hist<<local<<','<<s.updates<<','<<(residual.valid?policy_json_number(residual.A):"null")<<','<<(residual.valid?policy_json_number(residual.B):"null")<<','<<model->dip.calls<<'\n';hist.flush();if(!hist)throw std::runtime_error("history_output_failure");
   if(reason!="continue")break;
   if(s.updates==INT_MAX){reason="global_update_overflow";break;}
   SD next=s;advance_sd(next,e.H);auto fresh=model->eval(next.m);s=std::move(next);e=std::move(fresh);local++;
  }
 }catch(const std::exception&x){detail=x.what();reason=policy_exception_reason(reason,current);}
 // A directly invoked native executable only produces an unverified candidate.
 try{
  if(made){
   if(current){snapshot(out/"final.bin",s.m);policy_save_eval(out,e);sd_checkpoint(out/"checkpoint.bin",s);SD back=sd_restore(out/"checkpoint.bin",true);if(!bits(s.m,back.m))throw std::runtime_error("checkpoint_roundtrip_failure");}
   if(budget>0&&std::chrono::duration<double>(Clock::now()-start).count()>=budget)reason="wall_budget";
   std::ofstream f(out/"native_policy_result.json");f<<"{\"policy_id\":\""<<POST_PH_POLICY<<"\",\"requested_tolerance\":{\"value\":"<<policy_json_number(eps)<<",\"unit\":\"A/m\"},\"achieved_A_Apm\":"<<(residual.valid?policy_json_number(residual.A):"null")<<",\"achieved_B_Apm\":"<<(residual.valid?policy_json_number(residual.B):"null")<<",\"stop_reason\":"<<policy_json_string(reason)<<",\"native_candidate\":"<<(reason=="residual_tolerance"?"true":"false")<<",\"status\":\""<<(reason=="residual_tolerance"?"unverified_candidate":"not_success")<<"\",\"independent_check\":\"not_checked\",\"local_updates\":"<<local<<",\"initial_global_updates\":"<<initial_global<<",\"global_updates\":"<<s.updates<<",\"field_calls\":"<<(model?model->dip.calls:0)<<",\"wall_s\":"<<policy_json_number(std::chrono::duration<double>(Clock::now()-start).count())<<",\"Ms_Apm\":["<<(model?policy_json_number(model->c.Ms[0]):"null")<<','<<(model?policy_json_number(model->c.Ms[1]):"null")<<"],\"external_H_Apm\":["<<policy_json_number(external.x)<<','<<policy_json_number(external.y)<<','<<policy_json_number(external.z)<<"],\"detail\":"<<policy_json_string(detail)<<"}\n";if(!f)throw std::runtime_error("native_result_output_failure");
  }
 }catch(const std::exception&x){std::cerr<<x.what()<<'\n';return 2;}
 return reason=="residual_tolerance"?0:2;
}

int policy_unit(){
 auto expect=[](bool b){if(!b)throw std::runtime_error("synthetic_policy_failure");};
 Spins m,H;m[0]={{0,0,1}};m[1]={{0,0,1}};H[0]={{1,0,2}};H[1]={{1,0,3}};std::array<double,2>ms={3e5,6e5};
 auto r=policy_residual(m,H,ms);expect(r.valid&&r.A==1&&r.B==1);expect(policy_decide(r,1,false,false,0,0,false)=="residual_tolerance");
 expect(policy_decide(r,1,true,false,0,0,false)=="wall_budget");expect(policy_decide(r,1,false,true,0,0,false)=="field_budget");
 H[1][0].x=std::nextafter(1.,2.);r=policy_residual(m,H,ms);expect(policy_decide(r,1,false,false,0,0,true)=="step_budget");
 H[0][0].x=2;H[1][0].x=.5;r=policy_residual(m,H,ms);expect(r.A>1&&r.B<1);
 H[0][0].x=.5;H[1][0].x=2;r=policy_residual(m,H,ms);expect(r.A<1&&r.B>1);
 // Pre-low/post-high and pre-high/post-low are synthetic current-state decisions.
 auto high=r;H[1][0].x=.5;auto low=policy_residual(m,H,ms);expect(policy_decide(high,1,false,false,1,1,true)=="step_budget");expect(policy_decide(low,1,false,false,1,1,false)=="residual_tolerance");
 for(double v:{0.,-1.,double(NAN),double(INFINITY)})expect(!valid_policy_tolerance(v));for(double v:{.5,1.,2.})expect(valid_policy_tolerance(v));
 std::ostringstream broken;broken.setstate(std::ios::badbit);std::string prior="residual_tolerance";try{if(!broken)throw std::runtime_error("synthetic history_output_failure");}catch(const std::exception&){prior=policy_exception_reason(prior,true);}expect(prior=="native_error");
 H[1][0].y=NAN;expect(!policy_residual(m,H,ms).valid);H[1][0].y=INFINITY;expect(!policy_residual(m,H,ms).valid);H[1][0].y=0;m[0][0].x=NAN;expect(!policy_residual(m,H,ms).valid);
 std::cout<<"{\"synthetic_only\":true,\"real_fields\":0,\"threshold_equality_AB_finiteness_post_and_budget_priority\":true}\n";return 0;
}
int policy_checkpoint_unit(const std::filesystem::path&p){bool legacy_rejected=false;try{(void)sd_restore(p);}catch(const std::exception&){legacy_rejected=true;}auto s=sd_restore(p,true);if(!legacy_rejected||s.updates<=10000)throw std::runtime_error("high_global_checkpoint_opt_in_test");std::cout<<"{\"real_fields\":0,\"legacy_high_global_rejected\":true,\"policy_opt_in_read\":true,\"global_updates\":"<<s.updates<<"}\n";return 0;}
