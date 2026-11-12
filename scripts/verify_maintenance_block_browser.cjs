// Real Chromium paths on an isolated Waitress instance; credentials remain private.
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const [origin,credentialsFile,outputDir,executablePath]=process.argv.slice(2);
const {assertRendered}=require('../tests/maintenance_render_contract.cjs');
const STAGES=new Set(['startup','open','no-script','room-options','lists','query-errors','csrf','create-wait','invalid','conflict','unknown','session','member','existing-paths']);
let currentStage='startup';
function safeDiagnostic(error,stage=currentStage){
  const types=new Set(['AssertionError','Error','TypeError','TimeoutError','SyntaxError','RangeError']);let source=null;
  for(const line of String(error?.stack||'').split('\n')){
    if(!/^\s+at /.test(line))continue;const marker=line.lastIndexOf(__filename+':');if(marker<0)continue;
    const match=line.slice(marker+__filename.length+1).match(/^([0-9]+):([0-9]+)\)?$/);
    if(match&&Number(match[1])>0&&Number(match[1])<1000000&&Number(match[2])>0&&Number(match[2])<1000000){source={file:'scripts/verify_maintenance_block_browser.cjs',line:Number(match[1]),column:Number(match[2])};break;}
  }
  return {stage:STAGES.has(stage)?stage:'startup',error_type:types.has(error?.name)?error.name:'Error',source};
}
async function login(context,user){
  const page=await context.newPage();await page.goto(origin+'/login');await page.locator('#username').fill(user.username);
  await page.locator('#password').fill(user.password);await page.locator('#password').press('Enter');await page.waitForURL(origin+'/');return page;
}
async function settled(page){await page.waitForFunction(()=>!document.querySelector('#block-form').hasAttribute('aria-busy'));}
async function fill(page,values){for(const name of ['room_id','start','end','reason']){const field=page.locator('#block-'+name);if(name==='room_id')await field.selectOption(String(values[name]));else await field.fill(values[name]);}await page.locator('#block-confirm').check();}
async function draft(page){return page.locator('#block-form').evaluate(form=>Object.fromEntries(['room_id','start','end','reason'].map(name=>[name,form.elements.namedItem(name).value])));}
const blockKeys='id,room,creator_id,creator_display_name,reason,start_at,start_local,end_at,end_local,status,created_at,created_local,revoked_at,revoked_local,revoked_by_id,revoked_by_display_name,revoke_reason'.split(',').sort();
const bookingKeys='id,room,title,purpose,attendees,owner_id,owner_display_name,start_at,start_local,end_at,end_local,status,created_at,created_local,cancelled_at,cancelled_local,cancelled_by_id,cancelled_by_display_name,cancel_reason'.split(',').sort();
async function assertVisibleRows(page,kind,records){
  const actual=await page.locator(`#admin-${kind}-items > li`).evaluateAll(items=>items.map(item=>({
    title:item.querySelector('h3').textContent,pairs:[...item.querySelectorAll('dl > dt')].map(dt=>[dt.textContent,dt.nextElementSibling.textContent])
  })));
  assertRendered(actual,records,kind);
}
async function main(){
  const {chromium}=require('playwright');assert.equal(require('playwright/package.json').version,'1.58.2');
  const users=JSON.parse(fs.readFileSync(credentialsFile,'utf8')).users;
  const browser=await chromium.launch({headless:true,...(executablePath?{executablePath}:{})}),results=[];
  try{
    for(const viewport of [{width:1280,height:800},{width:390,height:844}]){
      const context=await browser.newContext({viewport}),page=await login(context,users[2]),network=[],errors=[];let writes=0;
      page.on('pageerror',error=>errors.push(error.name));page.on('request',request=>{if(request.method()==='POST'&&new URL(request.url()).pathname==='/api/admin/blocks')writes++;});
      function stage(name){currentStage=name;fs.writeFileSync(path.join(outputDir,'progress.json'),JSON.stringify({viewport,stage:name}));}
      async function capture(response,phase){const row={phase,path:new URL(response.url()).pathname,status:response.status(),body:await response.json()};network.push(row);fs.writeFileSync(path.join(outputDir,`network-${viewport.width}.json`),JSON.stringify(network,null,2));return row;}
      async function screenshot(name){const size=await page.evaluate(()=>({document:document.documentElement.scrollWidth,viewport:innerWidth}));assert.ok(size.document<=size.viewport);await page.screenshot({path:path.join(outputDir,`${name}-${viewport.width}.png`),fullPage:true});}
      async function query(kind,phase){const response=page.waitForResponse(r=>r.request().method()==='GET'&&new URL(r.url()).pathname==='/api/admin/'+kind);await page.locator(`#admin-${kind}-submit`).click();const row=await capture(await response,phase);await page.waitForFunction(kind=>!document.querySelector(`#admin-${kind}-form`).hasAttribute('aria-busy'),kind);if(row.status===200)await assertVisibleRows(page,kind,row.body.data.items);return row;}
      stage('no-script');const inertContext=await browser.newContext({viewport,storageState:await context.storageState(),javaScriptEnabled:false});
      const inertPage=await inertContext.newPage();await inertPage.goto(origin+'/admin');
      assert.equal(await inertPage.locator('#block-fields').getAttribute('disabled'),'');assert.equal(await inertPage.locator('#block-reason').isDisabled(),true);assert.equal(await inertPage.locator('#block-submit').isDisabled(),true);
      assert.equal(await inertPage.locator('#block-script-unavailable').isVisible(),true);
      const inertRequests=[];inertPage.on('request',request=>inertRequests.push(request.url()));
      await inertPage.locator('#block-reason').evaluate(input=>{input.value='PRIVATE_REASON_JS_DISABLED';});
      await inertPage.locator('#block-submit').click({force:true});await inertPage.locator('body').press('Enter');
      assert.equal(inertPage.url(),origin+'/admin');assert.deepEqual(inertRequests,[]);
      await inertContext.close();
      stage('open');await page.locator('.primary-nav a[href="/admin"]').click();await page.waitForSelector('#block-form');
      assert.match(await page.locator('#admin-blocks-feedback').textContent(),/尚未查询/);assert.match(await page.locator('#admin-bookings-feedback').textContent(),/尚未查询/);
      for(const name of ['room_id','start','end','reason'])assert.equal(await page.locator(`label[for="block-${name}"]`).count(),1);
      await screenshot('initial');
      stage('lists');
      for(const kind of ['bookings','blocks']){
        const all=await query(kind,'full-'+kind);assert.equal(all.status,200);assert.ok(all.body.data.total>0);
        for(const row of all.body.data.items)assert.deepEqual(Object.keys(row).sort(),kind==='blocks'?blockKeys:bookingKeys);
        assert.equal(await page.locator(`#admin-${kind}-items img,#admin-${kind}-items svg,#admin-${kind}-items script`).count(),0);
        for(const status of ['pending','in_progress','ended',kind==='blocks'?'revoked':'cancelled']){
          await page.locator(`#admin-${kind}-status`).selectOption(status);assert.equal(await page.locator(`#admin-${kind}-items > li`).count(),0);assert.match(await page.locator(`#admin-${kind}-feedback`).textContent(),/条件已更改/);const filtered=await query(kind,kind+'-'+status);
          assert.ok(filtered.body.data.items.length);assert.ok(filtered.body.data.items.every(row=>row.status===status));
        }
        await page.locator(`#admin-${kind}-status`).selectOption('');
      }
      await page.locator('#admin-blocks-date').fill('2025-01-01');const empty=await query('blocks','empty');assert.equal(empty.body.data.total,0);
      assert.match(await page.locator('#admin-blocks-feedback').textContent(),/没有符合条件/);await screenshot('empty');await page.locator('#admin-blocks-date').fill('');
      stage('query-errors');
      assert.equal(await page.locator('#admin-blocks-date').getAttribute('max'),'9999-12-30');
      for(const name of ['date','room_id','status']){
        const input=page.locator('#admin-blocks-'+name);
        if(name==='date'){await input.evaluate(node=>node.removeAttribute('max'));await input.fill('9999-12-31');}
        else {await input.evaluate(node=>{const option=document.createElement('option');option.value='invalid';option.textContent='合成非法值';node.append(option);});await input.selectOption('invalid');}
        const rejected=await query('blocks','query-field-'+name);assert.equal(rejected.status,400);
        assert.equal(await input.getAttribute('aria-invalid'),'true');assert.equal(await input.isDisabled(),false);
        assert.equal(await page.evaluate(()=>document.activeElement.id),'admin-blocks-'+name);
        assert.equal(await page.locator('#admin-blocks-'+name+'-error').textContent(),rejected.body.error.fields[name]);
        if(name==='date'){await input.fill('');await input.evaluate(node=>node.max='9999-12-30');}else await input.selectOption('');
        assert.equal(await input.getAttribute('aria-invalid'),null);await query('blocks','corrected-'+name);
      }
      let release;const gate=new Promise(resolve=>{release=resolve;});await page.route('**/api/admin/blocks?*',async route=>{await gate;await route.continue();});
      const pendingQuery=query('blocks','list-wait');await page.waitForFunction(()=>document.querySelector('#admin-blocks-form').hasAttribute('aria-busy'));
      assert.match(await page.locator('#admin-blocks-feedback').textContent(),/正在加载/);assert.equal(await page.locator('#block-submit').isDisabled(),true);
      await screenshot('list-loading');await page.locator('#room-name').focus();release();await pendingQuery;assert.equal(await page.evaluate(()=>document.activeElement.id),'room-name');await page.unroute('**/api/admin/blocks?*');
      const day=viewport.width===1280?'13':'17',next=viewport.width===1280?'14':'18';
      const values={room_id:'30',start:`2026-11-${day}T10:00`,end:`2026-11-${next}T16:00`,reason:`<img src=x onerror="window.blockXss=1">维护 ${viewport.width}`};
      await fill(page,values);
      stage('room-options');await page.locator('#admin-bookings-room_id').selectOption('30');await page.locator('#admin-blocks-room_id').selectOption('30');
      const keptDraft=await draft(page),newRoom={name:`新增选项 ${viewport.width} <房间>`,location:'新测试楼',capacity:9};
      for(const name of ['name','location','capacity'])await page.locator('#room-'+name).fill(String(newRoom[name]));await page.locator('#room-confirm').check();
      let roomResponse=page.waitForResponse(r=>r.request().method()==='POST'&&new URL(r.url()).pathname==='/api/admin/rooms');await page.locator('#room-submit').click();
      const roomCreated=await capture(await roomResponse,'new-room-for-options');assert.equal(roomCreated.status,201);
      await page.waitForFunction(()=>!document.querySelector('#room-form').hasAttribute('aria-busy'));
      roomResponse=page.waitForResponse(r=>r.request().method()==='GET'&&new URL(r.url()).pathname==='/api/rooms');await page.locator('#block-rooms-refresh').click();await capture(await roomResponse,'room-option-refresh');
      await page.waitForFunction(()=>document.querySelector('#block-rooms-feedback').textContent.includes('选项已刷新'));
      for(const selector of ['#block-room_id','#admin-bookings-room_id','#admin-blocks-room_id']){
        assert.equal(await page.locator(selector).inputValue(),'30');
        assert.equal(await page.locator(`${selector} option[value="${roomCreated.body.data.id}"]`).textContent(),`${newRoom.name} · ${newRoom.location}`);
      }
      assert.deepEqual(await draft(page),keptDraft);assert.equal(await page.locator('#block-confirm').isChecked(),false);
      assert.match(await page.locator('#block-summary').textContent(),/停用原因.*<img/);
      await page.locator('#block-confirm').uncheck();const beforeUnconfirmed=writes;await page.locator('#block-submit').click();assert.equal(writes,beforeUnconfirmed);await page.locator('#block-confirm').check();
      stage('csrf');await page.route('**/api/admin/blocks',async route=>{const headers=route.request().headers();delete headers['x-csrf-token'];await route.continue({headers});});
      let response=page.waitForResponse(r=>r.request().method()==='POST'&&new URL(r.url()).pathname==='/api/admin/blocks');await page.locator('#block-submit').click();
      assert.equal((await capture(await response,'csrf')).status,403);await settled(page);assert.deepEqual(await draft(page),values);await screenshot('csrf-rejected');await page.unroute('**/api/admin/blocks');
      stage('create-wait');const createGate=new Promise(resolve=>{release=resolve;});await page.route('**/api/admin/blocks',async route=>{await createGate;await route.continue();});
      response=page.waitForResponse(r=>r.request().method()==='POST'&&new URL(r.url()).pathname==='/api/admin/blocks');await page.locator('#block-submit').focus();await page.keyboard.press('Enter');
      assert.equal(await page.locator('#block-reason').isDisabled(),true);assert.equal(await page.locator('#admin-blocks-submit').isDisabled(),true);await screenshot('creating');
      await page.locator('#room-name').focus();release();const created=await capture(await response,'created');assert.equal(created.status,201);await settled(page);
      assert.equal(await page.evaluate(()=>document.activeElement.id),'room-name');assert.deepEqual(Object.keys(created.body.data).sort(),blockKeys);
      assert.equal(await page.locator('#admin-blocks-items img,#admin-blocks-items script').count(),0);assert.equal(await page.evaluate(()=>window.blockXss),undefined);
      assert.ok((await page.locator('#admin-blocks-items').textContent()).includes(values.reason));await screenshot('created');await page.unroute('**/api/admin/blocks');
      stage('conflict');await page.locator('#block-confirm').check();response=page.waitForResponse(r=>r.request().method()==='POST'&&new URL(r.url()).pathname==='/api/admin/blocks');await page.locator('#block-submit').click();
      const conflict=await capture(await response,'block-conflict');assert.equal(conflict.status,409);await settled(page);assert.deepEqual(await draft(page),values);
      assert.ok((await page.locator('#block-conflicts').textContent()).includes(values.reason));await screenshot('block-conflict');
      await fill(page,{room_id:'10',start:'2026-11-12T11:00',end:'2026-11-12T12:00',reason:'与原预约冲突'});
      response=page.waitForResponse(r=>r.request().method()==='POST'&&new URL(r.url()).pathname==='/api/admin/blocks');await page.locator('#block-submit').click();
      const bookingConflict=await capture(await response,'booking-conflict');assert.equal(bookingConflict.status,409);await settled(page);assert.match(await page.locator('#block-conflicts').textContent(),/预约 107.*5 人/);await screenshot('booking-conflict');
      stage('invalid');await fill(page,{...values,reason:'长'.repeat(501)});response=page.waitForResponse(r=>r.request().method()==='POST'&&new URL(r.url()).pathname==='/api/admin/blocks');await page.locator('#block-submit').click();
      assert.equal((await capture(await response,'invalid')).status,400);await settled(page);assert.equal(await page.evaluate(()=>document.activeElement.id),'block-reason');assert.equal((await page.locator('#block-reason').inputValue()).length,501);await screenshot('invalid');
      stage('unknown');const unknown={...values,start:`2026-11-${next}T16:00`,end:`2026-11-${next}T17:00`,reason:'响应未知维护'};await fill(page,unknown);
      let committedUnknown;await page.route('**/api/admin/blocks',async route=>{const saved=await capture(await route.fetch(),'committed-response-dropped');assert.equal(saved.status,201);committedUnknown=saved.body.data;await route.abort();});
      const beforeUnknown=writes;await page.locator('#block-submit').click();await page.waitForFunction(()=>document.querySelector('#block-feedback').textContent.includes('未能确认'));await settled(page);
      assert.equal(writes,beforeUnknown+1);assert.deepEqual(await draft(page),unknown);await screenshot('unknown');await page.unroute('**/api/admin/blocks');
      assert.equal(await page.locator('#block-confirm').isChecked(),false);await page.locator('#block-submit').click();assert.equal(writes,beforeUnknown+1);
      const recovery=await query('blocks','manual-confirm-unknown');assert.equal(writes,beforeUnknown+1);assert.deepEqual(await draft(page),unknown);
      const recovered=recovery.body.data.items.find(row=>row.id===committedUnknown.id);assert.ok(recovered);
      for(const key of ['id','start_at','start_local','end_at','end_local','reason'])assert.equal(recovered[key],committedUnknown[key]);
      await assertVisibleRows(page,'blocks',recovery.body.data.items);
      const recoveredItem=page.locator('#admin-blocks-items > li').filter({has:page.locator('h3',{hasText:new RegExp(`^停用 ${committedUnknown.id} ·`)})});
      assert.equal(await recoveredItem.count(),1);assert.ok((await recoveredItem.textContent()).includes(unknown.reason));
      assert.ok((await recoveredItem.textContent()).includes(`${committedUnknown.start_local.slice(0,10)} ${committedUnknown.start_local.slice(11,19)} 至 ${committedUnknown.end_local.slice(0,10)} ${committedUnknown.end_local.slice(11,19)}`));
      // Manual query failures preserve filters and recover on the next deliberate query.
      await page.route('**/api/admin/bookings?*',route=>route.abort());await query('blocks','independent-block-query');
      await page.locator('#admin-bookings-submit').click();await page.waitForFunction(()=>document.querySelector('#admin-bookings-feedback').textContent.includes('查询失败'));
      assert.equal(await page.locator('#admin-bookings-submit').isDisabled(),false);await page.unroute('**/api/admin/bookings?*');await query('bookings','query-recovered');
      await page.locator('#block-confirm').check();
      stage('session');const csrf=(await (await context.request.get(origin+'/api/me')).json()).data.csrf_token;
      assert.equal((await context.request.post(origin+'/api/logout',{data:{},headers:{Origin:origin,'X-CSRF-Token':csrf}})).status(),200);
      response=page.waitForResponse(r=>r.request().method()==='POST'&&new URL(r.url()).pathname==='/api/admin/blocks');await page.locator('#block-submit').click();
      assert.equal((await capture(await response,'session-expired')).status,401);await settled(page);assert.deepEqual(await draft(page),unknown);
      assert.equal(await page.locator('#block-relogin').isVisible(),true);assert.equal(await page.locator('#block-submit').isDisabled(),true);assert.equal(await page.locator('#room-submit').isDisabled(),true);assert.equal(await page.locator('#admin-rooms li').count(),0);assert.equal(await page.locator('#admin-blocks-items li').count(),0);await screenshot('session-expired');
      stage('member');const memberContext=await browser.newContext({viewport}),memberPage=await login(memberContext,users[0]);
      assert.equal(await memberPage.locator('.primary-nav a[href="/admin"]').count(),0);
      for(const endpoint of ['/admin','/api/admin/bookings','/api/admin/blocks'])assert.equal((await memberContext.request.get(origin+endpoint)).status(),403);
      const memberCsrf=(await (await memberContext.request.get(origin+'/api/me')).json()).data.csrf_token;
      assert.equal((await memberContext.request.post(origin+'/api/admin/blocks',{data:{},headers:{Origin:origin,'X-CSRF-Token':memberCsrf}})).status(),403);
      stage('existing-paths');await memberPage.locator('#room_id').selectOption('30');await memberPage.locator('#date').fill(`2026-11-${day}`);
      response=memberPage.waitForResponse(r=>new URL(r.url()).pathname==='/api/schedule');await memberPage.locator('#schedule-form button[type=submit]').click();const schedule=await capture(await response,'shared-schedule');
      assert.equal(schedule.status,200);assert.ok(schedule.body.data.items.some(row=>row.kind==='block'&&row.record.reason===values.reason));
      await memberPage.locator('.primary-nav a[href="/my"]').click();await memberPage.waitForSelector('#history-feedback');
      await memberPage.locator('#logout-form button').focus();await memberPage.keyboard.press('Enter');await memberPage.waitForURL(origin+'/login?logged_out=1');
      assert.equal((await memberContext.request.get(origin+'/api/admin/blocks')).status(),401);assert.deepEqual(errors,[]);
      results.push({viewport,complete_dtos_plain_text:true,creation_conflict_recovery_session:true,four_states_filters:true,cross_form_focus:true,no_horizontal_overflow:true,writes});
      await memberContext.close();await context.close();
    }
  }finally{await browser.close();}
  console.log(JSON.stringify({result:'PASS',viewports:results}));
}
module.exports={safeDiagnostic};
if(require.main===module)main().catch(error=>{fs.writeFileSync(path.join(outputDir,'failure-diagnostics.json'),JSON.stringify(safeDiagnostic(error),null,2));process.exitCode=1;});
