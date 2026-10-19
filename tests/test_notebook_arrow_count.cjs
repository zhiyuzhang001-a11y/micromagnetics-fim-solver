// Targeted zero-field browser check. Uses its own Chrome profile and fixture only.
const {spawn}=require('node:child_process');
const fs=require('node:fs'),assert=require('node:assert/strict'),readline=require('node:readline');
const {chromium}=require('playwright');
const out=(process.env.CI_RESULTS||'ci-results');
fs.mkdirSync(out,{recursive:true});
const child=spawn(process.env.PYTHON||'python',[process.cwd()+'/tests/notebook_usability_viewer_fixture.py','3'],{stdio:['pipe','pipe','inherit']});
const lines=readline.createInterface({input:child.stdout});let queue=[],waiters=[];
lines.on('line',s=>{const value=JSON.parse(s);if(waiters.length)waiters.shift()(value);else queue.push(value);});
const next=()=>queue.length?Promise.resolve(queue.shift()):new Promise(resolve=>waiters.push(resolve));
child.on('exit',code=>{if(code){console.error('fixture failed '+code);process.exitCode=1;}});
(async()=>{let browser;const observations=[];try{
 const ready=await next();browser=await chromium.launch({headless:true,args:['--use-gl=angle','--use-angle=swiftshader','--enable-unsafe-swiftshader']});
 const page=await browser.newPage({viewport:{width:1440,height:1000}});const errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.goto(ready.url);await page.waitForFunction(()=>window.previewDiagnostics?.().frameLoads>=1);await page.locator('#latest').click();
 async function check(expected){
  const label=page.locator('#sampleCount');await label.waitFor({state:'visible'});assert.equal(await label.innerText(),expected);
  observations.push({text:expected,visible:await label.isVisible(),diagnostics:await page.evaluate(()=>window.previewDiagnostics())});
 }
 await page.locator('#stride').selectOption('1');await page.waitForFunction(()=>window.previewDiagnostics().views[0].instances[0]===9);
 await check('A 9、B 9 · 18 箭头');
 const requests1=await page.evaluate(()=>window.previewDiagnostics().frameLoads);
 await page.locator('[data-sub="A"]').click();await check('A 9 · 9 箭头');
 await page.locator('[data-sub="B"]').click();await check('B 9 · 9 箭头');
 assert.equal(await page.evaluate(()=>window.previewDiagnostics().frameLoads),requests1);
 await page.locator('[data-sub="both"]').click();await page.locator('#stride').selectOption('2');await page.waitForFunction(()=>window.previewDiagnostics().views[0].instances[0]===4);
 await check('A 4、B 4 · 8 箭头');await page.screenshot({path:out+'/arrow-count-3d-headless.png'});
 const requests2=await page.evaluate(()=>window.previewDiagnostics().frameLoads);
 await page.locator('[data-sub="A"]').click();await check('A 4 · 4 箭头');
 await page.locator('[data-sub="B"]').click();await check('B 4 · 4 箭头');
 await page.locator('#viewMode').selectOption('2d');await page.locator('#stride').selectOption('2');await page.waitForFunction(()=>document.getElementById('sampleCount').textContent==='B 4 · 4 显示点');await check('B 4 · 4 显示点');
 await page.locator('[data-sub="both"]').click();await check('A 4、B 4 · 8 显示点');
 assert((await page.evaluate(()=>window.previewDiagnostics().frameLoads))>requests2);
 await page.screenshot({path:out+'/arrow-count-2d-headless.png'});child.stdin.write('metrics\n');const metrics=await next();
 assert.deepEqual(metrics.fields,{fm:0,fim:0});assert.deepEqual(errors,[]);
 const receipt={status:'passed',scope:'3x3x1 cached accepted-state UI; independent headless Chrome; not user foreground GUI',observations,metrics,errors,sub_switch_extra_frames:0,view_switch_requires_bound_packet:true};
 fs.writeFileSync(out+'/ARROW_COUNT_UI.json',JSON.stringify(receipt,null,2));console.log(JSON.stringify(receipt));
 }finally{if(browser)await browser.close();child.stdin.write('close\n');setTimeout(()=>child.kill(),2000).unref();}})().catch(error=>{console.error(error);process.exitCode=1;});
