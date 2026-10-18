// GPL-3.0-only. The genuine one-field FM model, independent of frozen SP4 CLI guards.
#define SCRIPT_API_GENERAL_GEOMETRY 1
#define SCRIPT_API_TRACE 1
#include "../../validation/fm/fm.hpp"
#include <cstring>
static thread_local std::string script_error;
struct ScriptModel{Model model;unsigned long fft_calls=0;explicit ScriptModel(Config c):model(std::move(c)){} };
extern "C" {
const char* mm_error(){return script_error.c_str();}
void* mm_create(const char*config,const char*){try{return new ScriptModel(read_config(config));}catch(const std::exception&e){script_error=e.what();return nullptr;}}
void mm_destroy(void*p){delete static_cast<ScriptModel*>(p);}
int mm_eval(void*p,const double*m,double*H,double*parts){try{
 auto*model=static_cast<ScriptModel*>(p);State s;s[0].resize(model->model.c.count());std::memcpy(s[0].data(),m,s[0].size()*sizeof(V));auto e=model->model.eval(s);std::memcpy(H,e.H[0].data(),s[0].size()*sizeof(V));for(int k=0;k<7;k++)parts[k]=k<4?e.parts[k]:0;if(model->model.dip)model->fft_calls+=6;return 0;
 }catch(const std::exception&e){script_error=e.what();return 1;}}
int mm_rhs(void*p,const double*m,const double*H,const double*,double*out,double*power_out){try{
 auto*model=static_cast<ScriptModel*>(p);State s;Evaluation e;s[0].resize(model->model.c.count());e.H[0].resize(s[0].size());std::memcpy(s[0].data(),m,s[0].size()*sizeof(V));std::memcpy(e.H[0].data(),H,s[0].size()*sizeof(V));auto k=model->model.rhs(s,e);std::memcpy(out,k[0].data(),s[0].size()*sizeof(V));power_out[0]=model->model.loss(s,e)[0];power_out[1]=power_out[2]=power_out[3]=0;return 0;
 }catch(const std::exception&e){script_error=e.what();return 1;}}
unsigned long mm_calls(void*p){return static_cast<ScriptModel*>(p)->model.calls;}
unsigned long mm_fft_calls(void*p){return static_cast<ScriptModel*>(p)->fft_calls;}
int mm_subfields(void*){return 1;}
unsigned long mm_local_calls(void*p,int term){return static_cast<ScriptModel*>(p)->model.script_calls.at(term);}
}
