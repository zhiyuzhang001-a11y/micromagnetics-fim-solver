#pragma once
#include <CommonCrypto/CommonDigest.h>
#include <sstream>
inline std::string file_sha256(const std::filesystem::path&p){std::ifstream f(p,std::ios::binary);if(!f)throw std::runtime_error("kernel file open");std::vector<unsigned char>bytes((std::istreambuf_iterator<char>(f)),{});unsigned char d[CC_SHA256_DIGEST_LENGTH];CC_SHA256(bytes.data(),static_cast<CC_LONG>(bytes.size()),d);std::ostringstream o;o<<std::hex<<std::setfill('0');for(auto x:d)o<<std::setw(2)<<int(x);return o.str();}

#include <Accelerate/Accelerate.h>
#include <array>
#include <vector>
#include <cmath>

// Mathematical Newell primitives, implemented independently from the cited equations.
// No OOMMF or BORIS routines are linked/copied into this kernel.
double newell_f(double x,double y,double z){
    x=std::abs(x);y=std::abs(y);z=std::abs(z);double R=std::sqrt(x*x+y*y+z*z);
    if(R==0)return 0;
    double out=(2*x*x-y*y-z*z)*R/6;
    if(x*x+z*z>0)out+=y*(z*z-x*x)*std::asinh(y/std::sqrt(x*x+z*z))/2;
    if(x*x+y*y>0)out+=z*(y*y-x*x)*std::asinh(z/std::sqrt(x*x+y*y))/2;
    if(x>0)out-=x*y*z*std::atan(y*z/(x*R));
    return out;
}
double newell_g(double x,double y,double z){
    if(x==0||y==0)return 0;
    double sign=(x<0?-1.:1.)*(y<0?-1.:1.);x=std::abs(x);y=std::abs(y);z=std::abs(z);
    double R=std::sqrt(x*x+y*y+z*z);
    double out=-x*y*R/3;
    out+=x*y*z*std::asinh(z/std::sqrt(x*x+y*y));
    out+=y*(3*z*z-y*y)*std::asinh(x/std::sqrt(y*y+z*z))/6;
    out+=x*(3*z*z-x*x)*std::asinh(y/std::sqrt(x*x+z*z))/6;
    if(z>0)out-=z*z*z*std::atan(x*y/(z*R))/6;
    out-=y*y*z*std::atan(x*z/(y*R))/2;
    out-=x*x*z*std::atan(y*z/(x*R))/2;
    return sign*out;
}
using Tensor=std::array<double,6>; // xx yy zz xy xz yz
Tensor tensor_at(std::array<double,3> h,std::array<double,3> r){
    double scale=std::max({h[0],h[1],h[2]});
    if(!std::isfinite(scale)||scale<=0)throw std::runtime_error("invalid cell shape");
    for(int a=0;a<3;a++){if(h[a]<=0||!std::isfinite(h[a])||!std::isfinite(r[a]))throw std::runtime_error("invalid tensor point");h[a]/=scale;r[a]/=scale;}
    Tensor sums{},comp{};
    auto add=[&](int a,double value){double t=sums[a]+value;if(std::abs(sums[a])>=std::abs(value))comp[a]+=(sums[a]-t)+value;else comp[a]+=(value-t)+sums[a];sums[a]=t;};
    const int weights[3]={-1,2,-1};
    for(int i=-1;i<=1;i++)for(int j=-1;j<=1;j++)for(int k=-1;k<=1;k++){
        double x=r[0]+i*h[0],y=r[1]+j*h[1],z=r[2]+k*h[2];double w=weights[i+1]*weights[j+1]*weights[k+1];
        add(0,w*newell_f(x,y,z));add(1,w*newell_f(y,x,z));add(2,w*newell_f(z,x,y));
        add(3,w*newell_g(x,y,z));add(4,w*newell_g(x,z,y));add(5,w*newell_g(y,z,x));
    }
    double denominator=4*std::acos(-1.)*h[0]*h[1]*h[2];
    for(int a=0;a<6;a++)sums[a]=(sums[a]+comp[a])/denominator;
    // These off-diagonal values are mathematically zero by exact reflection symmetry.
    if(r[0]==0||r[1]==0)sums[3]=0;
    if(r[0]==0||r[2]==0)sums[4]=0;
    if(r[1]==0||r[2]==0)sums[5]=0;
    return sums;
}
struct ComplexGrid {std::vector<double> r,i;ComplexGrid()=default;explicit ComplexGrid(int n):r(n),i(n){};};
int nextpow(int n){int p=2;while(p<n)p*=2;return p;}
int logpow(int n){int p=0;while((1<<p)<n)p++;return p;}
class Demag {
public:
    int nx,ny,px,py;
    std::array<double,3> h;
    std::vector<Tensor> coefficients;
    std::array<ComplexGrid,6> kernel;
    FFTSetupD setup;
    unsigned long calls=0;
    Demag(int x,int y,std::array<double,3>hh):Demag(x,y,hh,"",""){}
    Demag(int x,int y,std::array<double,3> hh,const std::filesystem::path&path,const std::string&expected):nx(x),ny(y),px(nextpow(2*x-1)),py(nextpow(2*y-1)),h(hh){
        if(path.empty()){if(x<1||y<1||x>8||y>4)throw std::runtime_error("legacy small grid limit");}else if(!((x==100&&y==25)||(x==200&&y==50)||(x==4&&y==3)))throw std::runtime_error("frozen D0 loaded-kernel geometry only");
        setup=vDSP_create_fftsetupD(std::max(logpow(px),logpow(py)),kFFTRadix2);if(!setup)throw std::runtime_error("Accelerate FFT setup failed");
        coefficients.resize((2*nx-1)*(2*ny-1));if(!path.empty()){if(file_sha256(path)!=expected)throw std::runtime_error("qualified kernel sha mismatch");std::ifstream f(path,std::ios::binary);char magic[8];int xx,yy;std::array<double,3>shape;f.read(magic,8);f.read((char*)&xx,4);f.read((char*)&yy,4);f.read((char*)shape.data(),24);if(std::string(magic,6)!="OPENv2"||xx!=nx||yy!=ny||shape!=h)throw std::runtime_error("kernel header geometry");f.read((char*)coefficients.data(),coefficients.size()*sizeof(Tensor));if(!f||f.peek()!=EOF)throw std::runtime_error("kernel payload size");for(auto t:coefficients)for(double v:t)if(!std::isfinite(v))throw std::runtime_error("kernel nonfinite");}std::array<ComplexGrid,6> real;
        for(auto&v:real)v=ComplexGrid(px*py);
        for(int dy=1-ny;dy<ny;dy++)for(int dx=1-nx;dx<nx;dx++){
            auto index=(dx+nx-1)+(dy+ny-1)*(2*nx-1);Tensor t=path.empty()?tensor_at(h,{dx*h[0],dy*h[1],0.}):coefficients[index];coefficients[index]=t;
            int ix=(dx+px)%px,iy=(dy+py)%py;
            for(int a=0;a<6;a++)real[a].r[ix+iy*px]=-t[a];
        }
        for(int a=0;a<6;a++)kernel[a]=fft(real[a],FFT_FORWARD);
    }
    ~Demag(){vDSP_destroy_fftsetupD(setup);}
    Demag(const Demag&)=delete;Demag&operator=(const Demag&)=delete;
    ComplexGrid fft(const ComplexGrid&in,FFTDirection direction){
        ComplexGrid out(px*py);DSPDoubleSplitComplex a{const_cast<double*>(in.r.data()),const_cast<double*>(in.i.data())},b{out.r.data(),out.i.data()};
        vDSP_fft2d_zopD(setup,&a,1,px,&b,1,px,logpow(px),logpow(py),direction);return out;
    }
    std::vector<V> field(const std::vector<V>&magnetization){
        calls++;std::array<ComplexGrid,3> source,spectrum,out;
        for(auto&v:source)v=ComplexGrid(px*py);
        for(int y=0;y<ny;y++)for(int x=0;x<nx;x++)for(int a=0;a<3;a++)source[a].r[x+y*px]=magnetization[x+y*nx][a];
        for(int a=0;a<3;a++){spectrum[a]=fft(source[a],FFT_FORWARD);out[a]=ComplexGrid(px*py);}
        int lookup[3][3]={{0,3,4},{3,1,5},{4,5,2}};
        for(int p=0;p<px*py;p++)for(int a=0;a<3;a++)for(int b=0;b<3;b++){
            auto&k=kernel[lookup[a][b]];out[a].r[p]+=k.r[p]*spectrum[b].r[p]-k.i[p]*spectrum[b].i[p];
            out[a].i[p]+=k.r[p]*spectrum[b].i[p]+k.i[p]*spectrum[b].r[p];
        }
        std::array<ComplexGrid,3> inverse;for(int a=0;a<3;a++)inverse[a]=fft(out[a],FFT_INVERSE);
        std::vector<V> result(nx*ny);for(int y=0;y<ny;y++)for(int x=0;x<nx;x++)for(int a=0;a<3;a++)result[x+y*nx][a]=inverse[a].r[x+y*px]/(px*py);
        return result;
    }
};
