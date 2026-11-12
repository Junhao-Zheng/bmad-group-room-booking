// Real browser operations; evidence excludes synthetic passwords and session credentials.
const {chromium}=require('playwright');
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const [origin,credentialsFile,outputDir,executablePath]=process.argv.slice(2);
const users=JSON.parse(fs.readFileSync(credentialsFile,'utf8')).users;
const fullKeys=['id','room','title','purpose','attendees','owner_id','owner_display_name','start_at','start_local','end_at','end_local','status','created_at','created_local','cancelled_at','cancelled_local','cancelled_by_id','cancelled_by_display_name','cancel_reason'].sort();
async function login(context,user){const page=await context.newPage();await page.goto(origin+'/login');await page.locator('#username').fill(user.username);await page.locator('#password').fill(user.password);await page.locator('#password').press('Enter');await page.waitForURL(origin+'/');return page;}
async function settled(page){await page.waitForFunction(()=>!document.querySelector('#admin-cancel-form').hasAttribute('aria-busy'));}
async function width(page){const sizes=await page.evaluate(()=>({document:document.documentElement.scrollWidth,viewport:innerWidth}));assert.ok(sizes.document<=sizes.viewport);return sizes;}
(async()=>{
  assert.equal(require('playwright/package.json').version,'1.58.2');
  const browser=await chromium.launch({headless:true,executablePath});const results=[];
  try{
    for(const viewport of [{width:1280,height:800},{width:390,height:844}]){
      const context=await browser.newContext({viewport}),page=await login(context,users[2]);
      const target=viewport.width===1280?103:104,ongoing=viewport.width===1280?102:201,network=[],errors=[];
      page.on('pageerror',error=>errors.push(error.name));let posts=0;
      page.on('request',request=>{if(request.method()==='POST'&&request.url().endsWith('/cancel'))posts++;});
      const saveNetwork=()=>fs.writeFileSync(path.join(outputDir,`admin-cancel-network-${viewport.width}.json`),JSON.stringify(network,null,2));
      async function capture(response,phase){const url=new URL(response.url());const result={phase,path:url.pathname+url.search,status:response.status(),body:await response.json()};network.push(result);saveNetwork();return result;}
      async function screenshot(name,locator='#admin-cancel-panel'){await page.locator(locator).scrollIntoViewIfNeeded();await width(page);await page.screenshot({path:path.join(outputDir,`${name}-${viewport.width}.png`),fullPage:true});await page.locator(locator).screenshot({path:path.join(outputDir,`${name}-panel-${viewport.width}.png`)});}
      async function choose(id){await page.locator('#admin-bookings-items button').filter({hasText:new RegExp(`预约 ${id}$`)}).click();await page.locator('#admin-cancel-reason').waitFor({state:'visible'});}
      await page.goto(origin+'/admin');
      assert.equal(await page.locator('#admin-cancel-reason').getAttribute('aria-describedby'),'admin-cancel-summary admin-cancel-reason-error');
      assert.equal(await page.locator('#admin-cancel-confirm').getAttribute('aria-describedby'),'admin-cancel-summary');
      await page.locator('#admin-bookings-status').selectOption('pending');await page.locator('#admin-bookings-submit').click();await page.waitForSelector('#admin-bookings-items li');
      assert.equal(await page.locator('#admin-bookings-items li').filter({has:page.locator('h3').filter({hasText:'预约 101 ·'})}).locator('button').count(),0);
      await choose(target);assert.equal(await page.locator('#admin-cancel-reason').isEnabled(),true);
      await page.locator('#admin-cancel-reason').fill('   ');await page.locator('#admin-cancel-confirm').check();
      let response=page.waitForResponse(r=>r.url().endsWith(`/${target}/cancel`));await page.locator('#admin-cancel-submit').click();
      const invalid=await capture(await response,'blank-reason-rejected');assert.equal(invalid.status,400);await settled(page);
      assert.equal(await page.locator('#admin-cancel-reason').inputValue(),'   ');assert.equal(await page.evaluate(()=>document.activeElement.id),'admin-cancel-reason');
      const reason='<svg onload="window.adminCancelXss=1">维护说明</svg> '+ '长文本' .repeat(50);
      await page.locator('#admin-cancel-reason').fill(reason);assert.equal(await page.locator('#admin-cancel-confirm').isChecked(),false);
      const beforeNoConfirm=posts;await page.locator('#admin-cancel-submit').click();assert.equal(posts,beforeNoConfirm);
      await page.locator('#admin-cancel-confirm').check();
      await page.route(`**/api/admin/bookings/${target}/cancel`,async route=>{const headers=route.request().headers();delete headers['x-csrf-token'];await route.continue({headers});});
      response=page.waitForResponse(r=>r.url().endsWith(`/${target}/cancel`));await page.locator('#admin-cancel-submit').click();
      const rejected=await capture(await response,'real-csrf-rejection');assert.equal(rejected.status,403);await settled(page);
      assert.equal(await page.locator('#admin-cancel-reason').inputValue(),reason);assert.equal(await page.locator('#admin-cancel-reason').isEnabled(),true);
      await screenshot('admin-cancel-rejected');await page.unroute(`**/api/admin/bookings/${target}/cancel`);
      let release;const gate=new Promise(resolve=>{release=resolve;});
      await page.route(`**/api/admin/bookings/${target}/cancel`,async route=>{await gate;await route.continue();});
      response=page.waitForResponse(r=>r.url().endsWith(`/${target}/cancel`));await page.locator('#admin-cancel-submit').click();
      assert.equal(await page.locator('#admin-cancel-submit').isDisabled(),true);assert.equal(await page.locator('#admin-cancel-reason').isDisabled(),true);
      assert.equal(await page.locator('#admin-bookings-submit').isDisabled(),true);await screenshot('admin-cancel-waiting');
      await page.locator('#room-name').focus();release();const success=await capture(await response,'pending-cancel-success');assert.equal(success.status,200);await settled(page);
      assert.equal(await page.evaluate(()=>document.activeElement.id),'room-name');assert.deepEqual(Object.keys(success.body.data).sort(),fullKeys);
      assert.equal(success.body.data.cancel_reason,reason);assert.equal(success.body.data.cancelled_by_id,3);
      assert.match(await page.locator('#admin-cancel-summary').textContent(),/已取消/);assert.ok((await page.locator('#admin-cancel-summary').textContent()).includes(reason));
      assert.equal(await page.locator('#admin-cancel-summary svg,#admin-bookings-items svg').count(),0);assert.equal(await page.evaluate(()=>window.adminCancelXss),undefined);
      const row=page.locator('#admin-bookings-items li').filter({has:page.locator('h3').filter({hasText:`预约 ${target} ·`})});assert.equal(await row.count(),0);
      const saved=success.body.data,summary=await page.locator('#admin-cancel-summary').textContent();
      assert.ok(summary.includes(`会议室：${saved.room.id} · ${saved.room.name} · ${saved.room.location}`));
      assert.ok(summary.includes(`预约时段（北京时间）：${saved.start_local.replace('T',' ').slice(0,19)} 至 ${saved.end_local.replace('T',' ').slice(0,19)}`));
      await screenshot('admin-cancel-success');await page.unroute(`**/api/admin/bookings/${target}/cancel`);
      await page.locator('#admin-cancel-reason').fill('重新确认的合规原因');await page.locator('#admin-cancel-confirm').check();
      response=page.waitForResponse(r=>r.url().endsWith(`/${target}/cancel`));await page.locator('#admin-cancel-submit').focus();await page.keyboard.press('Enter');
      const repeated=await capture(await response,'repeat-keeps-first-facts');await settled(page);assert.deepEqual(repeated.body,success.body);
      assert.equal(await page.evaluate(()=>document.activeElement.id),'admin-cancel-feedback');
      await page.locator('#admin-bookings-status').selectOption('');await page.locator('#admin-bookings-submit').click();await page.waitForSelector('#admin-bookings-items li');
      await choose(ongoing);await page.locator('#admin-cancel-reason').fill('进行中预约的合成管理原因');await page.locator('#admin-cancel-confirm').check();
      await page.route(`**/api/admin/bookings/${ongoing}/cancel`,async route=>{await capture(await route.fetch(),'committed-response-dropped');await route.abort();});
      const beforeUnknown=posts;await page.locator('#admin-cancel-submit').click();await page.waitForFunction(()=>document.querySelector('#admin-cancel-feedback').textContent.includes('未能确认'));await settled(page);
      assert.equal(posts,beforeUnknown+1);assert.equal(await page.locator('#admin-cancel-confirm').isChecked(),false);
      assert.equal(await page.locator('#admin-cancel-reason').inputValue(),'进行中预约的合成管理原因');await screenshot('admin-cancel-unknown');
      await page.unroute(`**/api/admin/bookings/${ongoing}/cancel`);await page.locator('#admin-cancel-confirm').check();
      response=page.waitForResponse(r=>r.url().endsWith(`/${ongoing}/cancel`));await page.locator('#admin-cancel-submit').click();
      const ongoingResult=await capture(await response,'in-progress-manual-retry');assert.equal(ongoingResult.status,200);await settled(page);
      assert.deepEqual(ongoingResult.body,network.find(item=>item.phase==='committed-response-dropped').body);
      const memberContext=await browser.newContext({viewport}),member=await login(memberContext,users[0]);
      await member.goto(origin+'/my');await member.locator('#history-items button').filter({hasText:`编号 ${target}`}).click();await member.waitForFunction(()=>!document.querySelector('#detail-fields').hidden);
      const detail=await member.locator('#detail-fields').evaluate(node=>{const result={};for(let i=0;i<node.children.length;i+=2)result[node.children[i].textContent]=node.children[i+1].textContent;return result;});
      assert.equal(detail['取消原因'],reason);assert.equal(detail['取消操作者'],'演示管理员');assert.equal(detail['状态'],'已取消');
      assert.equal(await member.locator('#detail-fields svg,#detail-fields script,#detail-fields img').count(),0);assert.equal(await member.evaluate(()=>window.adminCancelXss),undefined);
      await width(member);await member.locator('#history-detail').scrollIntoViewIfNeeded();await member.screenshot({path:path.join(outputDir,`member-visible-reason-${viewport.width}.png`),fullPage:true});
      const csrf=(await(await memberContext.request.get(origin+'/api/me')).json()).data.csrf_token;
      const denied=await capture(await memberContext.request.post(`${origin}/api/admin/bookings/0/cancel`,{headers:{Origin:origin,'X-CSRF-Token':csrf},data:{reason:null}}),'member-admin-denied');assert.equal(denied.status,403);
      const original=success.body.data;
      await member.goto(origin+'/');await member.locator('#start').fill(original.start_local.slice(0,16));await member.locator('#end').fill(original.end_local.slice(0,16));await member.locator('#attendees').fill('5');
      await member.locator('#availability-form button[type=submit]').click();await member.waitForFunction(()=>!document.querySelector('#availability-form').hasAttribute('aria-busy'));
      assert.ok((await member.locator('#availability-results').textContent()).includes(original.room.name));
      const availability=await capture(await memberContext.request.get(`${origin}/api/availability?start=${original.start_local.slice(0,16)}&end=${original.end_local.slice(0,16)}&attendees=5`),'released-availability');
      assert.ok(availability.body.data.items.some(room=>room.id===original.room.id));
      await memberContext.close();
      const logoutPage=await context.newPage();await logoutPage.goto(origin+'/admin');await logoutPage.locator('#logout-form button').click();await logoutPage.waitForURL(origin+'/login?logged_out=1');
      await page.locator('#admin-cancel-confirm').check();await page.locator('#admin-cancel-submit').click();await page.waitForFunction(()=>!document.querySelector('#admin-cancel-relogin').hidden&&document.querySelector('#admin-cancel-fields').disabled);await settled(page);
      assert.equal(await page.locator('#admin-bookings-items li').count(),0);assert.equal(await page.locator('#admin-cancel-summary').textContent(),'');
      assert.equal(await page.locator('#admin-cancel-reason').inputValue(),'进行中预约的合成管理原因');await screenshot('admin-cancel-session-lost');
      assert.deepEqual(errors,[]);results.push({viewport,width:await width(page),pending_and_in_progress:true,confirmation_required:true,reason_failure_retained:true,
        csrf_rejection:true,waiting_disabled:true,first_result_preserved:true,unknown_manual_retry:true,member_sees_reason:true,member_management_denied:true,
        released_availability:true,session_loss_blocks:true,plain_text_xss:true,keyboard_and_focus:true,summary_aria_links:true,pending_filter_preserves_complete_success_summary:true,page_errors:errors});await context.close();
    }
    console.log(JSON.stringify({result:'PASS',browser:await browser.version(),runner:'Playwright 1.58.2',node_version:process.version,results},null,2));
  }finally{await browser.close();}
})().catch(error=>{const source=String(error.stack).match(/verify_admin_cancel_browser\.cjs:[0-9]+:[0-9]+/);fs.writeFileSync(path.join(outputDir,'browser-failure.json'),JSON.stringify({error_type:error.name,source:source?source[0]:null},null,2));console.error(error.name);process.exitCode=1;});
