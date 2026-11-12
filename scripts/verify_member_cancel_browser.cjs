// Real DOM actions and server outcomes. Private synthetic login credentials never enter artifacts.
const {chromium}=require('playwright');
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const [origin,credentialsFile,outputDir,executablePath]=process.argv.slice(2);
const users=JSON.parse(fs.readFileSync(credentialsFile,'utf8')).users;
const fullKeys=['id','room','title','purpose','attendees','owner_id','owner_display_name','start_at','start_local','end_at','end_local','status','created_at','created_local','cancelled_at','cancelled_local','cancelled_by_id','cancelled_by_display_name','cancel_reason'].sort();
async function login(context,user){
  const page=await context.newPage();await page.goto(origin+'/login');
  await page.locator('#username').fill(user.username);await page.locator('#password').fill(user.password);
  await page.locator('#password').press('Enter');await page.waitForURL(origin+'/');return page;
}
async function settled(page){await page.waitForFunction(()=>!document.querySelector('#cancel-form').hasAttribute('aria-busy'));}
async function openDetail(page,id){
  await page.locator('#history-items button').filter({hasText:`编号 ${id}`}).click();
  await page.waitForFunction(id=>!document.querySelector('#detail-fields').hidden&&document.querySelector('#detail-fields dd').textContent===String(id),id);
}
async function fields(page){return page.locator('#detail-fields').evaluate(node=>{
  const result={};for(let i=0;i<node.children.length;i+=2)result[node.children[i].textContent]=node.children[i+1].textContent;return result;
});}
async function width(page){const value=await page.evaluate(()=>({document:document.documentElement.scrollWidth,viewport:innerWidth}));assert.ok(value.document<=value.viewport);return value;}
(async()=>{
  assert.equal(require('playwright/package.json').version,'1.58.2');
  const browser=await chromium.launch({headless:true,...(executablePath?{executablePath}:{})});const results=[];
  try{
    for(const viewport of [{width:1280,height:800},{width:390,height:844}]){
      const context=await browser.newContext({viewport});const page=await login(context,users[0]);
      const errors=[];page.on('pageerror',error=>errors.push(error.name));const network=[];
      const target=viewport.width===1280?103:104;let requests=0;
      page.on('request',request=>{if(request.method()==='POST'&&request.url().endsWith('/cancel'))requests++;});
      async function capture(response,phase){const url=new URL(response.url());const result={phase,path:url.pathname+url.search,status:response.status(),body:await response.json()};network.push(result);return result;}
      const csrf=(await (await context.request.get(origin+'/api/me')).json()).data.csrf_token;
      async function post(id,body={},headers={}){
        return capture(await context.request.post(`${origin}/api/bookings/${id}/cancel`,{data:body,headers:{Origin:origin,'X-CSRF-Token':csrf,...headers}}),'direct-authorization-check');
      }
      const screenshot=async name=>{await width(page);await page.screenshot({path:path.join(outputDir,`${name}-${viewport.width}.png`),fullPage:true});};
      await page.locator('.primary-nav a[href="/my"]').click();await page.waitForSelector('#history-items button');
      await openDetail(page,target);const before=await fields(page);assert.equal(before['状态'],'待开始');
      const dto=await capture(await context.request.get(`${origin}/api/bookings/${target}`),'before-cancel');
      assert.deepEqual(Object.keys(dto.body.data).sort(),fullKeys);assert.deepEqual(Object.keys(dto.body.data.room).sort(),['capacity','id','location','name']);
      assert.equal(before['用途'],dto.body.data.purpose);assert.equal(before['活动名称'],dto.body.data.title);
      assert.equal(await page.locator('#detail-fields script,#history-items img').count(),0);assert.equal(await page.evaluate(()=>window.historyXss),undefined);
      await page.locator('#cancel-submit').click();assert.equal(requests,0);assert.equal(await page.locator('#cancel-confirm').isChecked(),false);
      await page.locator('#cancel-confirm').check();
      // A real server CSRF rejection keeps the selected record and editable confirmation.
      await page.route(`**/api/bookings/${target}/cancel`,async route=>{const headers=route.request().headers();delete headers['x-csrf-token'];await route.continue({headers});});
      let response=page.waitForResponse(r=>r.url().endsWith(`/${target}/cancel`));
      await page.locator('#cancel-submit').focus();await page.keyboard.press('Enter');
      const rejected=await capture(await response,'page-csrf-rejection');assert.equal(rejected.status,403);await settled(page);
      assert.equal(await page.evaluate(()=>document.activeElement.id),'cancel-feedback');
      assert.match(await page.locator('#cancel-feedback').textContent(),/保留/);
      await page.keyboard.press('Shift+Tab');assert.equal(await page.evaluate(()=>document.activeElement.id),'cancel-submit');
      assert.deepEqual(await fields(page),before);assert.equal(await page.locator('#cancel-confirm').isEnabled(),true);
      await page.locator('#cancel-confirm').uncheck();await page.locator('#cancel-confirm').check();
      assert.match(await page.locator('#cancel-feedback').textContent(),/保留/);await screenshot('cancel-rejected');
      await page.unroute(`**/api/bookings/${target}/cancel`);
      let release;const gate=new Promise(resolve=>{release=resolve;});
      await page.route(`**/api/bookings/${target}/cancel`,async route=>{await gate;await route.continue();});
      response=page.waitForResponse(r=>r.url().endsWith(`/${target}/cancel`));await page.locator('#cancel-submit').click();
      assert.equal(await page.locator('#cancel-submit').isDisabled(),true);assert.equal(await page.locator('#cancel-confirm').isDisabled(),true);
      await screenshot('cancel-loading');await page.locator('#logout-form button').focus();release();
      const success=await capture(await response,'page-confirmed-cancel');assert.equal(success.status,200);await settled(page);
      assert.equal(await page.evaluate(()=>document.activeElement===document.querySelector('#logout-form button')),true);
      assert.deepEqual(Object.keys(success.body.data).sort(),fullKeys);assert.equal(success.body.data.status,'cancelled');
      const actual=await fields(page);assert.equal(actual['状态'],'已取消');assert.equal(actual['取消操作者'],'演示成员甲');
      assert.equal(actual['取消时间（北京时间）'],'2026-11-12 10:00:00');assert.equal(actual['取消原因'],'未填写（本人取消无需原因）');
      assert.equal(await page.locator('#history-items li').filter({has:page.locator('button').filter({hasText:`编号 ${target}`})}).locator('.schedule-status').textContent(),'已取消');
      await screenshot('cancel-success');await page.unroute(`**/api/bookings/${target}/cancel`);
      await page.locator('#cancel-confirm').check();response=page.waitForResponse(r=>r.url().endsWith(`/${target}/cancel`));
      await page.locator('#cancel-submit').focus();await page.keyboard.press('Enter');
      const repeated=await capture(await response,'page-repeat');await settled(page);
      assert.deepEqual(repeated.body,success.body);
      assert.equal(await page.evaluate(()=>document.activeElement.id),'cancel-feedback');
      assert.match(await page.locator('#cancel-feedback').textContent(),/已取消/);
      await page.keyboard.press('Shift+Tab');assert.equal(await page.evaluate(()=>document.activeElement.id),'cancel-submit');
      const denied=await post(201),missing=await post(999);assert.equal(denied.status,404);assert.deepEqual(denied.body,missing.body);
      assert.equal((await post(106,{}, {'X-CSRF-Token':'invalid'})).status,403);
      assert.equal((await post(102)).status,409);assert.equal((await post(101)).status,409);
      for(const id of [102,101]){await openDetail(page,id);assert.equal(await page.locator('#cancel-form').isVisible(),false);assert.match(await page.locator('#cancel-feedback').textContent(),/已开始或结束.*不能取消/);}
      await screenshot('cancel-closed');
      // Navigating back and querying must immediately see released availability and schedule.
      await page.locator('.primary-nav a[href="/"]').click();
      const original=dto.body.data;
      await page.locator('#start').fill(original.start_local.slice(0,16));await page.locator('#end').fill(original.end_local.slice(0,16));
      await page.locator('#attendees').fill('5');await page.locator('#availability-form button[type=submit]').click();
      await page.waitForFunction(()=>!document.querySelector('#availability-form').hasAttribute('aria-busy'));
      assert.ok((await page.locator('#availability-results').textContent()).includes(original.room.name));
      const available=await capture(await context.request.get(`${origin}/api/availability?start=${original.start_local.slice(0,16)}&end=${original.end_local.slice(0,16)}&attendees=5`),'released-availability');
      assert.ok(available.body.data.items.some(room=>room.id===original.room.id));
      await page.locator('#room_id').selectOption(String(original.room.id));await page.locator('#date').fill('2026-11-12');
      const scheduleResponse=page.waitForResponse(r=>new URL(r.url()).pathname==='/api/schedule');
      await page.locator('#schedule-form button[type=submit]').click();
      const schedule=await capture(await scheduleResponse,'released-schedule-rendered');
      await page.waitForFunction(()=>!document.querySelector('#schedule-form').hasAttribute('aria-busy'));
      assert.equal(await page.locator('#schedule-results').isVisible(),true);
      const renderedTitles=await page.locator('#schedule-items h4').allTextContents();
      assert.deepEqual(renderedTitles,viewport.width===1280?['合成历史活动 101','合成历史活动 102']:['合成历史活动 201']);
      assert.ok(!renderedTitles.includes(original.title));
      assert.ok(schedule.body.data.items.every(item=>item.record.title!==original.title));
      const payload={room_id:original.room.id,title:original.title,purpose:original.purpose,attendees:5,start:original.start_local.slice(0,16),end:original.end_local.slice(0,16),intent_key:`browser-member-cancel-${viewport.width}`};
      const created=await capture(await context.request.post(origin+'/api/bookings',{data:payload,headers:{Origin:origin,'X-CSRF-Token':csrf}}),'reuse-released-slot');
      assert.equal(created.status,201);const replacement=created.body.data.booking.id;
      await page.goto(origin+'/my');await page.waitForSelector('#history-items button');await openDetail(page,replacement);
      await page.locator('#cancel-confirm').check();const originalFields=await fields(page);
      // Commit at the server, then drop response at the browser. Manual retry must reuse the ID.
      await page.route(`**/api/bookings/${replacement}/cancel`,async route=>{await capture(await route.fetch(),'server-committed-response-dropped');await route.abort();});
      const beforeUnknown=requests;await page.locator('#cancel-submit').click();
      await page.waitForFunction(()=>document.querySelector('#cancel-feedback').textContent.includes('未能确认'));await settled(page);
      assert.equal(requests,beforeUnknown+1);assert.deepEqual(await fields(page),originalFields);
      assert.equal(await page.locator('#cancel-confirm').isEnabled(),true);assert.match(await page.locator('#cancel-submit').textContent(),/重试确认原预约取消/);
      await screenshot('cancel-response-unknown');await page.unroute(`**/api/bookings/${replacement}/cancel`);
      response=page.waitForResponse(r=>r.url().endsWith(`/${replacement}/cancel`));await page.locator('#cancel-submit').click();
      const confirmed=await capture(await response,'manual-confirm-original-id');await settled(page);assert.equal(confirmed.body.data.id,replacement);
      assert.equal((await fields(page))['状态'],'已取消');assert.equal(requests,beforeUnknown+2);
      const replay=await capture(await context.request.post(origin+'/api/bookings',{data:payload,headers:{Origin:origin,'X-CSRF-Token':csrf}}),'replay-cancelled-original-intent');
      assert.equal(replay.status,200);assert.equal(replay.body.data.replayed,true);assert.equal(replay.body.data.booking.status,'cancelled');
      const observedWidth=await width(page);await screenshot('cancel-retry-confirmed');
      const stale=await context.newPage();await stale.goto(origin+'/my');await stale.waitForSelector('#history-items button');await openDetail(stale,target);await stale.locator('#cancel-confirm').check();
      await page.locator('#logout-form button').click();await page.waitForURL(origin+'/login?logged_out=1');
      await stale.locator('#cancel-submit').click();await stale.waitForFunction(()=>!document.querySelector('#detail-relogin').hidden);
      assert.equal(await stale.locator('#detail-fields').isVisible(),false);assert.equal(await stale.locator('#cancel-form').isVisible(),false);
      assert.equal(await stale.locator('#history-items li').count(),0);await stale.screenshot({path:path.join(outputDir,`cancel-session-expired-${viewport.width}.png`),fullPage:true});
      await context.close();
      const adminContext=await browser.newContext({viewport});await login(adminContext,users[2]);
      const adminCsrf=(await (await adminContext.request.get(origin+'/api/me')).json()).data.csrf_token;
      const adminForeign=await capture(await adminContext.request.post(`${origin}/api/bookings/${target}/cancel`,{data:{},headers:{Origin:origin,'X-CSRF-Token':adminCsrf}}),'admin-foreign-member-entry');
      assert.equal(adminForeign.status,404);await adminContext.close();
      fs.writeFileSync(path.join(outputDir,`cancel-network-${viewport.width}.jsonl`),network.map(row=>JSON.stringify(row)).join('\n')+'\n');
      assert.deepEqual(errors,[]);results.push({viewport,width:observedWidth,confirm_required:true,csrf_rejection:true,
        pending_cancel:true,duplicate_metadata_unchanged:true,expired_session:true,unknown_response_manual_retry:true,
        controls_editable_after_failure:true,success_preserves_other_form_focus:true,keyboard_feedback_and_tab:true,exact_dto:true,literal_text:true,
        released_schedule_availability:true,released_schedule_dom:true,rebooking:true,page_errors:errors});
    }
    console.log(JSON.stringify({result:'PASS',browser:await browser.version(),runner:'Playwright 1.58.2',node_version:process.version,results},null,2));
  }finally{await browser.close();}
})().catch(error=>{
  const source=String(error.stack).match(/verify_member_cancel_browser\.cjs:[0-9]+:[0-9]+/);
  fs.writeFileSync(path.join(outputDir,'browser-failure.json'),JSON.stringify({error_type:error.name,source:source?source[0]:null},null,2));
  console.error(error.name);process.exitCode=1;
});
