#pragma once
// Enabled by LF_TWO_OWNER; supported builds enable this backend by default.
// Reference evaluate() and parts diagnostics stay intact.
#include <condition_variable>
#include <cstdint>
#include <cstdlib>
#include <exception>
#include <memory>
#include <mutex>
#include <thread>

// Main owns H_A and every E/Ecross +=. Keep the reference j/d/module/i order,
// including onsite terms before later-j periodic scatter back into the same cell.
inline void local_main_A_energy(const C& c,Field& out){
    std::array<std::size_t,3> stride={1,static_cast<std::size_t>(c.n[0]),static_cast<std::size_t>(c.n[0]*c.n[1])};
    for(std::size_t j=0;j<c.count;j++){
        std::array<int,3> pos={static_cast<int>(j%c.n[0]),static_cast<int>((j/c.n[0])%c.n[1]),static_cast<int>(j/(c.n[0]*c.n[1]))};
        for(int d=0;d<3;d++){
            if(c.n[d]==1)continue;
            std::size_t other;
            if(pos[d]+1<c.n[d])other=j+stride[d];
            else if(c.pbc[d])other=j-(c.n[d]-1)*stride[d];
            else continue;
            if(c.active[0]){
                V da=c.m[0][other]-c.m[0][j],db=c.m[1][other]-c.m[1][j];
                double e=.5*c.volume*c.Anh*dot(da,db)/(c.h[d]*c.h[d]);out.E[0]+=e;out.Ecross+=e;
                for(int i=0;i<1;i++){
                    V value=(i==0?db:da)*(c.Anh/(mu0*c.Ms[i]*c.h[d]*c.h[d]));
                    out.H[i][j]+=value;out.H[i][other]+=value*(-1);
                }
            }
            for(int i=0;i<2;i++){
                V q=c.m[i][j],r=c.m[i][other],difference=r-q;
                if(c.active[0]){
                    out.E[0]+=.5*c.volume*c.A[i]*dot(difference,difference)/(c.h[d]*c.h[d]);
                    if(i==0){
                        V value=difference*(2*c.A[i]/(mu0*c.Ms[i]*c.h[d]*c.h[d]));
                        out.H[i][j]+=value;out.H[i][other]+=value*(-1);
                    }
                }
                if(d<2&&c.active[2]){
                    out.E[2]+=.5*c.volume*c.D[i]*(q[d]*r.z-q.z*r[d])/c.h[d];
                    if(i==0){
                        double k=c.D[i]/(mu0*c.Ms[i]*c.h[d]);
                        out.H[i][j][d]-=k*r.z;out.H[i][j].z+=k*r[d];
                        out.H[i][other][d]+=k*q.z;out.H[i][other].z-=k*q[d];
                    }
                }
            }
        }
        if(c.active[1]){
            out.E[1]+=-2*c.Ah*c.volume*dot(c.m[0][j],c.m[1][j]);
            for(int i=0;i<1;i++){V value=c.m[1-i][j]*(4*c.Ah/(mu0*c.Ms[i]));out.H[i][j]+=value;}
        }
        if(c.active[3])for(int i=0;i<2;i++){
            double u=dot(c.m[i][j],easy_axis(c,i)),s=1-u*u;
            out.E[3]+=.5*c.volume*(c.K1[i]*s+c.K2[i]*s*s);
            if(i==0){V value=easy_axis(c,i)*(2*u*(c.K1[i]+2*c.K2[i]*s)/(mu0*c.Ms[i]));out.H[i][j]+=value;}
        }
    }
}

// Worker reads the same coupled immutable c.m[A/B], but only writes H_B.
// Each B component sees exactly its original scatter/onsite addition sequence.
inline void local_worker_B_field(const C& c,Field& out){
    std::array<std::size_t,3> stride={1,static_cast<std::size_t>(c.n[0]),static_cast<std::size_t>(c.n[0]*c.n[1])};
    for(std::size_t j=0;j<c.count;j++){
        std::array<int,3> pos={static_cast<int>(j%c.n[0]),static_cast<int>((j/c.n[0])%c.n[1]),static_cast<int>(j/(c.n[0]*c.n[1]))};
        for(int d=0;d<3;d++){
            if(c.n[d]==1)continue;
            std::size_t other;
            if(pos[d]+1<c.n[d])other=j+stride[d];
            else if(c.pbc[d])other=j-(c.n[d]-1)*stride[d];
            else continue;
            if(c.active[0]){
                V da=c.m[0][other]-c.m[0][j],db=c.m[1][other]-c.m[1][j];
                for(int i=1;i<2;i++){
                    V value=(i==0?db:da)*(c.Anh/(mu0*c.Ms[i]*c.h[d]*c.h[d]));
                    out.H[i][j]+=value;out.H[i][other]+=value*(-1);
                }
            }
            for(int i=1;i<2;i++){
                V q=c.m[i][j],r=c.m[i][other],difference=r-q;
                if(c.active[0]){
                    V value=difference*(2*c.A[i]/(mu0*c.Ms[i]*c.h[d]*c.h[d]));
                    out.H[i][j]+=value;out.H[i][other]+=value*(-1);
                }
                if(d<2&&c.active[2]){
                    double k=c.D[i]/(mu0*c.Ms[i]*c.h[d]);
                    out.H[i][j][d]-=k*r.z;out.H[i][j].z+=k*r[d];
                    out.H[i][other][d]+=k*q.z;out.H[i][other].z-=k*q[d];
                }
            }
        }
        if(c.active[1]){
            for(int i=1;i<2;i++){V value=c.m[1-i][j]*(4*c.Ah/(mu0*c.Ms[i]));out.H[i][j]+=value;}
        }
        if(c.active[3])for(int i=1;i<2;i++){
            double u=dot(c.m[i][j],easy_axis(c,i)),s=1-u*u;
            V value=easy_axis(c,i)*(2*u*(c.K1[i]+2*c.K2[i]*s)/(mu0*c.Ms[i]));out.H[i][j]+=value;
        }
    }
}

#ifdef LF_TEST_HOOKS
inline void (*lf_main_hook)()=nullptr;
inline void (*lf_worker_hook)()=nullptr;
#endif
class LocalFieldTeam {
    // Lock order: whole-model call mutex -> job mutex. Worker only uses job mutex.
    std::mutex model_call_,job_mutex_;
    std::condition_variable work_ready_,job_done_;
    bool stop_=false;
    std::uint64_t generation_=0,completed_=0;
    const C* input_=nullptr;
    Field* output_=nullptr;
    std::exception_ptr worker_error_;
#ifdef LF_LOCAL_PROFILE
    // Main-only counters and worker-only counters are read together after join.
    std::uint64_t main_jobs_=0,worker_jobs_=0;
    double team_seconds_=0,main_seconds_=0,wait_seconds_=0,worker_seconds_=0,construct_seconds_=0;
#endif
    std::thread worker_;
    void worker_loop() noexcept {
        std::unique_lock<std::mutex> lock(job_mutex_);
        std::uint64_t seen=0;
        for(;;){
            work_ready_.wait(lock,[&]{return stop_||generation_!=seen;});
            if(stop_&&generation_==seen)return;
            const auto job=generation_;
            const C* c=input_;Field* out=output_;
            lock.unlock();
            std::exception_ptr error;
#ifdef LF_LOCAL_PROFILE
            const auto begin=Clock::now();
#endif
            try{
#ifdef LF_TEST_HOOKS
                if(lf_worker_hook)lf_worker_hook();
#endif
                local_worker_B_field(*c,*out);}catch(...){error=std::current_exception();}
#ifdef LF_LOCAL_PROFILE
            worker_seconds_+=std::chrono::duration<double>(Clock::now()-begin).count();worker_jobs_++;
#endif
            lock.lock();
            worker_error_=error;completed_=job;seen=job;input_=nullptr;output_=nullptr;
            job_done_.notify_all();
        }
    }
    std::uint64_t publish(const C& c,Field& out){
        std::lock_guard<std::mutex> lock(job_mutex_);
        if(stop_||generation_!=completed_||generation_==UINT64_MAX)throw std::logic_error("invalid local-field job state");
        input_=&c;output_=&out;worker_error_=nullptr;const auto job=++generation_;
        work_ready_.notify_one();return job;
    }
    std::exception_ptr drain(std::uint64_t job) noexcept {
        // Never release cc/out while a worker could still use them. A fundamental
        // synchronization failure terminates, rather than returning dangling data.
        std::unique_lock<std::mutex> lock(job_mutex_);
        job_done_.wait(lock,[&]{return completed_==job;});return worker_error_;
    }
public:
    LocalFieldTeam(){
#ifdef LF_LOCAL_PROFILE
        const auto begin=Clock::now();
#endif
        worker_=std::thread([this]{worker_loop();});
#ifdef LF_LOCAL_PROFILE
        construct_seconds_=std::chrono::duration<double>(Clock::now()-begin).count();
#endif
    }
    LocalFieldTeam(const LocalFieldTeam&)=delete;
    LocalFieldTeam& operator=(const LocalFieldTeam&)=delete;
    LocalFieldTeam(LocalFieldTeam&&)=delete;
    LocalFieldTeam& operator=(LocalFieldTeam&&)=delete;
    std::mutex& model_call_mutex() noexcept{return model_call_;}
    Field evaluate_owned(const C& c){
#ifdef LF_LOCAL_PROFILE
        const auto team_begin=Clock::now();
#endif
        Field out;for(auto&v:out.H)v.resize(c.count); // Both zero allocations precede publication.
        const auto job=publish(c,out);
        std::exception_ptr main_error;
#ifdef LF_LOCAL_PROFILE
        const auto main_begin=Clock::now();
#endif
        try{
#ifdef LF_TEST_HOOKS
            if(lf_main_hook)lf_main_hook();
#endif
            local_main_A_energy(c,out);}catch(...){main_error=std::current_exception();}
#ifdef LF_LOCAL_PROFILE
        main_seconds_+=std::chrono::duration<double>(Clock::now()-main_begin).count();
        const auto wait_begin=Clock::now();
#endif
        const auto worker_error=drain(job); // Always drain, including main exception paths.
#ifdef LF_LOCAL_PROFILE
        wait_seconds_+=std::chrono::duration<double>(Clock::now()-wait_begin).count();
#endif
        if(main_error)std::rethrow_exception(main_error);
        if(worker_error)std::rethrow_exception(worker_error);
        for(double e:out.E)if(!std::isfinite(e))throw std::runtime_error("nonfinite energy");
        for(auto&v:out.H)for(auto h:v)if(!finite(h))throw std::runtime_error("nonfinite field");
#ifdef LF_LOCAL_PROFILE
        main_jobs_++;team_seconds_+=std::chrono::duration<double>(Clock::now()-team_begin).count();
#endif
        return out;
    }
    ~LocalFieldTeam() noexcept {
        std::lock_guard<std::mutex> model_lock(model_call_);
#ifdef LF_LOCAL_PROFILE
        const auto join_begin=Clock::now();
#endif
        {std::lock_guard<std::mutex> lock(job_mutex_);stop_=true;}
        work_ready_.notify_one();
        if(worker_.joinable())worker_.join();
#ifdef LF_LOCAL_PROFILE
        const double shutdown=std::chrono::duration<double>(Clock::now()-join_begin).count();
        if(const char* path=std::getenv("LF_PROFILE_OUTPUT")){
            std::ofstream file(path);
            file<<std::setprecision(17)<<"{\"instrumented_only\":true,\"local_jobs\":"<<main_jobs_
                <<",\"worker_jobs\":"<<worker_jobs_<<",\"team_local_wall_s\":"<<team_seconds_
                <<",\"main_A_energy_s\":"<<main_seconds_<<",\"worker_HB_s\":"<<worker_seconds_
                <<",\"main_wait_s\":"<<wait_seconds_<<",\"construct_worker_s\":"<<construct_seconds_
                <<",\"shutdown_join_s\":"<<shutdown<<",\"overlapping_parts_not_additive\":true}\n";
            if(!file)std::cerr<<"local profile output failed\n";
        }
#endif
    }
};
