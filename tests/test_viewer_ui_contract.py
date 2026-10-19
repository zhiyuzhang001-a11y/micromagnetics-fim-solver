import sys,unittest,time,threading
from pathlib import Path
from types import SimpleNamespace
from collections import OrderedDict
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from fimrun.micromagnetics.preview import LivePreview,PreviewRequestError,IDENTITY
from fimrun.micromagnetics.native import EVALUATIONS
class PreviewContract(unittest.TestCase):
 def source(self,n=200):
  p=LivePreview(SimpleNamespace(run_id='test-run'),0);identity={k:'fixture-'+k for k in IDENTITY};identity['run_id']='test-run';identity['instance']=p.instance
  m=np.zeros((2,1,n,n,3));m[0,...,2]=1;m[1,...,2]=-1
  packet={'identity':identity,'revision':1,'published':time.monotonic(),'state':{'phase':'initialized'},'frame':{'geometry':{'n':[n,n,1]},'labels':['A','B'],'configuration':{'snapshot':'accepted-only'},'config_sha256':'test'},'m':m}
  p.frames[1]=packet;p.latest=packet
  q={k:[str(v)] for k,v in identity.items()};q['step']=['1'];return p,q
 def test_capacity_has_distinct_status_and_retains_frame(self):
  p,q=self.source();q['stride']=['1']
  with self.assertRaises(PreviewRequestError) as ctx:p.response('/api/frame',q)
  self.assertEqual((ctx.exception.code,ctx.exception.status),('capacity_exceeded',422));self.assertEqual(list(p.frames),[1])
 def test_actual_counts_and_parameter_snapshot(self):
  p,q=self.source()
  for stride,count in [(2,10000),(4,2500),(8,625),(16,169)]:
   q['stride']=[str(stride)];frame,headers=p.response('/api/frame',q);self.assertEqual(len(frame['indices']),count);self.assertEqual(frame['configuration'],{'snapshot':'accepted-only'});self.assertEqual(headers['X-Boris-Frame-Seq'],'1')
  self.assertLessEqual(len(p.frame_cache),2)
 def test_supported_boundary_grid(self):
  p,q=self.source(256);q['stride']=['2'];frame,_=p.response('/api/frame',q);self.assertEqual(len(frame['indices']),16384)
  q['stride']=['1']
  with self.assertRaises(PreviewRequestError):p.response('/api/frame',q)
 def test_identity_is_still_enforced(self):
  p,q=self.source();q['config_sha256']=['other']
  with self.assertRaises(PreviewRequestError) as ctx:p.response('/api/frame',q)
  self.assertEqual(ctx.exception.code,'source_changed')
 def test_expired_history_distinct(self):
  p,q=self.source();q['step']=['0']
  with self.assertRaises(PreviewRequestError) as ctx:p.response('/api/frame',q)
  self.assertEqual(ctx.exception.code,'frame_expired')
 def test_invalid_density_is_not_identity_loss(self):
  p,q=self.source();q['stride']=['3']
  with self.assertRaises(PreviewRequestError) as ctx:p.response('/api/frame',q)
  self.assertEqual((ctx.exception.code,ctx.exception.status),('invalid_sampling',400))
 def test_2d_full_resolution_is_independent_of_3d_arrow_cap(self):
  p,q=self.source();q.update(stride=['1'],view=['2d']);frame,_=p.response('/api/frame',q)
  self.assertEqual(frame['view_mode'],'2d');self.assertEqual(len(frame['indices']),40000)
  self.assertEqual(len(frame['vectors'][0]),40000);self.assertEqual(frame['vectors'][0][0],[0.,0.,1.])
  q['view']=['3d']
  with self.assertRaises(PreviewRequestError) as ctx:p.response('/api/frame',q)
  self.assertEqual(ctx.exception.status,422)
 def test_2d_has_its_own_finite_pixel_budget(self):
  p,q=self.source(256);q.update(stride=['1'],view=['2d']);frame,_=p.response('/api/frame',q);self.assertEqual(len(frame['indices']),65536)
  p,q=self.source(257);q.update(stride=['1'],view=['2d'])
  with self.assertRaises(PreviewRequestError):p.response('/api/frame',q)
 def test_view_response_caches_do_not_mix_modes(self):
  p,q=self.source();q.update(stride=['2'],view=['3d']);a,_=p.response('/api/frame',q)
  q.update(stride=['1'],view=['2d']);b,_=p.response('/api/frame',q)
  self.assertEqual((a['view_mode'],b['view_mode']),('3d','2d'));self.assertEqual((len(a['indices']),len(b['indices'])),(10000,40000));self.assertLessEqual(len(p.frame_cache),2)
 def test_invalid_view_rejected(self):
  p,q=self.source();q.update(view=['other'])
  with self.assertRaises(PreviewRequestError) as ctx:p.response('/api/frame',q)
  self.assertEqual(ctx.exception.code,'invalid_view')
 def test_no_scientific_fields(self):self.assertEqual(sum(EVALUATIONS.values()),0)
if __name__=='__main__':unittest.main(verbosity=2)
