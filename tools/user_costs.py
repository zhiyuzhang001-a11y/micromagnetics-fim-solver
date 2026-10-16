"""Append-only resource costs outside rollbackable checkpoints (POSIX file locking).
An unfinished native reservation stays charged at its conservative upper bound.
Legacy import covers the source run's recorded cumulative cost, not undiscovered
pre-ledger branches; those remain in the separate acceptance/campaign account.
"""
from pathlib import Path
import fcntl,json,os,time,uuid

def read_events(stream):
 stream.seek(0);events=[];previous=''
 import hashlib
 for line in stream:
  try:event=json.loads(line)
  except json.JSONDecodeError:raise ValueError('resource ledger incomplete record; inspect and reconcile, never reset')
  signature=event.pop('sha256',None)
  expected=hashlib.sha256(json.dumps(event,sort_keys=True,separators=(',',':')).encode()).hexdigest()
  if signature!=expected or event.get('previous')!=previous:raise ValueError('resource ledger checksum/order mismatch')
  event['sha256']=signature;events.append(event);previous=signature
 return events

def total(events):
 value=0;reservations={}
 for e in events:
  if e['kind']=='legacy_import':value+=e['fields']
  elif e['kind']=='reserve':reservations[e['reservation']]=e['fields']
  elif e['kind']=='settle':
   if e['reservation'] not in reservations:raise ValueError('resource ledger unknown reservation')
   if not 0<=e['fields']<=reservations.pop(e['reservation']):raise ValueError('resource ledger invalid settlement')
   value+=e['fields']
 return value+sum(reservations.values())

def inspect_ledger(path):
 with Path(path).open(encoding='utf-8') as stream:
  fcntl.flock(stream,fcntl.LOCK_SH)
  events=read_events(stream)
  if not events:raise ValueError('empty resource ledger; restore recorded costs, cannot reset')
  return total(events)

def legacy_source_cost(resume):
 source=Path(resume['_metadata_path']).resolve().parent.parent
 report=source/'report.json'
 if not report.is_file():raise ValueError('legacy resource migration needs source report.json; restore recorded costs, cannot use checkpoint snapshot alone')
 value=json.loads(report.read_text()).get('started_fields')
 if isinstance(value,bool) or not isinstance(value,int) or value<0:raise ValueError('invalid source recorded resource cost')
 return source,max(int(resume['spent_fields']),value)

class ResourceCosts:
 def __init__(self,out,resume):
  self.run_id=uuid.uuid4().hex
  if resume and resume.get('resource_ledger'):
   self.path=Path(resume['resource_ledger']);self.seed=0
   if not self.path.is_file():raise ValueError('resource ledger missing; recover external ledger, cannot reset costs')
   self.legacy_note=None
  elif resume:
   source,self.seed=legacy_source_cost(resume)
   self.path=source.with_name(source.name+'.resource-costs.jsonl')
   if self.seed<0:raise ValueError('negative legacy resource cost')
   self.legacy_note='Legacy import uses max(checkpoint cost, source run recorded total). Pre-ledger branches outside that run remain in the campaign account; no claim of discovering all historical branches.'
  else:
   self.path=Path(out).with_name(Path(out).name+'.resource-costs.jsonl');self.seed=0;self.legacy_note=None
  self.path.parent.mkdir(parents=True,exist_ok=True)
  if self.path.exists():
   recorded=inspect_ledger(self.path)
   if resume and recorded<int(resume.get('spent_fields',0)):raise ValueError('resource ledger predates checkpoint recorded costs')
  self._transaction(lambda events: None if events else {'kind':'legacy_import','fields':self.seed,'note':self.legacy_note or 'new resource lineage'},initialize=True)
 def _transaction(self,make,initialize=False):
  import hashlib
  with self.path.open('a+',encoding='utf-8') as stream:
   fcntl.flock(stream,fcntl.LOCK_EX)
   events=read_events(stream)
   if not events and not initialize:raise ValueError('empty resource ledger; cannot reset costs')
   event=make(events)
   if event is not None:
    event={**event,'run_id':self.run_id,'unix_s':time.time(),'previous':events[-1]['sha256'] if events else ''}
    event['sha256']=hashlib.sha256(json.dumps(event,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    stream.seek(0,2);stream.write(json.dumps(event,ensure_ascii=False)+'\n');stream.flush();os.fsync(stream.fileno());events.append(event)
   return total(events)
 def total(self):return self._transaction(lambda events:None)
 def reserve(self,fields,cap,label):
  token=uuid.uuid4().hex
  def event(events):
   if fields<1 or total(events)+fields>cap:raise RuntimeError('field_budget_exhausted: external resource ledger')
   return {'kind':'reserve','reservation':token,'fields':fields,'label':label}
  self._transaction(event);return token
 def settle(self,token,fields):return self._transaction(lambda events:{'kind':'settle','reservation':token,'fields':fields})

 def record_run_cost(self,wall_s,new_fields,branch_fields):
  return self._transaction(lambda events:{'kind':'run_cost','wall_s':wall_s,'fields_already_debited':new_fields,'branch_fields':branch_fields})
