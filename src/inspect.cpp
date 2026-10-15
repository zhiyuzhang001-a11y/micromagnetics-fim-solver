// Packaging adapter: evaluate the unchanged model without advancing it.
#include "model.hpp"
int main(int argc,char**argv){try{
 if(argc!=4)throw std::runtime_error("CONFIG KERNEL NEW_OUTPUT");
 std::filesystem::path out=argv[3];if(std::filesystem::exists(out))throw std::runtime_error("no overwrite");
 Model model(read(argv[1]),argv[2],{0,0,-.002/mu0});auto e=model.eval(model.c.m);
 std::filesystem::create_directories(out);snapshot(out/"initial.bin",model.c.m);save_eval(out,"initial",e);return 0;
}catch(const std::exception&e){std::cerr<<e.what()<<'\n';return 2;}}
