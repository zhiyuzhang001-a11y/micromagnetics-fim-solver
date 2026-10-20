#pragma once
#include <cstdint>
#include <climits>
#include <cstdlib>
#include <stdexcept>
#include <string>
#include <unistd.h>
#ifdef __APPLE__
#include <mach/mach.h>
#endif

namespace grid_capacity {
struct Layout { int px, py; std::uint64_t cells, real, complex, coefficients; };
inline Layout check(int nx,int ny,bool periodic,int mx=0,int my=0,bool fm=false) {
 if(nx<1||ny<1)throw std::runtime_error("grid capacity: positive XY counts required");
 std::int64_t x=nx,y=ny,px=periodic?x:2*x,py=periodic?y:2*y;
 auto fits=[](std::int64_t n){if(n<1||n>INT_MAX)throw std::runtime_error("grid capacity: signed 32-bit index/FFT/displacement overflow");};
 fits(x);fits(y);fits(px);fits(py);fits(x*y);fits(px*py);fits(py*(px/2+1));
 fits(periodic?(mx+1LL)*x-1:3*x-1);fits(periodic?(my+1LL)*y-1:3*y-1);
 if(fm){
  px=2;py=2;while(px<2*x-1)px*=2;while(py<2*y-1)py*=2;
  fits(px*py);fits((2*x-1)*(2*y-1));
 }
 return {int(px),int(py),std::uint64_t(x*y),std::uint64_t(px*py),std::uint64_t(py*(px/2+1)),std::uint64_t((2*x-1)*(2*y-1))};
}
inline std::uint64_t available() {
 std::uint64_t amount;
#ifdef __APPLE__
 vm_statistics_data_t s{};mach_msg_type_number_t n=HOST_VM_INFO_COUNT;vm_size_t page=0;
 auto host=mach_host_self();auto p=host_page_size(host,&page);
 auto status=host_statistics(host,HOST_VM_INFO,reinterpret_cast<host_info_t>(&s),&n);
 mach_port_deallocate(mach_task_self(),host);
 if(p!=KERN_SUCCESS||status!=KERN_SUCCESS)throw std::runtime_error("grid capacity: unable to query available memory");
 amount=(std::uint64_t(s.free_count)+s.inactive_count)*page;
#else
 auto pages=sysconf(_SC_AVPHYS_PAGES),page=sysconf(_SC_PAGESIZE);
 if(pages<=0||page<=0)throw std::runtime_error("grid capacity: unable to query available memory");
 amount=std::uint64_t(pages)*page;
#endif
 if(const char* value=std::getenv("FIMRUN_MEMORY_BUDGET_BYTES")) {
  std::string text(value);std::size_t used=0;unsigned long long limit=0;
  try{if(text.empty()||text[0]=='-')throw std::invalid_argument("budget");limit=std::stoull(text,&used);}catch(...){throw std::runtime_error("FIMRUN_MEMORY_BUDGET_BYTES must be a positive integer");}
  if(used!=text.size()||!limit)throw std::runtime_error("FIMRUN_MEMORY_BUDGET_BYTES must be a positive integer");
  if(limit<amount)amount=limit;
 }
 return amount;
}
inline void memory(std::uint64_t bytes,const char* operation) {
 auto limit=available();if(bytes>limit)throw std::runtime_error(std::string(operation)+": estimated working arrays "+std::to_string(bytes)+" bytes exceed available/configured budget "+std::to_string(limit)+" bytes");
}
inline std::uint64_t estimate(const Layout& p,bool fm=false) {
 return (fm?768:1536)*p.cells+(fm?288*p.real+48*p.coefficients:96*p.real+192*p.complex);
}
inline void model(const Layout& p,bool fm=false) {
 memory(estimate(p,fm),"grid capacity");
}
}
