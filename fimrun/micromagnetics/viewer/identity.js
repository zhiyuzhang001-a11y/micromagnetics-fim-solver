// Identity checks are independent of rendering; no interpolation or physics.
export const fields=['run_id','binding_sha256','instance','stage_id','stage_epoch','case_id','case_identity','config_sha256'];
export const key=s=>s?JSON.stringify(fields.map(k=>String(s[k]))):null;
export function acceptState(current,next){
 if(next.schema!=='boris-viewer-state-v1'||next.version!==1)throw Error('未知状态协议');
 if(current){
  if(next.run_id!==current.run_id||next.binding_sha256!==current.binding_sha256||next.instance!==current.instance)throw Error('运行或服务实例变化，请重新打开页面');
  if(next.revision<current.revision)return false;
  if(next.revision===current.revision&&key(next)!==key(current))throw Error('状态身份在相同版本中变化');
 }
 if(!Number.isInteger(next.revision)||!Number.isInteger(next.stage_epoch))throw Error('状态版本无效');
 return true;
}
export function checkFrame(headers,requested,current){
 if(key(requested)!==key(current))throw Error('丢弃过期阶段帧');
 if(headers.get('X-Boris-Schema')!=='boris-viewer-frame-v1'||headers.get('X-Boris-Version')!=='1')throw Error('帧协议无效');
 for(const k of [...fields,'resolved_case_sha256'])if(headers.get('X-Boris-'+k.replaceAll('_','-'))!==String(requested[k]))throw Error('帧身份不符：'+k);
 const revision=Number(headers.get('X-Boris-Revision'));
 if(!Number.isInteger(revision)||revision<requested.revision)throw Error('帧版本过期');
}

export function acceptScriptState(current,next,expected){
 if(next.schema!=='micromagnetics-viewer-v2'||next.version!==2)throw Error('Unknown script protocol');
 if(next.run_id!==expected.get('run_id')||next.instance!==expected.get('instance'))throw Error('Run or instance changed; reopen the intended viewer');
 if(!Number.isSafeInteger(next.revision)||!Number.isSafeInteger(next.stage_epoch)||next.stage_epoch<0)throw Error('Invalid script version');
 if(current&&(next.revision<current.revision||next.stage_epoch<current.stage_epoch))return false;
 if(current&&next.revision===current.revision&&key(next)!==key(current))throw Error('Identity changed at the same revision');
 return true;
}
export function checkScriptFrame(headers,requested,current,frameSeq){
 if(key(requested)!==key(current))throw Error('Discarding an obsolete stage frame');
 if(headers.get('X-Boris-Schema')!=='micromagnetics-frame-v2'||headers.get('X-Boris-Version')!=='2')throw Error('Invalid script frame protocol');
 for(const k of fields)if(headers.get('X-Boris-'+k.replaceAll('_','-'))!==String(requested[k]))throw Error('Script frame identity mismatch: '+k);
 if(frameSeq!=='latest'&&Number(headers.get('X-Boris-Frame-Seq'))!==Number(frameSeq))throw Error('Script frame sequence mismatch');
}

// Recovery is a single selection within a verified identity, never a retry loop.
export function selectScriptFrame({following,requested,frames,latest,sameIdentity}){
 const desired=following?'latest':requested??'latest';
 if(desired!=='latest'&&!frames.includes(desired)){
  if(!sameIdentity)throw Error('History belongs to another stage or configuration; select Follow latest');
  return {desired:'latest',target:latest,expired:true};
 }
 return {desired,target:desired==='latest'?latest:desired,expired:false};
}
