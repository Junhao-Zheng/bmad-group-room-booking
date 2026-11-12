// Record real elapsed browser activity. Final scene data must reference audited facts.
const {chromium}=require('playwright');
const fs=require('node:fs');const path=require('node:path');const assert=require('node:assert/strict');
const {performance}=require('node:perf_hooks');
const wait=ms=>new Promise(resolve=>setTimeout(resolve,ms));
(async()=>{
 const [dataFile,processOrigin,appOrigin,credentialsFile,outputDirectory,executable]=process.argv.slice(2);
 const preflight=process.argv.includes('--preflight');
 const data=JSON.parse(fs.readFileSync(dataFile,'utf8'));assert.equal(data.scenes.length,12);
 assert.equal(data.status,'FINAL_AUDITED');assert.ok(/^[0-9a-f]{40}$/.test(data.source_commit));assert.ok(!JSON.stringify(data.scenes).includes('{{'));
 const users=JSON.parse(fs.readFileSync(credentialsFile,'utf8')).users;
 const output=path.resolve(outputDirectory);fs.mkdirSync(output,{recursive:true});
 const report={result:'INCOMPLETE',started_at_utc:new Date().toISOString(),scenes:[],mode:preflight?'preflight':'recording',synthetic_narration:true,operator:'AI automation',source_commit:data.source_commit};
 const write=()=>fs.writeFileSync(path.join(output,'recording.json'),JSON.stringify(report,null,2)+'\n');write();
 const browser=await chromium.launch({headless:true,executablePath:executable});
 const context=await browser.newContext({viewport:null,...(preflight?{}:{recordVideo:{dir:path.join(output,'raw-video'),size:{width:1280,height:800}}})});
 let page;
 async function login(username){
  const me=await context.request.get(appOrigin+'/api/me');
  if(me.ok()){
   const body=await me.json();const out=await context.request.post(appOrigin+'/api/logout',{headers:{Origin:appOrigin,'X-CSRF-Token':body.data.csrf_token},data:{}});assert.equal(out.status(),200);
  }
  const user=users.find(u=>u.username===username);assert.ok(user);
  const html=await (await context.request.get(appOrigin+'/login')).text();
  const csrf=html.match(/name="csrf_token" value="([^"]+)"/)[1];
  const result=await context.request.post(appOrigin+'/api/login',{headers:{Origin:appOrigin,'X-CSRF-Token':csrf},data:{username:user.username,password:user.password}});assert.equal(result.status(),200);
 }
 try{
  await login('demo_member_a'); // Authentication happens before visible recording; no password in frames.
  page=await context.newPage();
  // Size the native content area: current Chrome screencast can clip an emulated viewport.
  const cdp=await context.newCDPSession(page);
  const {windowId}=await cdp.send('Browser.getWindowForTarget');
  const insets=await page.evaluate(()=>({width:outerWidth-innerWidth,height:outerHeight-innerHeight}));
  await cdp.send('Browser.setWindowBounds',{windowId,bounds:{width:1280+insets.width,height:800+insets.height}});
  await page.waitForFunction(()=>innerWidth===1280&&innerHeight===800);
  report.viewport=await page.evaluate(()=>({width:innerWidth,height:innerHeight,outerWidth,outerHeight,devicePixelRatio}));
  await cdp.detach();write();
  const errors=[];page.on('pageerror',error=>errors.push(error.name));
  const start=performance.now();
  for(let i=0;i<12;i++){
   const scene=data.scenes[i];if(scene.username)await login(scene.username);
   const began=performance.now();
   const url=scene.app_path?appOrigin+scene.app_path:processOrigin+'/#'+i;
   await page.goto(url,{waitUntil:'networkidle'});
   for(const action of scene.actions??[]){
    if(action.kind==='pause'){assert.ok(Number.isInteger(action.milliseconds)&&action.milliseconds>=0&&action.milliseconds<=10000);await wait(preflight?Math.min(action.milliseconds,100):action.milliseconds);continue;}
    const node=page.locator(action.selector);
    if(action.kind==='fill')await node.fill(action.value);
    else if(action.kind==='select')await node.selectOption(action.value);
    else if(action.kind==='click')await node.click();
    else if(action.kind==='text')assert.ok((await node.textContent()).includes(action.value));
    else if(action.kind==='wait_text')await node.filter({hasText:action.value}).waitFor({state:'visible'});
    else if(action.kind==='scroll')await node.scrollIntoViewIfNeeded();
    else throw new Error('Unknown recording action');
   }
   assert.deepEqual(errors,[]);
   const overflow=await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth);assert.equal(overflow,false);
   await page.screenshot({path:path.join(output,`scene-${String(i+1).padStart(2,'0')}.png`)});
   const item={index:i+1,title:scene.title,actual_started_seconds:(began-start)/1000,actions_complete_seconds:(performance.now()-start)/1000,route:scene.app_path??`process#${i}`};
   report.scenes.push(item);write();console.log(JSON.stringify({scene:i+1,result:'actions_verified',elapsed_seconds:item.actions_complete_seconds}));
   const remaining=preflight?0:(i+1)*50000-(performance.now()-start);
   if(remaining<0)throw new Error('Scene actions exceeded the real recording slot');
   await wait(remaining);item.actual_ended_seconds=(performance.now()-start)/1000;write();
  }
  // Keep a real final frame briefly; later trim only surplus, never stretch a shorter video.
  await wait(preflight?0:1000);
  report.actual_recording_seconds=(performance.now()-start)/1000;if(!preflight)assert.ok(report.actual_recording_seconds>=600);
  const video=page.video();await page.close();await context.close();
  if(!preflight)await video.saveAs(path.join(output,'actual-browser.webm'));
  report.browser=await browser.version();report.node=process.version;report.playwright=require('playwright/package.json').version;
  report.result='PASS';report.completed_at_utc=new Date().toISOString();write();
 }finally{await browser.close();}
})().catch(error=>{console.error(JSON.stringify({error_type:error.name,message:'Recording failed; raw credential-bearing diagnostics omitted'}));process.exitCode=1;});
