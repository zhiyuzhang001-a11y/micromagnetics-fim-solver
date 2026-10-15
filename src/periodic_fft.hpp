#pragma once
#include <fftw3.h>
struct FFT {
 int nx,ny,n,nf;double* real;fftw_complex* complex;fftw_plan forward,inverse;
 FFT(int x,int y):nx(x),ny(y),n(x*y),nf(y*(x/2+1)){
  real=fftw_alloc_real(n);complex=fftw_alloc_complex(nf);if(!real||!complex)throw std::runtime_error("FFT allocation");
  forward=fftw_plan_dft_r2c_2d(ny,nx,real,complex,FFTW_ESTIMATE);inverse=fftw_plan_dft_c2r_2d(ny,nx,complex,real,FFTW_ESTIMATE);if(!forward||!inverse)throw std::runtime_error("FFT planning");
 }
 ~FFT(){fftw_destroy_plan(forward);fftw_destroy_plan(inverse);fftw_free(real);fftw_free(complex);}
 FFT(const FFT&)=delete;FFT&operator=(const FFT&)=delete;
 std::vector<std::array<double,2>>fwd(const std::vector<double>&v){if(int(v.size())!=n)throw std::runtime_error("FFT shape");std::copy(v.begin(),v.end(),real);fftw_execute(forward);std::vector<std::array<double,2>>s(nf);for(int i=0;i<nf;i++)s[i]={complex[i][0],complex[i][1]};return s;}
 std::vector<double>inv(const std::vector<std::array<double,2>>&s){for(int i=0;i<nf;i++){complex[i][0]=s[i][0];complex[i][1]=s[i][1];}fftw_execute(inverse);std::vector<double>v(n);for(int i=0;i<n;i++)v[i]=real[i]/n;return v;}
};
