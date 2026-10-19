"""Bounded per-call reads. Content is rehashed before a result is returned."""
from collections import OrderedDict
from contextvars import ContextVar
from functools import wraps
import hashlib
import sys
from pathlib import Path
from ..progress import Progress

_ACTIVE=ContextVar('postprocess_reads',default=None)


class Reads:
    def __init__(self):
        self.raw=OrderedDict();self.bytes=0;self.limit=16*1024*1024
        self.parsed=OrderedDict();self.parsed_bytes=0;self.parsed_limit=16*1024*1024;self.hashes={};self.reporter=Progress('后处理')
        self.stage=None

    def read(self,path):
        path=Path(path).resolve()
        if path in self.raw:
            value=self.raw.pop(path);self.raw[path]=value;return value
        value=path.read_bytes();digest=hashlib.sha256(value).hexdigest()
        if path in self.hashes and self.hashes[path]!=digest:raise ValueError('Source changed during analysis: '+str(path))
        self.hashes[path]=digest
        if len(value)<=self.limit:
            self.raw[path]=value;self.bytes+=len(value)
            while self.bytes>self.limit:
                _,old=self.raw.popitem(last=False);self.bytes-=len(old)
        return value

    def verify(self):
        total=len(self.hashes)
        for n,(path,digest) in enumerate(self.hashes.items(),1):
            if hashlib.sha256(path.read_bytes()).hexdigest()!=digest:raise ValueError('Source changed during analysis: '+str(path))
            self.reporter.count('最终内容校验',n,total,force=n==total)


def read_bytes(path):
    active=_ACTIVE.get()
    return active.read(path) if active else Path(path).read_bytes()


def parsed(path,kind,loader):
    active=_ACTIVE.get();key=(str(Path(path).resolve()),kind)
    if active and key in active.parsed:
        # Parsed objects are read-only by convention and only shared per call.
        return active.parsed[key][0]
    value=loader()
    if active:
        seen=set()
        def size(obj):
            if id(obj) in seen:return 0
            seen.add(id(obj));cost=sys.getsizeof(obj)
            if isinstance(obj,dict):cost+=sum(size(k)+size(v) for k,v in obj.items())
            elif isinstance(obj,(list,tuple)):cost+=sum(size(v) for v in obj)
            return cost
        cost=size(value)
        if cost<=active.parsed_limit:
            active.parsed[key]=(value,cost);active.parsed_bytes+=cost
            while len(active.parsed)>4 or active.parsed_bytes>active.parsed_limit:
                _,(_,oldcost)=active.parsed.popitem(last=False);active.parsed_bytes-=oldcost
    return value


def report(stage,done,total):
    active=_ACTIVE.get()
    if active:
        changed=active.stage!=stage;active.stage=stage
        active.reporter.count(stage,done,total,force=changed or done==total)


def tracked_reads(fn):
    @wraps(fn)
    def run(*args,**kwargs):
        if _ACTIVE.get() is not None:return fn(*args,**kwargs)
        active=Reads();token=_ACTIVE.set(active)
        active.reporter.update('准备读取与校验',force=True)
        calibration=kwargs.get('calibration')
        if calibration is None: calibration=Path(__file__).parent/'calibration_v1.json'
        if fn.__name__ in ('analyze','analyze_ovf') and isinstance(calibration,(str,Path)): active.read(calibration)
        try:
            result=fn(*args,**kwargs);active.verify()
            active.reporter.update('已完成；结果已缓存，可直接show/plot/to_csv',force=True)
            return result
        except BaseException as e:
            active.reporter.update(('已中断' if isinstance(e,KeyboardInterrupt) else '失败')+' · '+str(e),force=True)
            raise
        finally:_ACTIVE.reset(token)
    return run


class ProgressFrames(list):
    def __iter__(self):
        for n,item in enumerate(super().__iter__()):
            report('磁结构分析',n,len(self))
            yield item
        report('磁结构分析',len(self),len(self))
