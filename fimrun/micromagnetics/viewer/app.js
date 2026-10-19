import * as T from 'three';
import {fields,key,acceptState,checkFrame,acceptScriptState,checkScriptFrame,selectScriptFrame} from './identity.js';
import {OrbitControls} from './vendor/OrbitControls.js';
const $=id=>document.getElementById(id), views=[];
const scriptSource=new URLSearchParams(location.search).get('source')==='script';
const expectedSource=new URLSearchParams(location.search);
let bindingState=null, bindingEpoch=0;
const densityByMode={'3d':'4','2d':'1'},viewFrames={'3d':null,'2d':null};let selectedFrame=null;
let shown=null,timer=null,following=true,serial=0,inflight=null,state=null,unchanged=0,lastVersion=null,activeSource=null;
const counters={requests:0,frameLoads:0,builds:0,renders:0};
const color=z=>{const t=Math.abs(Math.max(-1,Math.min(1,z))),end=z<0?[33,102,172]:[178,24,43];return new T.Color().setRGB(...end.map(c=>(247+(c-247)*t)/255),T.SRGBColorSpace);};
function status(message,bad=false){$('notice').textContent=message;$('notice').hidden=!message;$('recover').hidden=!message;}
function render(){if(document.hidden)return;syncViewMode();if(shown)paintSampleCount(shown);document.querySelector('.legend').firstElementChild.textContent=['mx','my','mz'][Number($('component').value)]+' −1';if($('viewMode').value==='2d'){if(shown)draw2D(shown);return;}counters.renders++;document.body.dataset.renders=counters.renders;for(const v of views)if(v.el.clientWidth){v.renderer.render(v.scene,v.camera);v.el.dataset.drawCalls=v.renderer.info.render.calls;v.el.dataset.geometries=v.renderer.info.memory.geometries;v.el.dataset.triangles=v.renderer.info.render.triangles;}}
function resize(){if(document.hidden)return;for(const v of views){const w=v.el.clientWidth,h=v.el.clientHeight;if(!w)continue;v.renderer.setSize(w,h);v.camera.aspect=w/h;v.camera.fov=T.MathUtils.radToDeg(2*Math.atan(Math.tan(T.MathUtils.degToRad(21))/Math.min(1,w/h)));v.camera.updateProjectionMatrix();}render();}
let syncing=false;
function setup(id){const el=$(id),scene=new T.Scene();scene.background=new T.Color('#101e30');const camera=new T.PerspectiveCamera(42,1,.1,100000);camera.up.set(0,0,1);const renderer=new T.WebGLRenderer({antialias:true});renderer.setPixelRatio(Math.min(devicePixelRatio,2));renderer.outputColorSpace=T.SRGBColorSpace;el.append(renderer.domElement);const controls=new OrbitControls(camera,renderer.domElement);controls.enableDamping=false;const v={el,scene,camera,renderer,controls,meshes:[]};views.push(v);controls.addEventListener('change',()=>{if(syncing)return;syncing=true;for(const other of views)if(other!==v){other.camera.position.copy(camera.position);other.camera.quaternion.copy(camera.quaternion);other.controls.target.copy(controls.target);other.controls.update();}syncing=false;render();});return v;}
try{setup('viewA');setup('viewB');}catch(e){status('WebGL 不可用：'+e.message,true);throw e;}
if(scriptSource){
 const pan=document.createElement('button');pan.id='pan';pan.textContent='平移';pan.setAttribute('aria-pressed','false');
 pan.onclick=()=>{const enabled=pan.getAttribute('aria-pressed')!=='true';pan.setAttribute('aria-pressed',String(enabled));pan.classList.toggle('active',enabled);for(const view of views)view.controls.mouseButtons.LEFT=enabled?T.MOUSE.PAN:T.MOUSE.ROTATE;};
 document.querySelector('.tools').append(pan);
}
new ResizeObserver(resize).observe(document.querySelector('.panels'));
function reset(){if(!shown)return;const g=shown.geometry,d=Math.max(...g.n.map((n,i)=>n*g.cell_nm[i]));for(const v of views){v.camera.position.set(d*.85,-d*1.2,d*1.3);v.controls.target.set(0,0,0);v.controls.update();}resize();}
function clear(v){for(const obj of [...v.scene.children]){v.scene.remove(obj);obj.material?.map?.dispose();obj.geometry?.dispose();if(Array.isArray(obj.material))obj.material.forEach(m=>m.dispose());else obj.material?.dispose();obj.dispose?.();}v.meshes=[];}
function syncViewMode(data=shown){
 const is2D=$('viewMode').value==='2d';if($('pan'))$('pan').hidden=is2D;
 for(const v of views){
  v.renderer.domElement.hidden=is2D||!data;v.renderer.domElement.style.display=is2D||!data?'none':'block';
  if(v.heat){v.heat.hidden=!is2D||!data;v.heat.style.display=is2D&&data?'block':'none';}
  if(!v.empty){v.empty=document.createElement('div');v.empty.className='empty-state';v.empty.textContent='等待有效磁态';v.el.append(v.empty);}
  v.empty.hidden=Boolean(data);
 }
}
function build(data){const started=performance.now();if(data.view_mode&&data.view_mode!==$('viewMode').value)throw Error('视图数据模式不符');syncViewMode(data);
 if($('viewMode').value==='2d')return;
 if(data.indices.length>20000)throw Error('3D箭头数量超限，未绘制。');
 counters.builds++;const g=data.geometry,[nx,ny,nz]=g.n,h=g.cell_nm,o=g.origin_nm,extent=g.n.map((n,i)=>n*h[i]),center=extent.map((v,i)=>v/2+o[i]);const spacing=Math.min(h[0],h[1])*data.stride,length=spacing*1.6,width=spacing*1.15;
const dummy=new T.Object3D(),up=new T.Vector3(0,1,0),dir=new T.Vector3();let maxDirectionError=0;
views.forEach((v,sub)=>{clear(v);if(sub>=data.vectors.length)return;const material=new T.MeshBasicMaterial();const shaft=new T.CylinderGeometry(.055,.055,.68,6);shaft.translate(0,.34,0);const head=new T.ConeGeometry(.16,.32,8);head.translate(0,.84,0);const meshes=[shaft,head].map(geo=>new T.InstancedMesh(geo,material,data.indices.length));
data.indices.forEach((idx,i)=>{const x=idx%nx,y=Math.floor(idx/nx)%ny,z=Math.floor(idx/(nx*ny));const m=data.vectors[sub][i];dummy.position.set(o[0]+(x+.5)*h[0]-center[0],o[1]+(y+.5)*h[1]-center[1],o[2]+(z+.5)*h[2]-center[2]);dir.fromArray(m);dummy.quaternion.setFromUnitVectors(up,dir.normalize());maxDirectionError=Math.max(maxDirectionError,up.clone().applyQuaternion(dummy.quaternion).distanceTo(dir));dummy.scale.set(width,length,width);dummy.updateMatrix();const c=color(m[Number($('component').value)]);for(const mesh of meshes){mesh.setMatrixAt(i,dummy.matrix);mesh.setColorAt(i,c);}});
for(const mesh of meshes){mesh.instanceMatrix.needsUpdate=true;mesh.instanceColor.needsUpdate=true;mesh.computeBoundingSphere();v.scene.add(mesh);}v.meshes=meshes;
const ax=new T.AxesHelper(Math.max(...extent)*.18);ax.position.set(-extent[0]/2,-extent[1]/2,-length);v.scene.add(ax);axisLabels(v,ax.position,Math.max(...extent)*.18);
const points=[[-extent[0]/2,-extent[1]/2,0],[extent[0]/2,-extent[1]/2,0],[extent[0]/2,extent[1]/2,0],[-extent[0]/2,extent[1]/2,0]].map(p=>new T.Vector3(...p));v.scene.add(new T.LineLoop(new T.BufferGeometry().setFromPoints(points),new T.LineBasicMaterial({color:0x57718b})));
});document.body.dataset.buildMs=(performance.now()-started).toFixed(2);document.body.dataset.builds=counters.builds;document.querySelector('.panels').dataset.directionError=maxDirectionError;document.querySelector('.panels').dataset.drawCalls=views.map(v=>v.meshes.length).join(',');}
const number=(v,d=0)=>v==null||!Number.isFinite(v)?'—':new Intl.NumberFormat('en-US',{minimumFractionDigits:d,maximumFractionDigits:d}).format(v);
const sci=v=>v==null||!Number.isFinite(v)?'—':v.toExponential(2).replace('e-','e−').replace(/^-/,'−');
const age=v=>v<60?`${number(v)} 秒前`:v<3600?`${number(v/60)} 分钟前`:`${number(v/3600,1)} 小时前`;
function value(id,v,unit,d=0){const el=$(id);el.replaceChildren(document.createTextNode(number(v,d)));if(v!=null){const small=document.createElement('small');small.textContent=unit;el.append(small);}}
function displayNumber(v){return typeof v==='number'?(v===0?'0':Math.abs(v)<.001||Math.abs(v)>=1e5?v.toExponential(3):String(Number(v.toPrecision(6)))):String(v??'—');}
function config(s,frame=null){
 const root=$('configValues');root.replaceChildren();
 const historical=Boolean(frame)&&state&&((frame.frame_seq??frame.step)!==state.checkpoint_step);
 const c=frame?.configuration??(!historical?s.configuration:null),g=frame?.geometry??s.geometry;
 $('configSummary').textContent=historical?'当前显示帧 · 模型参数':'模型参数';
 if(!c){root.textContent='此历史帧未提供参数快照，无法确认。';return;}
 if(!s.new_api){root.textContent='此来源尚未提供可整理的参数快照。';return;}
 const model=c.model;
 function section(title,heads,rows){if(!rows.length)return;const box=document.createElement('section'),h=document.createElement('h3'),table=document.createElement('table');box.className='parameter-section';h.textContent=title;box.append(h);
 const tr=document.createElement('tr');for(const text of heads){const th=document.createElement('th');th.textContent=text;tr.append(th);}const thead=document.createElement('thead');thead.append(tr);table.append(thead);const body=document.createElement('tbody');
 for(const row of rows){const line=document.createElement('tr');for(const value of row){const td=document.createElement('td');td.textContent=displayNumber(value);line.append(td);}body.append(line);}table.append(body);box.append(table);root.append(box);}
 const mat=model.material??{},A=mat.A??mat,B=mat.B;
 section('网格与尺寸',['项目','X','Y','Z','单位'],[['网格数',...g.n,'格'],['单元尺寸',...g.cell_nm,'nm'],['样品尺寸',...g.n.map((n,i)=>n*g.cell_nm[i]),'nm'],['原点',...g.origin_nm,'nm']]);
 const rows=[['饱和磁化 Ms',A.Ms,...(B?[B.Ms]:[]),'A/m'],['阻尼 α',A.alpha,...(B?[B.alpha]:[]),'1'],['旋磁比 γH',A.gamma_H,...(B?[B.gamma_H]:[]),'m/(A·s)']];
 section('材料',B?['参数','A','B','单位']:['参数','值','单位'],rows);
 const terms=model.energy??[],energy=[];
 const pair=(label,t,a,b,unit)=>energy.push([label,displayNumber(t[a]),B?displayNumber(t[b]):'—',unit]);
 for(const t of terms){switch(t.type){
 case 'FiMExchange':pair('梯度交换 A',t,'A_A','A_B','J/m');energy.push(['交叉交换 Anh',displayNumber(t.Anh)+'（共享）','—','J/m']);break;
 case 'OnsiteCoupling':energy.push(['局域耦合 Ah',displayNumber(t.Ah)+'（共享）','—','J/m³']);break;
 case 'DMI':pair('DMI',t,'D_A','D_B','J/m²');break;
 case 'FiMAnisotropy':pair('各向异性 K₁',t,'K1_A','K1_B','J/m³');pair('各向异性 K₂',t,'K2_A','K2_B','J/m³');energy.push(['易轴',t.axis_A?.map(displayNumber).join(', '),t.axis_B?.map(displayNumber).join(', '),'单位方向']);break;
 case 'Demag':energy.push(['退磁','已启用（共享）','—','—']);break;
 case 'Zeeman':break;
 default:energy.push([t.type,'已启用','—','—']);}}
 section('能量项',['参数','A / 共享','B','单位'],energy);
 const zeeman=terms.find(t=>t.type==='Zeeman'),excitation=[];
 if(zeeman){const H=zeeman.H_ext,Bext=zeeman.B_ext;excitation.push([Bext?'外场 B':'外场 H',(Bext??H??[]).map(displayNumber).join(', '),Bext?'T':'A/m']);}else excitation.push(['外场','未施加','—']);
 if(c.current){for(const [key,label,unit]of [['J','电流 J','A/m²'],['incident_direction','入射方向','单位方向']])excitation.push([label,c.current[key]?.map(displayNumber).join(', '),unit]);for(const [key,label]of [['xi_A','A 力矩系数 ξ'],['xi_B','B 力矩系数 ξ'],['field_like_A','A 场型比'],['field_like_B','B 场型比']])excitation.push([label,c.current[key],'1']);}else excitation.push(['电流','未施加','—']);
 section('外场与电流',['项目','值','单位'],excitation);
 const solver=[];if(frame?.stage==='static'||(!frame&&s.stage==='static')){if(c.stop){if(c.stop.tolerance!=null)solver.push(['残差阈值',c.stop.tolerance,'A/m']);if(c.stop.mxh!=null)solver.push(['mxh阈值',c.stop.mxh,'1']);if(c.stop.consecutive!=null)solver.push(['连续接受态',c.stop.consecutive,'次']);}}
 else if(c.solver?.dt!=null)solver.push(['动态步长',c.solver.dt,'s']);
 section(historical?'该帧求解设置':'求解设置',['项目','值','单位'],solver);
 root.dataset.configHash=frame?.config_sha256??'';
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
 const physics=document.querySelectorAll('.physics > span');physics[1].hidden=true;physics[2].hidden=true;
 physics[1].querySelector('.key').textContent='Residual '+s.labels[0];
 $('elapsedNote').textContent='本阶段';
 if(s.stage==='static')$('progressTarget').textContent='满足双门及连续计数后停止';
 if(s.progress){const p=s.progress;$('progressKey').textContent=p.kind==='static'?'已接受迭代':'本次演化';
 value('progressValue',p.kind==='static'?p.step:p.stage_elapsed_s*1e12,p.kind==='static'?'次':'ps',p.kind==='static'?0:3);
 $('progressTarget').textContent=p.kind==='static'?`连续达标 ${p.consecutive}/${p.consecutive_required}`:`目标 ${number(p.stage_duration_s*1e12,3)} ps · ${number(p.percent,1)}%`;
 $('stepsTarget').textContent=`目标 ${number(p.target_steps)} · 累计 ${number(p.physical_time_s*1e12,3)} ps`;
 $('elapsedNote').textContent=p.phase==='running'?'等待下一接受态/原生调用返回':'本阶段';
 if(['initialized','restored'].includes(p.phase)){$('progressKey').textContent='累计物理时间';value('progressValue',p.physical_time_s*1e12,'ps',3);$('progressTarget').textContent=p.phase==='restored'?'已恢复 · 待运行':'未开始';$('stepsMetric').hidden=true;}}
 paintDiagnostics(s);
};
function paintFrame(data){paintSampleCount(data);$('frameTime').textContent=data.stage==='static'?`磁矩 · 迭代 ${number(data.step)}`:`磁矩 ${number(data.time_ps,3)} ps`;
 const index=state.frames.indexOf(data.frame_seq??data.step);$('frame').value=Math.max(0,index);$('frameCount').textContent=`${number(index+1)} / ${number(state.frames.length)}`;
 $('source').textContent=`\n磁矩 step ${data.step} · ${data.source}\n磁矩文件 UTC ${data.frame_mtime_utc}\n日志目录 ${state.source}\n进度文件 UTC ${state.progress_mtime_utc}\n浏览器检查 UTC ${new Date().toISOString()}\n文件年龄为检查时数值，不证明进程仍在运行。${state.stop_reason?'\n原生停止原因：'+state.stop_reason:''}${bindingState?'\nrun '+bindingState.run_id+' · revision '+bindingState.revision+' · stage '+bindingState.stage_id+' / epoch '+bindingState.stage_epoch+'\ncase '+bindingState.case_id+' · '+bindingState.case_identity+'\nconfig '+bindingState.config_sha256+'\nresolved file '+bindingState.resolved_case_sha256+'\nviewer instance '+bindingState.instance:''}`;
 if(state.new_api){$('source').textContent=`run ${bindingState.run_id} | instance ${bindingState.instance}\nsegment ${bindingState.stage_id} | epoch ${bindingState.stage_epoch} | revision ${bindingState.revision}\nconfig ${bindingState.config_sha256}\nframe ${data.frame_seq} | accepted step ${data.step} | physical time ${data.physical_time_s} s\nsource: bounded transient memory; no file modification time\nchecked ${new Date().toISOString()} | frame age ${number(data.frame_age_s,2)} s`;$('age').textContent='更新于 '+number(state.progress_age_s,1)+' 秒前';$('age').title='Accepted-state publication age; not a file timestamp';$('logTime').textContent='';}
 $('io').textContent='';config(state,data);paintDiagnostics(state,data);
}
async function get(url,signal,identity=null){
 counters.requests++;document.body.dataset.requests=counters.requests;
 if(scriptSource){const u=new URL(url,location.origin);for(const k of ['run_id','instance'])u.searchParams.set(k,expectedSource.get(k));url=u.pathname+u.search;}
 const r=await fetch(url,{signal,cache:'no-store'});
 if(!r.ok){const text=await r.text();let body={};try{body=JSON.parse(text);}catch{}
  const capacity=body.code==='capacity_exceeded'||text.includes('too many visible arrows');
  const e=Error(capacity?(body.message??'3D箭头数量过多，请选择更疏的显示；2D可用每1格。'):body.message??body.error??(r.status===409?'来源或历史帧已变化，请恢复最新磁态。':`无法读取磁态（${r.status}），请刷新重试。`));
  e.code=capacity?'capacity_exceeded':body.code??(r.status===409?'source_changed':'request_failed');
  if(['source_changed','frame_expired','waiting_for_state'].includes(e.code)){clearFrame();bindingState=null;}
  throw e;
 }
 if(identity){try{if(scriptSource)checkScriptFrame(r.headers,identity,bindingState,new URL(url,location.origin).searchParams.get('step'));else checkFrame(r.headers,identity,bindingState);}catch{clearFrame();bindingState=null;const error=Error('磁态来源校验未通过，请恢复最新或重新打开目标模拟。');error.code='source_changed';throw error;}}
 return r.json();
}
function clearFrame(){shown=null;selectedFrame=null;viewFrames['2d']=viewFrames['3d']=null;activeSource=null;for(const v of views){clear(v);if(v.heat){v.heat.getContext('2d').clearRect(0,0,v.heat.width,v.heat.height);}v.heatFrame=null;}
 $('sampleCount').textContent='';$('frameTime').textContent='磁态不可用';$('frameCount').textContent='— / —';$('source').textContent='';$('io').textContent='';$('configValues').replaceChildren();syncViewMode();render();}
function mode(){const hidden=document.hidden;$('latest').textContent=following?'暂停观看':'继续观看';$('latest').classList.toggle('active',following);$('mode').textContent=hidden?'页面隐藏 · 已暂停':following?`自动跟随 · ${scriptSource?2:Math.min(30,5*2**unchanged)} 秒检查`:'已暂停观看 · 不影响计算';}
function cancel(){document.body.setAttribute('aria-busy','false');clearTimeout(timer);timer=null;inflight?.abort();inflight=null;serial++;}
function pause(){following=false;cancel();mode();}
async function load(requested=null){if(document.hidden)return;clearTimeout(timer);inflight?.abort();const token=++serial,controller=new AbortController();inflight=controller;const timeout=setTimeout(()=>controller.abort(),8000);document.body.setAttribute('aria-busy','true');
 try{let historyIdentityUnchanged=false,recoveredHistory=false,previewNotice=null;let next;if(scriptSource){const binding=await get('/api/binding',controller.signal);if(token!==serial)return;if(binding.handoff_error){clearFrame();bindingState=null;throw Error(binding.handoff_error);}previewNotice=binding.handoff_notice;if(binding.instance!==expectedSource.get('instance')||!Number.isSafeInteger(binding.binding_epoch)||binding.binding_epoch<bindingEpoch)throw Error('Invalid viewer rebind');if(binding.run_id!==expectedSource.get('run_id')){if(binding.binding_epoch<=bindingEpoch)throw Error('Unapproved run rebind');clearFrame();bindingState=null;state=null;activeSource=null;following=true;unchanged=0;selectedFrame=null;expectedSource.set('run_id',binding.run_id);const reboundUrl=new URL(window.location.href);reboundUrl.searchParams.set('run_id',binding.run_id);window.history.replaceState(null,'',reboundUrl);}bindingEpoch=binding.binding_epoch;}next=await get('/api/state',controller.signal);if(token!==serial||document.hidden)return;
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
 let desired=following?'latest':requested??selectedFrame??shown?.frame_seq??shown?.step??'latest',target=desired==='latest'?state.checkpoint_step:desired;
 if(scriptSource){const selection=selectScriptFrame({following,requested:desired,frames:state.frames,latest:state.checkpoint_step,sameIdentity:historyIdentityUnchanged});({desired,target}=selection);recoveredHistory=selection.expired;}
 const same=shown&&(!shown.view_mode||shown.view_mode===$('viewMode').value)&&shown.stage===state.stage&&(shown.frame_seq??shown.step)===target&&shown.stride===Number($('stride').value)&&JSON.stringify(shown.source_signature)===JSON.stringify(desired==='latest'?state.latest_signature:shown.source_signature);
 if(!same){const requestedIdentity=bindingState?{...bindingState}:null,params=new URLSearchParams({stage:state.stage,step:scriptSource?String(target):desired,stride:$('stride').value,view:$('viewMode').value});if(requestedIdentity)for(const k of fields)params.set(k,requestedIdentity[k]);const data=await get('/api/frame?'+params,controller.signal,requestedIdentity);if(token!==serial||document.hidden)return;const requestedView=params.get('view');if(data.view_mode&&data.view_mode!==requestedView)throw Error('收到错误视图的数据，已忽略。');
 counters.frameLoads++;const first=!shown;data._viewerKey=key(requestedIdentity);build(data);shown=data;selectedFrame=data.frame_seq??data.step;viewFrames[requestedView]=data;densityByMode[requestedView]=String(data.stride);$('stride').value=String(data.stride);if(first)reset();else render();}
 if(shown)paintFrame(shown);if(recoveredHistory){status('历史帧已过期，现显示已验证的最新磁态；观看仍暂停。');document.body.dataset.historyRecoveries=String(Number(document.body.dataset.historyRecoveries||0)+1);}if(previewNotice)status(previewNotice,true);mode();
 }catch(e){if(token!==serial||document.hidden)return;unchanged=Math.min(3,unchanged+1);if(scriptSource)$('phase').textContent='预览暂不可用 · 非实时';if(shown){$('stride').value=String(shown.stride);paintSampleCount(shown);config(state,shown);}status(`${shown?'已保留原磁态。':'暂无有效磁态。'}${e.name==='AbortError'?'连接超时，请刷新重试。':e instanceof TypeError?'连接已断开；正在自动重试，这不是实时磁态。':e.message}`,true);syncViewMode();mode();}
 finally{clearTimeout(timeout);if(token===serial){document.body.setAttribute('aria-busy','false');inflight=null;if((following||scriptSource)&&!document.hidden)timer=setTimeout(()=>load(),scriptSource?2000:Math.min(30000,5000*2**unchanged));}}
}
$('frame').oninput=()=>{const step=state?.frames[Number($('frame').value)];pause();if(step!=null)load(step);};
for(const [id,delta]of[['prev',-1],['next',1]])$(id).onclick=()=>{if(!state?.frames.length)return;const i=Math.max(0,Math.min(state.frames.length-1,Number($('frame').value)+delta));pause();load(state.frames[i]);};
$('latest').onclick=()=>{if(following)pause();else{following=true;unchanged=0;mode();load();}};
$('refresh').onclick=()=>load();$('recover').onclick=()=>{following=true;unchanged=0;mode();load('latest');};$('reset').onclick=reset;$('stride').onchange=()=>load();
for(const button of document.querySelectorAll('[data-sub]'))button.onclick=()=>{for(const b of document.querySelectorAll('[data-sub]')){const active=b===button;b.classList.toggle('active',active);b.setAttribute('aria-pressed',String(active));}const sub=button.dataset.sub;$('panelA').hidden=sub==='B';$('panelB').hidden=sub==='A';resize();};
document.addEventListener('visibilitychange',()=>{const audit=JSON.parse(document.body.dataset.visibilityAudit||'[]');audit.push({hidden:document.hidden,unix_ms:Date.now(),...counters});document.body.dataset.visibilityAudit=JSON.stringify(audit.slice(-4));if(document.hidden){cancel();mode();}else{mode();if(following){unchanged=0;load();}}});
window.addEventListener('pagehide',cancel);
window.previewDiagnostics=()=>({scriptSource,instance:bindingState?.instance,frameSeq:shown?.frame_seq,stageEpoch:bindingState?.stage_epoch,step:shown?.step,following,hidden:document.hidden,pollDelayMs:Math.min(30000,5000*2**unchanged),...counters,views:views.map(v=>({calls:v.renderer.info.render.calls,geometries:v.renderer.info.memory.geometries,instances:v.meshes.map(m=>m.count)}))});
$('viewMode').onchange=()=>{
 cancel();const modeName=$('viewMode').value;$('stride').value=densityByMode[modeName];
 const cached=viewFrames[modeName],target=following?state?.checkpoint_step:selectedFrame;
 shown=cached&&cached._viewerKey===key(bindingState)&&(cached.frame_seq??cached.step)===target&&state?.frames.includes(target)?cached:null;
 syncViewMode();if(shown){status(state?.failure??'',Boolean(state?.failure));build(shown);paintFrame(shown);render();if(following)timer=setTimeout(()=>load(),5000);}
 else{$('sampleCount').textContent='';$('frameTime').textContent='正在读取磁态…';$('configValues').textContent='正在读取对应帧参数…';load(selectedFrame);}
};
$('component').onchange=()=>{if(shown){build(shown);render();}};
mode();load();


function axisLabels(v,base,length){
 for(const [i,label,tint]of [[0,'+X','#ff7777'],[1,'+Y','#77ff77'],[2,'+Z','#88aaff']]){
  const c=document.createElement('canvas');c.width=128;c.height=64;const ctx=c.getContext('2d');ctx.fillStyle=tint;ctx.font='bold 40px sans-serif';ctx.fillText(label,10,48);
  const material=new T.SpriteMaterial({map:new T.CanvasTexture(c),depthTest:false});const sprite=new T.Sprite(material);sprite.position.copy(base);sprite.position.setComponent(i,sprite.position.getComponent(i)+length*1.2);sprite.scale.set(length*.7,length*.35,1);v.scene.add(sprite);
 }
}
function paintDiagnostics(s,frame=null){
 if(!s.new_api)return;
 const historical=!following&&frame&&frame.frame_seq!==s.checkpoint_step;
 const p=historical?frame.progress:s.progress,el=$('convergence');el.hidden=false;el.replaceChildren();
 const title=document.createElement('div');title.textContent=historical?`历史帧指标 · 接受步 ${frame.step}（上方为当前求解进度）`:'当前接受态指标';el.append(title);
 if(!p){title.textContent+=' · 暂无指标快照';return;}
 for(const g of p.convergence){
 const row=document.createElement('div');
 const q=g.mxh==null?'等待':sci(g.mxh),r=g.residual_Apm==null?'等待':sci(g.residual_Apm);
 row.textContent=`${g.label}   mxh ${q}（无量纲） · Residual ${r} A/m`;
 if(p.kind==='static')row.textContent+=` · 阈值 mxh ${g.mxh_limit==null?'未启用':sci(g.mxh_limit)} / Residual ${sci(g.residual_limit_Apm)} A/m · ${g.residual_pass&&g.mxh_pass!==false?'本态达标':'尚未达标'}`;
 el.append(row);
 }
 if(p.kind==='static'){const note=document.createElement('div');note.textContent=`连续达标 ${p.consecutive}/${p.consecutive_required} · ${p.phase==='converged'?'已收敛':'以求解器最终状态为准'}`;el.append(note);}
 if(historical){$('energy').textContent=sci(frame.energy_J);$('resA').textContent=sci(p.convergence[0]?.residual_Apm);$('resB').textContent=sci(p.convergence[1]?.residual_Apm);}
}
function paintGates(s){
 const el=$('convergence');if(!s.new_api){el.textContent='';el.hidden=true;}
 const initialized=['initialized','restored'].includes(s.phase);
 if(initialized){$('phase').textContent=s.phase==='restored'?'已恢复 · 待运行':'初态 · 未开始';$('progressTarget').textContent='';}else if(s.new_api)$('phase').textContent=({running:'运行中',completed:'已完成',converged:'已收敛',interrupted:'已中断',cancelled:'已中断',failed:'失败',initialized:'未开始'}[s.phase]??s.phase);
 document.querySelector('.physics').hidden=s.energy_J==null;
 $('stepsMetric').hidden=initialized||s.stage==='static';$('dtMetric').hidden=initialized||s.stage==='static'||s.dt_fs==null;
 document.querySelector('.metrics').classList.toggle('initial',initialized);
 for(const el of document.querySelectorAll('.metric:nth-child(n+4)'))el.hidden=initialized;
}
function draw2D(data){
 const drawStarted=performance.now();
 const g=data.geometry,[nx,ny,nz]=g.n,h=g.cell_nm,o=g.origin_nm,stride=data.stride;
 const layer=0;
 const sampledLayer=Math.floor(layer/stride)*stride;
 views.forEach((v,sub)=>{
  v.renderer.domElement.hidden=true;v.renderer.domElement.style.display='none';if(!v.heat){v.heat=document.createElement('canvas');v.heat.style.cssText='width:100%;height:100%';v.el.append(v.heat);}v.heat.hidden=false;v.heat.style.display='block';
  const c=v.heat,w=Math.max(1,v.el.clientWidth),height=Math.max(1,v.el.clientHeight);c.width=w;c.height=height;const ctx=c.getContext('2d');ctx.fillStyle='#101e30';ctx.fillRect(0,0,w,height);if(!data.vectors[sub])return;
  const pad=32,scale=Math.max(.001,Math.min((w-2*pad)/(nx*h[0]),(height-2*pad)/(ny*h[1]))),left=(w-nx*h[0]*scale)/2,top=(height-ny*h[1]*scale)/2;
  if(nx*ny>65536)throw Error('2D热图网格数量超限，未绘制。');
  if(!v.heatImage)v.heatImage=document.createElement('canvas');const image=v.heatImage,component=Number($('component').value);if(v.heatFrame!==data||v.heatComponent!==component){image.width=nx;image.height=ny;
  const imageContext=image.getContext('2d'),pixels=imageContext.createImageData(nx,ny),bytes=pixels.data;
  data.indices.forEach((idx,j)=>{const z=Math.floor(idx/(nx*ny));if(z!==sampledLayer)return;const x=idx%nx,y=Math.floor(idx/nx)%ny,value=Math.max(-1,Math.min(1,data.vectors[sub][j][component])),t=Math.abs(value),end=value<0?[33,102,172]:[178,24,43],rgb=end.map(c=>Math.round(247+(c-247)*t));
   for(let py=y;py<Math.min(ny,y+stride);py++)for(let px=x;px<Math.min(nx,x+stride);px++){const k=((ny-1-py)*nx+px)*4;bytes[k]=rgb[0];bytes[k+1]=rgb[1];bytes[k+2]=rgb[2];bytes[k+3]=255;}
  });imageContext.putImageData(pixels,0,0);v.heatFrame=data;v.heatComponent=component;}ctx.imageSmoothingEnabled=false;ctx.drawImage(image,left,top,nx*h[0]*scale,ny*h[1]*scale);
  ctx.strokeStyle='#57718b';ctx.strokeRect(left,top,nx*h[0]*scale,ny*h[1]*scale);
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
  const layer=0;
  const sampledLayer=Math.floor(layer/data.stride)*data.stride;
  count=data.indices.filter(idx=>Math.floor(idx/(nx*ny))===sampledLayer).length;
 }
 const visible=labels.filter((label,i)=>i<data.vectors.length&&(labels.length===1||selected==='both'||selected===label));
 const detail=visible.map(label=>`${label} ${number(count)}`).join('、');
 $('sampleCount').textContent=`${detail} · ${number(count*visible.length)} ${is2D?'显示点':'箭头'}`;
}
