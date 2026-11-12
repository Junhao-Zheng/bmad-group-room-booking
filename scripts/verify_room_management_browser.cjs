// Real browser management paths. Synthetic secrets remain in the private credential file.
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const [origin,credentialsFile,outputDir,executablePath]=process.argv.slice(2);
const STAGES=new Set(['startup','open','multiline','csrf','create-wait','unchanged','invalid','duplicate','capacity','unknown','session','member','existing-paths']);
let currentStage='startup';
function safeDiagnostic(error,stage=currentStage){
  const types=new Set(['AssertionError','Error','TypeError','TimeoutError','SyntaxError','RangeError']);
  let source=null;
  for(const line of String(error?.stack||'').split('\n')){
    if(!/^\s+at /.test(line))continue;
    const marker=line.lastIndexOf(__filename+':');if(marker<0)continue;
    const match=line.slice(marker+__filename.length+1).match(/^([0-9]+):([0-9]+)\)?$/);
    if(match&&Number(match[1])>0&&Number(match[1])<1000000&&Number(match[2])>0&&Number(match[2])<1000000){
      source={file:'scripts/verify_room_management_browser.cjs',line:Number(match[1]),column:Number(match[2])};break;
    }
  }
  return {stage:STAGES.has(stage)?stage:'startup',error_type:types.has(error?.name)?error.name:'Error',source};
}
function writeFailure(error,directory,stage=currentStage){
  const diagnostic=safeDiagnostic(error,stage);
  fs.writeFileSync(path.join(directory,'failure-diagnostics.json'),JSON.stringify(diagnostic,null,2));return diagnostic;
}
const roomKeys=['capacity','id','location','name'];
async function login(context,user){
  const page=await context.newPage();await page.goto(origin+'/login');
  await page.locator('#username').fill(user.username);await page.locator('#password').fill(user.password);
  await page.locator('#password').press('Enter');await page.waitForURL(origin+'/');return page;
}
async function settled(page){await page.waitForFunction(()=>!document.querySelector('#room-form').hasAttribute('aria-busy'));}
async function fill(page,value){for(const key of ['name','location','capacity'])await page.locator(`#room-${key}`).fill(String(value[key]));await page.locator('#room-confirm').check();}
async function draft(page){return page.locator('#room-form').evaluate(form=>Object.fromEntries(['name','location','capacity'].map(key=>[key,form.elements.namedItem(key).value])));}
async function main(){
  const {chromium}=require('playwright');
  const users=JSON.parse(fs.readFileSync(credentialsFile,'utf8')).users;
  assert.equal(require('playwright/package.json').version,'1.58.2');
  const browser=await chromium.launch({headless:true,...(executablePath?{executablePath}:{})});const results=[];
  try{
    for(const viewport of [{width:1280,height:800},{width:390,height:844}]){
      currentStage='startup';fs.writeFileSync(path.join(outputDir,'progress.json'),JSON.stringify({viewport,stage:currentStage}));
      const context=await browser.newContext({viewport}),page=await login(context,users[2]);
      const errors=[],network=[];let writes=0;
      page.on('pageerror',error=>errors.push(error.name));page.on('request',request=>{if(request.method()==='POST'&&request.url().includes('/api/admin/rooms'))writes++;});
      function stage(name){currentStage=STAGES.has(name)?name:'startup';fs.writeFileSync(path.join(outputDir,'progress.json'),JSON.stringify({viewport,stage:currentStage}));}
      async function capture(response,phase){const row={phase,path:new URL(response.url()).pathname,status:response.status(),body:await response.json()};network.push(row);fs.writeFileSync(path.join(outputDir,`network-${viewport.width}.json`),JSON.stringify(network,null,2));return row;}
      async function screenshot(name){const width=await page.evaluate(()=>({document:document.documentElement.scrollWidth,viewport:innerWidth}));assert.ok(width.document<=width.viewport);await page.screenshot({path:path.join(outputDir,`${name}-${viewport.width}.png`),fullPage:true});}
      stage('open');await page.locator('.primary-nav a[href="/admin"]').click();await page.waitForSelector('#room-form');
      assert.equal(await page.locator('#room-form-title').textContent(),'新增会议室');
      for(const name of ['name','location','capacity'])assert.equal(await page.locator(`label[for="room-${name}"]`).count(),1);
      await screenshot('admin-initial');
      stage('multiline');
      const capacityTexts=viewport.width===1280?['1e2','10.0','01']:['2e2','20.0','02'];
      for(const [index,newline] of ['\n','\r','\r\n'].entries()){
        const id=10+index,rawName=`合成多行 ${id}上${newline}下`,rawLocation=`东${newline}西`;
        await page.goto(origin+'/admin');await page.locator('#admin-rooms button').filter({hasText:new RegExp(`^编辑会议室 ${id}$`)}).click();
        assert.equal(await page.locator('#room-name').evaluate(node=>node.tagName),'TEXTAREA');
        assert.equal(await page.locator('#room-name').inputValue(),`合成多行 ${id}上\n下`);
        assert.equal(await page.locator('#room-location').inputValue(),'东\n西');
        await page.locator('#room-confirm').check();let unchangedResponse=page.waitForResponse(r=>r.url().endsWith(`/api/admin/rooms/${id}`));await page.locator('#room-submit').click();
        const multilineUnchanged=await capture(await unchangedResponse,`multiline-${index}-unchanged`);await settled(page);
        assert.equal(multilineUnchanged.status,200);assert.equal(multilineUnchanged.body.data.name,rawName);assert.equal(multilineUnchanged.body.data.location,rawLocation);
        // After the save's JSON refresh, edit through the newly rendered button too.
        await page.locator('#admin-rooms button').filter({hasText:new RegExp(`^编辑会议室 ${id}$`)}).click();
        await page.locator('#room-confirm').check();await page.locator('#room-capacity').fill(capacityTexts[index]);
        assert.equal(await page.locator('#room-confirm').isChecked(),false);const beforeConfirmation=writes;
        await page.locator('#room-submit').click();assert.equal(writes,beforeConfirmation);await page.locator('#room-confirm').check();
        const updateResponse=page.waitForResponse(r=>r.url().endsWith(`/api/admin/rooms/${id}`));await page.locator('#room-submit').click();
        const changed=await capture(await updateResponse,`multiline-${index}-capacity-only`);await settled(page);
        assert.equal(changed.status,200);assert.equal(changed.body.data.name,rawName);assert.equal(changed.body.data.location,rawLocation);
        assert.equal(changed.body.data.capacity,Number(capacityTexts[index]));
      }
      await page.locator('#room-cancel').click();
      const values={name:`<img src=x onerror="window.roomXss=1">新 ${viewport.width}`,location:'合成楼 <script>纯文本</script>',capacity:20};
      await fill(page,values);await page.locator('#room-confirm').uncheck();const beforeInitialConfirmation=writes;await page.locator('#room-submit').click();assert.equal(writes,beforeInitialConfirmation);
      await page.locator('#room-confirm').check();
      stage('csrf');
      await page.route('**/api/admin/rooms',async route=>{const headers=route.request().headers();delete headers['x-csrf-token'];await route.continue({headers});});
      let response=page.waitForResponse(r=>new URL(r.url()).pathname==='/api/admin/rooms');await page.locator('#room-submit').focus();await page.keyboard.press('Enter');
      assert.equal((await capture(await response,'csrf-rejected')).status,403);await settled(page);
      assert.deepEqual(await draft(page),{...values,capacity:'20'});assert.equal(await page.evaluate(()=>document.activeElement.id),'room-feedback');
      await screenshot('csrf-rejected');await page.unroute('**/api/admin/rooms');
      stage('create-wait');let release;const gate=new Promise(resolve=>{release=resolve;});
      await page.route('**/api/admin/rooms',async route=>{await gate;await route.continue();});
      response=page.waitForResponse(r=>new URL(r.url()).pathname==='/api/admin/rooms');await page.locator('#room-submit').click();
      assert.equal(await page.locator('#room-name').isDisabled(),true);assert.equal(await page.locator('#rooms-refresh').isDisabled(),true);
      await screenshot('saving');await page.locator('#logout-form button').focus();release();
      const created=await capture(await response,'created');assert.equal(created.status,201);await settled(page);
      assert.equal(await page.evaluate(()=>document.activeElement===document.querySelector('#logout-form button')),true);
      assert.deepEqual(Object.keys(created.body.data).sort(),roomKeys);
      assert.equal(await page.locator('#admin-rooms img,#admin-rooms script').count(),0);assert.equal(await page.evaluate(()=>window.roomXss),undefined);
      await screenshot('created-plain-text');await page.unroute('**/api/admin/rooms');
      stage('unchanged');await page.locator('#room-confirm').check();response=page.waitForResponse(r=>r.url().endsWith(`/api/admin/rooms/${created.body.data.id}`));
      await page.locator('#room-submit').click();const unchanged=await capture(await response,'unchanged');await settled(page);assert.deepEqual(unchanged.body,created.body);
      stage('invalid');await page.locator('#room-name').fill('长'.repeat(81));await page.locator('#room-confirm').check();
      response=page.waitForResponse(r=>r.url().endsWith(`/api/admin/rooms/${created.body.data.id}`));await page.locator('#room-submit').click();
      assert.equal((await capture(await response,'field-invalid')).status,400);await settled(page);
      assert.equal(await page.evaluate(()=>document.activeElement.id),'room-name');assert.equal(await page.locator('#room-name').inputValue(),'长'.repeat(81));await screenshot('field-invalid');
      stage('duplicate');await page.locator('#room-cancel').click();await fill(page,values);response=page.waitForResponse(r=>new URL(r.url()).pathname==='/api/admin/rooms');
      await page.locator('#room-submit').click();assert.equal((await capture(await response,'duplicate')).status,409);await settled(page);assert.deepEqual(await draft(page),{...values,capacity:'20'});await screenshot('duplicate');
      stage('capacity');const target=viewport.width===1280?1:2;
      await page.locator('#admin-rooms button').filter({hasText:new RegExp(`^编辑会议室 ${target}$`)}).click();
      const edited={name:`管理修改 ${viewport.width}`,location:'新地点',capacity:4};await fill(page,edited);
      response=page.waitForResponse(r=>r.url().endsWith(`/api/admin/rooms/${target}`));await page.locator('#room-submit').click();
      const conflict=await capture(await response,'capacity-conflict');assert.equal(conflict.status,409);await settled(page);
      assert.deepEqual(Object.keys(conflict.body.error.conflicts[0]).sort(),['attendees','end_at','end_local','id','reason','room_id','start_at','start_local','status','type']);
      assert.deepEqual(await draft(page),{...edited,capacity:'4'});
      const renderedConflicts=await page.locator('#room-conflicts li').allTextContents();
      assert.deepEqual(renderedConflicts,conflict.body.error.conflicts.map(row=>`预约 ${row.id} · ${row.attendees} 人 · 北京时间 ${row.start_local.replace('T',' ').slice(0,19)} 至 ${row.end_local.replace('T',' ').slice(0,19)} · ${row.status==='in_progress'?'进行中':'待开始'}`));
      assert.equal(renderedConflicts[0],`预约 ${target===1?102:201} · 5 人 · 北京时间 2026-11-12 10:00:00 至 2026-11-12 11:00:00 · 进行中`);await screenshot('capacity-conflict');
      await page.locator('#room-capacity').fill('5');
      assert.equal(await page.locator('#room-confirm').isChecked(),false);const beforeReconfirm=writes;await page.locator('#room-submit').click();assert.equal(writes,beforeReconfirm);
      await page.locator('#room-confirm').check();response=page.waitForResponse(r=>r.url().endsWith(`/api/admin/rooms/${target}`));await page.locator('#room-submit').click();
      const changed=await capture(await response,'equal-capacity-saved');assert.equal(changed.status,200);assert.equal(changed.body.data.id,target);await settled(page);await screenshot('updated');
      stage('unknown');await page.locator('#room-cancel').click();const unknown={name:`响应未知房间 ${viewport.width}`,location:'临时楼',capacity:8};await fill(page,unknown);
      await page.route('**/api/admin/rooms',async route=>{await capture(await route.fetch(),'committed-response-dropped');await route.abort();});
      const beforeUnknown=writes;await page.locator('#room-submit').click();await page.waitForFunction(()=>document.querySelector('#room-feedback').textContent.includes('未能确认'));await settled(page);
      assert.equal(writes,beforeUnknown+1);assert.deepEqual(await draft(page),{...unknown,capacity:'8'});await screenshot('response-unknown');await page.unroute('**/api/admin/rooms');
      await page.locator('#rooms-refresh').click();await settled(page);assert.deepEqual(await draft(page),{...unknown,capacity:'8'});
      assert.ok((await page.locator('#admin-rooms').textContent()).includes(unknown.name));assert.equal(writes,beforeUnknown+1);
      stage('session');const csrf=(await (await context.request.get(origin+'/api/me')).json()).data.csrf_token;
      assert.equal((await context.request.post(origin+'/api/logout',{data:{},headers:{Origin:origin,'X-CSRF-Token':csrf}})).status(),200);
      response=page.waitForResponse(r=>new URL(r.url()).pathname==='/api/admin/rooms');await page.locator('#room-submit').click();
      assert.equal((await capture(await response,'session-expired')).status,401);await settled(page);
      assert.deepEqual(await draft(page),{...unknown,capacity:'8'});assert.equal(await page.locator('#room-relogin').isVisible(),true);assert.equal(await page.locator('#room-submit').isDisabled(),true);await screenshot('session-expired');
      stage('member');const memberContext=await browser.newContext({viewport}),memberPage=await login(memberContext,users[0]);
      assert.equal(await memberPage.locator('.primary-nav a[href="/admin"]').count(),0);
      const denied=await memberContext.request.get(origin+'/admin');assert.equal(denied.status(),403);
      const memberCsrf=(await (await memberContext.request.get(origin+'/api/me')).json()).data.csrf_token;
      assert.equal((await memberContext.request.post(origin+'/api/admin/rooms',{data:values,headers:{Origin:origin,'X-CSRF-Token':memberCsrf}})).status(),403);
      // Existing directory, day schedule and personal history remain operable.
      stage('existing-paths');await memberPage.locator('#room_id').selectOption(String(target));await memberPage.locator('#date').fill('2026-11-12');
      const scheduleResponse=memberPage.waitForResponse(r=>new URL(r.url()).pathname==='/api/schedule');await memberPage.locator('#schedule-form button[type=submit]').click();
      assert.equal((await capture(await scheduleResponse,'existing-schedule')).status,200);
      await memberPage.locator('.primary-nav a[href="/my"]').click();await memberPage.waitForSelector('#history-items button');
      await memberPage.locator('#logout-form button').focus();await memberPage.keyboard.press('Enter');await memberPage.waitForURL(origin+'/login?logged_out=1');
      assert.equal((await memberContext.request.get(origin+'/api/rooms')).status(),401);
      assert.deepEqual(errors,[]);results.push({viewport,normal_rejected_unknown_and_session_paths:true,keyboard_focus:true,no_horizontal_overflow:true,exact_dto_and_plain_text:true,writes});
      await memberContext.close();await context.close();
    }
  }finally{await browser.close();}
  console.log(JSON.stringify({result:'PASS',viewports:results}));
}
module.exports={safeDiagnostic,writeFailure};
if(require.main===module)main().catch(error=>{writeFailure(error,outputDir);process.exitCode=1;});
