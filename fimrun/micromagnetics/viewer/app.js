import * as T from 'three';
import {fields,key,acceptState,checkFrame,acceptScriptState,checkScriptFrame,selectScriptFrame} from './identity.js';
import {OrbitControls} from './vendor/OrbitControls.js';
const $=id=>document.getElementById(id), views=[];
const scriptSource=new URLSearchParams(location.search).get('source')==='script';
const expectedSource=new URLSearchParams(location.search);
let bindingState=null, bindingEpoch=0;
let shown=null,timer=null,following=true,serial=0,inflight=null,state=null,unchanged=0,lastVersion=null,activeSource=null;
const counters={requests:0,frameLoads:0,builds:0,renders:0};
const color=z=>{const t=Math.abs(Math.max(-1,Math.min(1,z))),end=z<0?[33,102,172]:[178,24,43];return new T.Color().setRGB(...end.map(c=>(247+(c-247)*t)/255),T.SRGBColorSpace);};
function status(message,bad=false){$('notice').textContent=message;$('notice').hidden=!message;}
function render(){if(document.hidden)return;if(shown)paintSampleCount(shown);document.querySelector('.legend').firstElementChild.textContent=['mx','my','mz'][Number($('component').value)]+' −1';if($('viewMode').value==='2d'){if(shown)draw2D(shown);return;}counters.renders++;document.body.dataset.renders=counters.renders;for(const v of views)if(v.el.clientWidth){v.renderer.render(v.scene,v.camera);v.el.dataset.drawCalls=v.renderer.info.render.calls;v.el.dataset.geometries=v.renderer.info.memory.geometries;v.el.dataset.triangles=v.renderer.info.render.triangles;}}
function resize(){if(document.hidden)return;for(const v of views){const w=v.el.clientWidth,h=v.el.clientHeight;if(!w)continue;v.renderer.setSize(w,h);v.camera.aspect=w/h;v.camera.fov=T.MathUtils.radToDeg(2*Math.atan(Math.tan(T.MathUtils.degToRad(21))/Math.min(1,w/h)));v.camera.updateProjectionMatrix();}render();}
let syncing=false;
function setup(id){const el=$(id),scene=new T.Scene();scene.background=new T.Color('#101e30');const camera=new T.PerspectiveCamera(42,1,.1,100000);camera.up.set(0,0,1);const renderer=new T.WebGLRenderer({antialias:true});renderer.setPixelRatio(Math.min(devicePixelRatio,2));renderer.outputColorSpace=T.SRGBColorSpace;el.append(renderer.domElement);const controls=new OrbitControls(camera,renderer.domElement);controls.enableDamping=false;const v={el,scene,camera,renderer,controls,meshes:[]};views.push(v);controls.addEventListener('change',()=>{if(syncing)return;syncing=true;for(const other of views)if(other!==v){other.camera.position.copy(camera.position);other.camera.quaternion.copy(camera.quaternion);other.controls.target.copy(controls.target);other.controls.update();}syncing=false;render();});return v;}
try{setup('viewA');setup('viewB');}catch(e){status('WebGL 不可用：'+e.message,true);throw e;}
if(scriptSource){
 const pan=document.createElement('button');pan.id='pan';pan.textContent='Pan';pan.setAttribute('aria-pressed','false');
 pan.onclick=()=>{const enabled=pan.getAttribute('aria-pressed')!=='true';pan.setAttribute('aria-pressed',String(enabled));pan.classList.toggle('active',enabled);for(const view of views)view.controls.mouseButtons.LEFT=enabled?T.MOUSE.PAN:T.MOUSE.ROTATE;};
 document.querySelector('.tools').append(pan);
}
new ResizeObserver(resize).observe(document.querySelector('.panels'));
function reset(){if(!shown)return;const g=shown.geometry,d=Math.max(...g.n.map((n,i)=>n*g.cell_nm[i]));for(const v of views){v.camera.position.set(d*.85,-d*1.2,d*1.3);v.controls.target.set(0,0,0);v.controls.update();}resize();}
function clear(v){for(const obj of [...v.scene.children]){v.scene.remove(obj);obj.material?.map?.dispose();obj.geometry?.dispose();if(Array.isArray(obj.material))obj.material.forEach(m=>m.dispose());else obj.material?.dispose();obj.dispose?.();}v.meshes=[];}
function build(data){const started=performance.now();for(const v of views){v.renderer.domElement.hidden=$('viewMode').value==='2d';v.renderer.domElement.style.display=$('viewMode').value==='2d'?'none':'block';if(v.heat){v.heat.hidden=$('viewMode').value!=='2d';v.heat.style.display=$('viewMode').value==='2d'?'block':'none';}}counters.builds++;const g=data.geometry,[nx,ny,nz]=g.n,h=g.cell_nm,o=g.origin_nm,extent=g.n.map((n,i)=>n*h[i]),center=extent.map((v,i)=>v/2+o[i]);const length=Math.min(h[0],h[1])*Number($('arrowLength').value);
const dummy=new T.Object3D(),up=new T.Vector3(0,1,0),dir=new T.Vector3();let maxDirectionError=0;
views.forEach((v,sub)=>{clear(v);if(sub>=data.vectors.length)return;const material=new T.MeshBasicMaterial();const shaft=new T.CylinderGeometry(.055,.055,.68,6);shaft.translate(0,.34,0);const head=new T.ConeGeometry(.16,.32,8);head.translate(0,.84,0);const meshes=[shaft,head].map(geo=>new T.InstancedMesh(geo,material,data.indices.length));
data.indices.forEach((idx,i)=>{const x=idx%nx,y=Math.floor(idx/nx)%ny,z=Math.floor(idx/(nx*ny));const m=data.vectors[sub][i];dummy.position.set(o[0]+(x+.5)*h[0]-center[0],o[1]+(y+.5)*h[1]-center[1],o[2]+(z+.5)*h[2]-center[2]);dir.fromArray(m);dummy.quaternion.setFromUnitVectors(up,dir.normalize());maxDirectionError=Math.max(maxDirectionError,up.clone().applyQuaternion(dummy.quaternion).distanceTo(dir));dummy.scale.setScalar(length);dummy.updateMatrix();const c=color(m[Number($('component').value)]);for(const mesh of meshes){mesh.setMatrixAt(i,dummy.matrix);mesh.setColorAt(i,c);}});
for(const mesh of meshes){mesh.instanceMatrix.needsUpdate=true;mesh.instanceColor.needsUpdate=true;mesh.computeBoundingSphere();v.scene.add(mesh);}v.meshes=meshes;
const ax=new T.AxesHelper(Math.max(...extent)*.18);ax.position.set(-extent[0]/2,-extent[1]/2,-length);v.scene.add(ax);axisLabels(v,ax.position,Math.max(...extent)*.18);
const points=[[-extent[0]/2,-extent[1]/2,0],[extent[0]/2,-extent[1]/2,0],[extent[0]/2,extent[1]/2,0],[-extent[0]/2,extent[1]/2,0]].map(p=>new T.Vector3(...p));v.scene.add(new T.LineLoop(new T.BufferGeometry().setFromPoints(points),new T.LineBasicMaterial({color:0x57718b})));
});document.body.dataset.buildMs=(performance.now()-started).toFixed(2);document.body.dataset.builds=counters.builds;document.querySelector('.panels').dataset.directionError=maxDirectionError;document.querySelector('.panels').dataset.drawCalls=views.map(v=>v.meshes.length).join(',');}
const number=(v,d=0)=>v==null||!Number.isFinite(v)?'—':new Intl.NumberFormat('en-US',{minimumFractionDigits:d,maximumFractionDigits:d}).format(v);
const sci=v=>v==null||!Number.isFinite(v)?'—':v.toExponential(2).replace('e-','e−').replace(/^-/,'−');
const age=v=>v<60?`${number(v)} 秒前`:v<3600?`${number(v/60)} 分钟前`:`${number(v/3600,1)} 小时前`;
function value(id,v,unit,d=0){const el=$(id);el.replaceChildren(document.createTextNode(number(v,d)));if(v!=null){const small=document.createElement('small');small.textContent=unit;el.append(small);}}
function config(s){if(s.new_api){
 const c=s.configuration,m=c.model,g=s.geometry;
 $('configSummary').textContent=m.model+' | '+g.n.join(' x ')+' | material / terms / excitation';
 const values=[['Grid cells',g.n],['Cell size / nm',g.cell_nm],['Origin / nm',g.origin_nm],['Material: Ms A/m, alpha unit1, gamma_H m/(A s)',m.material],['Enabled terms (SI)',m.energy],['External field H A/m or B T',m.energy.find(t=>t.type==='Zeeman')??'Zero (no Zeeman term)'],['Current / torque: J A/m^2',c.current??'Off (no current torque)'],['RK4 dt / s',c.solver.dt],['Static stop / A/m',c.stop]];
 $('configValues').replaceChildren();for(const [label,value]of values){const cell=document.createElement('div'),b=document.createElement('b');b.textContent=label;cell.append(b,document.createTextNode(value==null?'Unavailable':JSON.stringify(value)));$('configValues').append(cell);}return;
 }const c=s.configuration,g=c.geometry,m=c.material||{},drive=c.drive;
 $('configSummary').textContent=`${g.n.join(' × ')} · ${g.cell_nm.map(v=>number(v,1)).join(' × ')} nm${drive?' · SOT':''}`;
 const fields=[['网格',g.n.join(' × ')],['单元 / nm',g.cell_nm.map(v=>number(v,1)).join(' × ')],['原点 / nm',g.origin_nm.map(v=>number(v,1)).join(', ')],['Ms / A/m',m.Ms_Apm?.map(sci).join(' / ')||'—'],['交换 A / J/m',m.A_Jpm?.map(sci).join(' / ')||'—'],['阻尼 α',m.alpha?.map(v=>number(v,3)).join(' / ')||'—'],['K₁ / J/m³',m.K1_Jpm3?.map(sci).join(' / ')||'—'],['外场 H / A/m',c.field?.H_Apm?.map(sci).join(', ')||'—']];
 if(drive)fields.push(['电流 Jc / A/m²',drive.Jc_Apm2?.map(sci).join(', ')||'—'],['力矩 ξ',drive.xi?.map(v=>number(v,3)).join(' / ')||'—'],['入射方向',drive.incident_direction?.map(v=>number(v,1)).join(', ')||'—'],['场型比例',drive.field_like_ratio?.map(v=>number(v,3)).join(' / ')||'—']);
 else fields.push(['力矩','不适用']);
 if(s.stage==='static')fields.push(['配置容差 / A/m',number(c.static?.tol_Apm,3)]);
 $('configValues').replaceChildren();for(const [k,v]of fields){const cell=document.createElement('div'),key=document.createElement('span'),b=document.createElement('b');key.textContent=k;b.textContent=v;cell.append(key,b);$('configValues').append(cell);}
}
function paintState(s){const isStatic=s.stage==='static';$('stepsMetric').hidden=isStatic;$('dtMetric').hidden=isStatic;document.querySelector('.metrics').classList.toggle('static',isStatic||Boolean(s.pre_native));if(s.pre_native){$('stepsMetric').hidden=true;$('dtMetric').hidden=true;}$('runName').textContent=s.name;const phase=s.phase?({driven_dynamic:'驱动态',dynamic:'动态',static:'静态',static_fresh:'静态',kernel:'核准备'}[s.phase]||s.phase):'阶段不可用';$('phase').textContent=`${phase}${s.failure?' · 失败':s.finished?' · 已结束':s.pre_native?' · 等待原生进度':''}`;
 $('progressKey').textContent=isStatic?'迭代进度':'求解时间';value('progressValue',isStatic?s.step:s.time_ps,isStatic?'次':'ps',isStatic?0:3);$('progressTarget').textContent=isStatic?`预算 ${number(s.target_steps)} 次`:s.target_ps==null?'目标不可用':`目标 ${number(s.target_ps,3)} ps`;
 $('stepsKey').textContent=isStatic?'动态步数':'步数';value('stepsValue',isStatic?null:s.step,'');$('stepsTarget').textContent=isStatic?'静态阶段不推进物理时间':`目标 ${number(s.target_steps)}`;
 value('dtValue',s.dt_fs,'fs',2);$('dtNote').textContent=isStatic?'静态步长未输出':'';value('elapsedValue',s.elapsed_s,'s',2);$('elapsedNote').textContent=s.pre_native?(s.elapsed_scope==='workflow'?'工作流':'当前阶段'):'当前原生阶段';value('speedValue',s.throughput_steps_s,isStatic?'次/s':'步/s',1);
 paintGates(s);$('energy').textContent=sci(s.energy_J);$('resA').textContent=sci(s.residual_A_Apm);$('resB').textContent=sci(s.residual_B_Apm);
 const energyAt=isStatic?`迭代 ${number(s.step)}`:`${number(s.time_ps,3)} ps`,resAt=isStatic?`迭代 ${number(s.residual_step)}`:`${number(s.residual_time_ps,3)} ps`;
 $('logTime').textContent=s.pre_native?'日志不可用':s.residual_step!=null&&s.residual_step!==s.step?`能量 ${energyAt} · 残差 ${resAt}`:`日志 ${energyAt}`;
 $('age').textContent=`输出更新 ${age(s.progress_age_s)}`;$('age').title=`进度文件 UTC ${s.progress_mtime_utc}；不是当前计算活动证明`;
 const frames=s.frames;$('frame').disabled=!frames.length;$('frame').max=Math.max(0,frames.length-1);config(s);
 if(s.failure)status(s.failure,true);else status('');
}
const paintLegacyState=paintState;
paintState=function(s){
 paintLegacyState(s);
 if(!s.new_api)return;
 const fm=s.labels.length===1,sub=document.querySelector('[data-sub].active')?.dataset.sub;
 $('panelA').hidden=!fm&&sub==='B';$('panelB').hidden=fm||sub==='A';
 document.querySelector('.caption').textContent=s.labels[0];
 for(const button of document.querySelectorAll('[data-sub]'))button.hidden=fm;
 const physics=document.querySelectorAll('.physics > span');physics[2].hidden=fm;
 physics[1].querySelector('.key').textContent='Residual '+s.labels[0];
 $('elapsedNote').textContent='Current stage';
 if(s.stage==='static')$('progressTarget').textContent='Stop '+JSON.stringify(s.configuration.stop)+'; no fixed update target';
};
function paintFrame(data){paintSampleCount(data);$('frameTime').textContent=data.stage==='static'?`磁矩 · 迭代 ${number(data.step)}`:`磁矩 ${number(data.time_ps,3)} ps`;
 const index=state.frames.indexOf(data.frame_seq??data.step);$('frame').value=Math.max(0,index);$('frameCount').textContent=`${number(index+1)} / ${number(state.frames.length)}`;
 $('source').textContent=`\n磁矩 step ${data.step} · ${data.source}\n磁矩文件 UTC ${data.frame_mtime_utc}\n日志目录 ${state.source}\n进度文件 UTC ${state.progress_mtime_utc}\n浏览器检查 UTC ${new Date().toISOString()}\n文件年龄为检查时数值，不证明进程仍在运行。${state.stop_reason?'\n原生停止原因：'+state.stop_reason:''}${bindingState?'\nrun '+bindingState.run_id+' · revision '+bindingState.revision+' · stage '+bindingState.stage_id+' / epoch '+bindingState.stage_epoch+'\ncase '+bindingState.case_id+' · '+bindingState.case_identity+'\nconfig '+bindingState.config_sha256+'\nresolved file '+bindingState.resolved_case_sha256+'\nviewer instance '+bindingState.instance:''}`;
 if(state.new_api){$('source').textContent=`run ${bindingState.run_id} | instance ${bindingState.instance}\nsegment ${bindingState.stage_id} | epoch ${bindingState.stage_epoch} | revision ${bindingState.revision}\nconfig ${bindingState.config_sha256}\nframe ${data.frame_seq} | accepted step ${data.step} | physical time ${data.physical_time_s} s\nsource: bounded transient memory; no file modification time\nchecked ${new Date().toISOString()} | frame age ${number(data.frame_age_s,2)} s`;$('age').textContent='State age '+number(state.progress_age_s,2)+' s';$('age').title='Accepted-state publication age; not a file timestamp';if(state.stage==='static')$('progressTarget').textContent='Stop '+JSON.stringify(state.configuration.stop);$('logTime').textContent='Cached scalar step '+state.scalar_step+' | residual '+(state.residual_step??'unavailable');}
 $('io').textContent=`${number(data.indices.length)} 箭头/子晶格 · 读取验证 ${number(data.read_ms,1)} ms${data.cache_hit?' · 缓存':''}`;
}
async function get(url,signal,identity=null){counters.requests++;document.body.dataset.requests=counters.requests;if(scriptSource){const u=new URL(url,location.origin);for(const k of ['run_id','instance'])u.searchParams.set(k,expectedSource.get(k));url=u.pathname+u.search;}const r=await fetch(url,{signal,cache:'no-store'});if(identity&&r.ok){if(scriptSource)checkScriptFrame(r.headers,identity,bindingState,new URL(url,location.origin).searchParams.get('step'));else checkFrame(r.headers,identity,bindingState);}if(scriptSource&&r.status===409){clearFrame();bindingState=null;throw Error('Source changed or frame expired. Select Follow latest to read a verified current frame');}const d=await r.json();if(!r.ok)throw Error(d.error||r.status);if(identity){if(scriptSource)checkScriptFrame(r.headers,identity,bindingState,new URL(url,location.origin).searchParams.get('step'));else checkFrame(r.headers,identity,bindingState);}return d;}
function clearFrame(){$('sampleCount').textContent='显示数量 —';for(const v of views)clear(v);shown=null;activeSource=null;$('frameTime').textContent='磁矩 —';$('frameCount').textContent='— / —';$('source').textContent='';$('io').textContent='';render();}
function mode(){const hidden=document.hidden;$('latest').textContent=following?'暂停':'跟随最新';$('latest').classList.toggle('active',following);$('mode').textContent=hidden?'页面隐藏 · 已暂停':following?`自动跟随 · ${Math.min(30,5*2**unchanged)} 秒检查`:'历史浏览 · 已暂停';}
function cancel(){clearTimeout(timer);timer=null;inflight?.abort();inflight=null;serial++;}
function pause(){following=false;cancel();mode();}
async function load(requested=null){if(document.hidden)return;clearTimeout(timer);inflight?.abort();const token=++serial,controller=new AbortController();inflight=controller;const timeout=setTimeout(()=>controller.abort(),8000);
 try{let historyIdentityUnchanged=false,recoveredHistory=false;let next;if(scriptSource){const binding=await get('/api/binding',controller.signal);if(token!==serial)return;if(binding.instance!==expectedSource.get('instance')||!Number.isSafeInteger(binding.binding_epoch)||binding.binding_epoch<bindingEpoch)throw Error('Invalid viewer rebind');if(binding.run_id!==expectedSource.get('run_id')){if(binding.binding_epoch<=bindingEpoch)throw Error('Unapproved run rebind');clearFrame();bindingState=null;state=null;activeSource=null;expectedSource.set('run_id',binding.run_id);}bindingEpoch=binding.binding_epoch;}next=await get('/api/state',controller.signal);if(token!==serial||document.hidden)return;
 if(next.schema==='micromagnetics-viewer-v2'){
  if(bindingState&&(next.run_id!==bindingState.run_id||next.instance!==bindingState.instance||next.stage_epoch!==bindingState.stage_epoch))clearFrame();
  if(!acceptScriptState(bindingState,next,expectedSource))return;
  historyIdentityUnchanged=bindingState!==null&&key(next)===key(bindingState);
  if(key(next)!==key(bindingState))clearFrame();bindingState=next;next=next.data;
 }else if(next.schema==='boris-viewer-state-v1'){
  if(!acceptState(bindingState,next))return;
  if(key(next)!==key(bindingState))clearFrame();bindingState=next;
  if(next.data===null){state=null;$('progressKey').textContent='求解进度';$('stepsMetric').hidden=true;$('dtMetric').hidden=true;document.querySelector('.metrics').classList.add('static');$('elapsedNote').textContent='等待原生输出';$('dtNote').textContent='';$('runName').textContent=next.case_id;$('phase').textContent=next.stage_id+' · 等待输出';$('frame').disabled=true;$('frameCount').textContent='— / —';$('source').textContent=`run ${next.run_id} · revision ${next.revision} · ${next.case_state}`;for(const id of ['progressValue','progressTarget','stepsValue','stepsTarget','dtValue','elapsedValue','speedValue','energy','resA','resB','logTime','age','configSummary'])$(id).textContent='—';$('configValues').replaceChildren();status(`${next.data_state==='waiting_for_case'?'等待配置文件':'等待完整原生磁矩帧'}${shown?' · 保留本阶段上个有效帧':''}`);mode();return;}
  next=next.data;
 }else if(bindingState)throw Error('状态协议发生变化');
 if(activeSource!==null&&next.run_source!==activeSource)clearFrame();activeSource=next.run_source;state=next;paintState(state);
 const version=JSON.stringify([state.run_source,state.phase,state.step,state.checkpoint_step,state.latest_signature,state.failure,state.finished]);unchanged=version===lastVersion?Math.min(3,unchanged+1):0;lastVersion=version;
 if(!state.frames.length){if(state.pre_native){status('');mode();return;}throw Error('尚无完整磁矩帧');}
 let desired=following?'latest':requested??shown?.frame_seq??shown?.step??'latest',target=desired==='latest'?state.checkpoint_step:desired;
 if(scriptSource){const selection=selectScriptFrame({following,requested:desired,frames:state.frames,latest:state.checkpoint_step,sameIdentity:historyIdentityUnchanged});({desired,target}=selection);recoveredHistory=selection.expired;}
 const same=shown&&shown.stage===state.stage&&(shown.frame_seq??shown.step)===target&&shown.stride===Number($('stride').value)&&JSON.stringify(shown.source_signature)===JSON.stringify(desired==='latest'?state.latest_signature:shown.source_signature);
 if(!same){const requestedIdentity=bindingState?{...bindingState}:null,params=new URLSearchParams({stage:state.stage,step:scriptSource?String(target):desired,stride:$('stride').value});if(requestedIdentity)for(const k of fields)params.set(k,requestedIdentity[k]);const data=await get('/api/frame?'+params,controller.signal,requestedIdentity);if(token!==serial||document.hidden)return;counters.frameLoads++;const first=!shown;build(data);shown=data;if(first)reset();else render();}
 if(shown){paintFrame(shown);if($('viewMode').value==='2d')draw2D(shown);}if(recoveredHistory){status('Selected history frame is no longer available; showing the latest verified frame. History remains paused.');document.body.dataset.historyRecoveries=String(Number(document.body.dataset.historyRecoveries||0)+1);}mode();
 }catch(e){if(token!==serial||document.hidden)return;unchanged=Math.min(3,unchanged+1);status(`${shown?'保留原帧':'尚无有效帧'} · ${e.name==='AbortError'?'连接超时':e.message}`,true);mode();}
 finally{clearTimeout(timeout);if(token===serial){inflight=null;if(following&&!document.hidden)timer=setTimeout(()=>load(),Math.min(30000,5000*2**unchanged));}}
}
$('frame').oninput=()=>{const step=state?.frames[Number($('frame').value)];pause();if(step!=null)load(step);};
for(const [id,delta]of[['prev',-1],['next',1]])$(id).onclick=()=>{if(!state?.frames.length)return;const i=Math.max(0,Math.min(state.frames.length-1,Number($('frame').value)+delta));pause();load(state.frames[i]);};
$('latest').onclick=()=>{if(following)pause();else{following=true;unchanged=0;mode();load();}};
$('refresh').onclick=()=>load();$('reset').onclick=reset;$('stride').onchange=()=>load();
for(const button of document.querySelectorAll('[data-sub]'))button.onclick=()=>{for(const b of document.querySelectorAll('[data-sub]')){const active=b===button;b.classList.toggle('active',active);b.setAttribute('aria-pressed',String(active));}const sub=button.dataset.sub;$('panelA').hidden=sub==='B';$('panelB').hidden=sub==='A';resize();};
document.addEventListener('visibilitychange',()=>{const audit=JSON.parse(document.body.dataset.visibilityAudit||'[]');audit.push({hidden:document.hidden,unix_ms:Date.now(),...counters});document.body.dataset.visibilityAudit=JSON.stringify(audit.slice(-4));if(document.hidden){cancel();mode();}else{mode();if(following){unchanged=0;load();}}});
window.addEventListener('pagehide',cancel);
window.previewDiagnostics=()=>({scriptSource,instance:bindingState?.instance,frameSeq:shown?.frame_seq,stageEpoch:bindingState?.stage_epoch,step:shown?.step,following,hidden:document.hidden,pollDelayMs:Math.min(30000,5000*2**unchanged),...counters,views:views.map(v=>({calls:v.renderer.info.render.calls,geometries:v.renderer.info.memory.geometries,instances:v.meshes.map(m=>m.count)}))});
for(const id of ['viewMode','component','slice','arrowLength'])$(id).onchange=()=>{if(shown){build(shown);render();}};
mode();load();


function axisLabels(v,base,length){
 for(const [i,label,tint]of [[0,'+X','#ff7777'],[1,'+Y','#77ff77'],[2,'+Z','#88aaff']]){
  const c=document.createElement('canvas');c.width=128;c.height=64;const ctx=c.getContext('2d');ctx.fillStyle=tint;ctx.font='bold 40px sans-serif';ctx.fillText(label,10,48);
  const material=new T.SpriteMaterial({map:new T.CanvasTexture(c),depthTest:false});const sprite=new T.Sprite(material);sprite.position.copy(base);sprite.position.setComponent(i,sprite.position.getComponent(i)+length*1.2);sprite.scale.set(length*.7,length*.35,1);v.scene.add(sprite);
 }
}
function paintGates(s){
 const el=$('convergence');if(!s.convergence){el.textContent='';return;}
 const parts=s.convergence.map(g=>{
  const gate=(value,limit,passed)=>limit==null?'未启用':value==null?'不可用':passed?'通过':'未过';
  return `${g.label}: residual ${sci(g.residual_Apm)} A/m / 阈值 ${sci(g.residual_limit_Apm)} [${gate(g.residual_Apm,g.residual_limit_Apm,g.residual_pass)}]; mxh ${sci(g.mxh)} / 阈值 ${sci(g.mxh_limit)} [${gate(g.mxh,g.mxh_limit,g.mxh_pass)}]; Ms=${sci(g.Ms_Apm)} A/m${g.dominant?' · 更严门槛 '+g.dominant:''}`;
 });el.textContent=parts.join(' | ')+' — 同一接受态；保守场残差，非完整LLG/SOT力矩。'+(s.static_stop_enabled?'连续接受态条件生效':'动态无静态判停');
}
function draw2D(data){
 const drawStarted=performance.now();
 const g=data.geometry,[nx,ny,nz]=g.n,h=g.cell_nm,o=g.origin_nm,stride=data.stride;
 $('slice').max=nz-1;const layer=Math.max(0,Math.min(nz-1,Math.floor(Number($('slice').value)||0)));$('slice').value=layer;
 const sampledLayer=Math.floor(layer/stride)*stride;
 views.forEach((v,sub)=>{
  v.renderer.domElement.hidden=true;v.renderer.domElement.style.display='none';if(!v.heat){v.heat=document.createElement('canvas');v.heat.style.cssText='width:100%;height:100%';v.el.append(v.heat);}v.heat.hidden=false;v.heat.style.display='block';
  const c=v.heat,w=Math.max(1,v.el.clientWidth),height=Math.max(1,v.el.clientHeight);c.width=w;c.height=height;const ctx=c.getContext('2d');ctx.fillStyle='#101e30';ctx.fillRect(0,0,w,height);if(!data.vectors[sub])return;
  const pad=48,scale=Math.max(.001,Math.min((w-2*pad)/(nx*h[0]),(height-2*pad)/(ny*h[1]))),left=(w-nx*h[0]*scale)/2,top=(height-ny*h[1]*scale)/2;
  data.indices.forEach((idx,j)=>{const z=Math.floor(idx/(nx*ny));if(z!==sampledLayer)return;const x=idx%nx,y=Math.floor(idx/nx)%ny;ctx.fillStyle='#'+color(data.vectors[sub][j][Number($('component').value)]).getHexString(T.SRGBColorSpace);ctx.fillRect(left+x*h[0]*scale,top+(ny-Math.min(ny,y+stride))*h[1]*scale,Math.min(stride,nx-x)*h[0]*scale+.5,Math.min(stride,ny-y)*h[1]*scale+.5);});
  ctx.strokeStyle='#a4b5c9';ctx.strokeRect(left,top,nx*h[0]*scale,ny*h[1]*scale);ctx.fillStyle='#edf3fa';ctx.font='12px sans-serif';ctx.fillText(`+X → / nm: ${o[0].toPrecision(4)} … ${(o[0]+nx*h[0]).toPrecision(4)}`,left,height-15);ctx.fillText(`+Y ↑ / nm: ${o[1].toPrecision(4)} … ${(o[1]+ny*h[1]).toPrecision(4)}`,10,20);ctx.fillText(`z cell ${sampledLayer}; z=${(o[2]+(sampledLayer+.5)*h[2]).toPrecision(4)} nm; stride ×${stride}`,left,height-32);
 });document.querySelector('.legend').firstElementChild.textContent=['mx','my','mz'][Number($('component').value)]+' −1';document.body.dataset.draw2dMs=(performance.now()-drawStarted).toFixed(3);
}


// Count the cached samples that the selected visible sublattices actually draw.
// No grid-size estimate, scientific field evaluation or extra HTTP request.
function paintSampleCount(data){
 const selected=document.querySelector('[data-sub].active')?.dataset.sub??'both';
 const labels=data.labels??state?.labels??['A','B'].slice(0,data.vectors.length);
 const is2D=$('viewMode').value==='2d';
 let count=data.indices.length;
 if(is2D){
  const [nx,ny,nz]=data.geometry.n;
  const layer=Math.max(0,Math.min(nz-1,Math.floor(Number($('slice').value)||0)));
  const sampledLayer=Math.floor(layer/data.stride)*data.stride;
  count=data.indices.filter(idx=>Math.floor(idx/(nx*ny))===sampledLayer).length;
 }
 const visible=labels.filter((label,i)=>i<data.vectors.length&&(labels.length===1||selected==='both'||selected===label));
 const detail=visible.map(label=>`${label} ${number(count)}`).join('、');
 $('sampleCount').textContent=`×${data.stride} · ${detail} · 合计 ${number(count*visible.length)} ${is2D?'采样格点':'箭头'}`;
}
