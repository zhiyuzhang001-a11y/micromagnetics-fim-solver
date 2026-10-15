"""Bounded packaging checks, not historical scientific validation."""
from pathlib import Path
import argparse,subprocess,sys,json,time,hashlib,numpy as np
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'))
from make_fixture import make
from check_residual import check
def run(bins,work,cap=25):
 start=time.monotonic();work=Path(work);work.mkdir(exist_ok=False);bins=Path(bins).resolve();kernel=ROOT/'examples/kernel125-mirror10.f64';records=[]
 def call(name,args,expected=0):
  t=time.monotonic();r=subprocess.run([str(bins/name),*map(str,args)],capture_output=True,text=True,timeout=max(.1,cap-(time.monotonic()-start)))
  records.append({'target':name,'returncode':r.returncode,'elapsed_s':time.monotonic()-t});(work/'calls.json').write_text(json.dumps(records,indent=2)+'\n')
  if r.returncode!=expected:raise RuntimeError(r.stderr)
  return r
 make(work/'fixture','smooth');cfg=work/'fixture/config.dat';seed=work/'fixture/seed.f64'
 call('fim_inspect',[cfg,kernel,work/'inspect']);E=json.loads((work/'inspect/initial_energy.json').read_text())['total_J'];assert E!=0
 assert seed.read_bytes()==(work/'inspect/initial.bin').read_bytes()
 call('fim_dynamic',[cfg,kernel,work/'dyn1','12.5','-',0,.0125,E,0]);s1=json.loads((work/'dyn1/summary.json').read_text())
 call('fim_dynamic',[cfg,kernel,work/'dyn2','12.5',work/'dyn1/final.bin',.0125,.025,E,s1['cumulative_rk_dissipated_J']]);s2=json.loads((work/'dyn2/summary.json').read_text())
 call('fim_dynamic',[cfg,kernel,work/'continuous','12.5','-',0,.025,E,0]);sc=json.loads((work/'continuous/summary.json').read_text())
 assert (work/'dyn2/final.bin').read_bytes()==(work/'continuous/final.bin').read_bytes()
 assert s1['cumulative_rk_dissipated_J']>0
 assert s2['energy_original_J']==E and s2['loss_before_J']==s1['cumulative_rk_dissipated_J'] and s2['cumulative_rk_dissipated_J']==sc['cumulative_rk_dissipated_J']
 call('fim_static',[cfg,kernel,work/'dyn2/final.bin',work/'seam-test','test','-',10])
 # The existing 15-update native restore test advances from the real dynamic endpoint.
 assert (work/'seam-test/full10.bin').read_bytes()==(work/'seam-test/resumed10.bin').read_bytes()
 dyn_res=check(work/'dyn2',kernel,cfg);assert dyn_res['field_consistent_1e_minus10'] and dyn_res['history_consistent_1e_minus6_Apm']
 # Uniform AP fixture makes the actual unmodified SDesc run stop quickly. No cap changes.
 make(work/'uniform');ucfg=work/'uniform/config.dat'
 call('fim_inspect',[ucfg,kernel,work/'uniform-inspect']);ue=json.loads((work/'uniform-inspect/initial_energy.json').read_text())['total_J']
 call('fim_dynamic',[ucfg,kernel,work/'uniform-dyn','12.5','-',0,.0125,ue,0])
 call('fim_static',[ucfg,kernel,work/'uniform-dyn/final.bin',work/'static','run','-',10])
 assert (work/'uniform-dyn/final.bin').read_bytes()==(work/'static/initial.bin').read_bytes()
 assert json.loads((work/'uniform-dyn/final_energy.json').read_text())==json.loads((work/'static/initial_energy.json').read_text())
 ds=json.loads((work/'uniform-dyn/summary.json').read_text())
 identity=lambda f:hashlib.sha256(Path(f).read_bytes()).hexdigest()
 handoff={'config_sha256':identity(ucfg),'kernel_sha256':identity(kernel),'dynamic_final_sha256':identity(work/'uniform-dyn/final.bin'),'static_initial_sha256':identity(work/'static/initial.bin'),'dynamic_original_energy_J':ds['energy_original_J'],'dynamic_final_energy_J':ds['energy_final_J'],'dynamic_cumulative_loss_J':ds['cumulative_rk_dissipated_J'],'dynamic_reached_physical_time_ps':ds['reached_time_ps'],'static_fresh_prime':True,'static_aux_is_physical_time':False,'state_storage':'native-endian binary64, A then B, x fastest'}
 (work/'handoff.json').write_text(json.dumps(handoff,indent=2)+'\n')
 stat_res=check(work/'static',kernel,ucfg);assert stat_res['field_consistent_1e_minus10'] and stat_res['history_consistent_1e_minus6_Apm']
 call('fim_static',[ucfg,kernel,work/'uniform-dyn/final.bin',work/'static-resume','resume_test',work/'static/checkpoint.bin',10])
 for name in ['fim_dynamic','fim_static','fim_inspect','label_prefix','d0_reference','fm_d1ns']:
  if (bins/name).exists():call(name,[],2)
 def reader_cli(directory,config,expected):
  result=subprocess.run([sys.executable,str(ROOT/'tools/check_residual.py'),str(directory),str(kernel),str(config)],capture_output=True,text=True,timeout=max(.1,cap-(time.monotonic()-start)))
  assert result.returncode==expected,(result.returncode,result.stderr)
 reader_cli(work/'static',ucfg,0)
 # Real native A-pre stop with residuals exceeding the external both<=1 condition.
 make(work/'near-stop','near-stop');ncfg=work/'near-stop/config.dat'
 call('fim_static',[ncfg,kernel,work/'near-stop/seed.f64',work/'near-static','run','-',10])
 near=check(work/'near-static',kernel,ncfg)
 assert near['internal_status']=='BORIS_A_pre_mxh_single_schedule_stop' and not near['external_acceptance_passed'] and near['A_B_projected_Apm'][0]<=1 and near['A_B_projected_Apm'][1]>1
 reader_cli(work/'near-static',ncfg,1)
 # Corrupt saved field and history separately; independent acceptance must reject both.
 hf=work/'static/final_H_B.bin';original=hf.read_bytes();v=np.frombuffer(original,dtype='=f8').copy();v[0]+=2.;hf.write_bytes(v.tobytes())
 corruptH=check(work/'static',kernel,ucfg);reader_cli(work/'static',ucfg,1);hf.write_bytes(original)
 assert not corruptH['field_consistent_1e_minus10'] and not corruptH['external_acceptance_passed']
 hp=work/'static/history.csv';original_text=hp.read_text();lines=original_text.splitlines();header=lines[0].split(',');last=lines[-1].split(',');last[header.index('post_B_Apm')]='2';lines[-1]=','.join(last);hp.write_text('\n'.join(lines)+'\n')
 corruptHist=check(work/'static',kernel,ucfg);reader_cli(work/'static',ucfg,1);hp.write_text(original_text)
 assert not corruptHist['history_consistent_1e_minus6_Apm'] and not corruptHist['external_acceptance_passed']
 assert stat_res['external_acceptance_passed']
 return {'scope':'packaging-only compatibility; not long-run science','smooth_RK4_updates':4,'uniform_RK4_updates':1,'sdesc_test_updates':15,'static_summary':json.loads((work/'static/summary.json').read_text()),
 'dynamic_restore_state_exact':True,'dynamic_loss_bookkeeping_exact':True,'dynamic_final_to_static_initial_state_and_energy_exact':True,'static_checkpoint_restore_exact':True,
 'dynamic_residual_check':dyn_res,'static_residual_check':stat_res,'native_stop_but_external_not_accepted':near,'corrupt_saved_field_rejected':True,'corrupt_history_rejected':True,'elapsed_s':time.monotonic()-start,'calls':records}
if __name__=='__main__':
 a=argparse.ArgumentParser();a.add_argument('--bins',type=Path,default=ROOT/'build');a.add_argument('--work',type=Path,required=True);a.add_argument('--cap',type=float,default=25);x=a.parse_args();result=run(x.bins,x.work,x.cap);(x.work/'smoke.json').write_text(json.dumps(result,indent=2,allow_nan=False)+'\n');print(json.dumps(result,indent=2))
