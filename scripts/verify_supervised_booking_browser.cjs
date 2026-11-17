const {chromium}=require('playwright');
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const [origin,credentialsFile,outputDir,executablePath]=process.argv.slice(2);
const users=JSON.parse(fs.readFileSync(credentialsFile,'utf8')).users;
(async()=>{
  const browser=await chromium.launch({headless:true,executablePath});const results=[];
  try {
    for(const [index,viewport] of [{width:1280,height:900},{width:390,height:844}].entries()) {
      const contexts=[];const errors=[];
      async function login(username) {const context=await browser.newContext({viewport});contexts.push(context);const page=await context.newPage();page.on('pageerror',e=>errors.push(e.message));
        const user=users.find(u=>u.username===username);await page.goto(origin+'/login');await page.locator('#username').fill(username);await page.locator('#password').fill(user.password);await page.locator('#password').press('Enter');await page.waitForURL(origin+'/');return {context,page};}
      async function shot(page,name) {assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);await page.screenshot({path:path.join(outputDir,`${name}-${viewport.width}.png`),fullPage:true});}
      async function settle(page) {await page.waitForFunction(()=>document.querySelector('#applications-panel').getAttribute('aria-busy')==='false');}
      const student=await login('demo_member_a'),teacher=await login('demo_teacher_a'),other=await login('demo_teacher_b'),admin=await login('demo_admin');
      const day=new Date(Date.now()+8*3600000+(index+1)*86400000).toISOString().slice(0,10);
      const page=student.page;await page.locator('#start').fill(day+'T10:10');await page.locator('#end').fill(day+'T11:10');await page.locator('#attendees').fill('3');
      await page.locator('#availability-form button').click();await page.locator('.booking-select').first().click();
      await page.locator('#booking-name').fill('学生讨论 <img src=x>');await page.locator('#booking-purpose').fill('私有用途：研究讨论');
      // Lose the first committed response, then verify the UI retries the original intent.
      let lost=false;const intents=[];
      await page.route('**/api/applications',async route=>{
        if(route.request().method()!=='POST')return route.continue();
        intents.push(route.request().postDataJSON().intent_key);
        if(!lost){lost=true;await route.fetch();return route.abort();}return route.continue();
      });
      await page.locator('#booking-form button[type=submit]').click();await page.waitForFunction(()=>document.querySelector('#booking-feedback').textContent.includes('未能确认'));
      await page.locator('#booking-form button[type=submit]').click();await page.waitForFunction(()=>document.querySelector('#booking-feedback').textContent.includes('已确认原申请'));
      assert.equal(intents.length,2);assert.equal(intents[0],intents[1]);await page.unroute('**/api/applications');
      const appList=(await (await student.context.request.get(origin+'/api/applications')).json()).data.items;
      const item=appList.find(a=>a.start_local.startsWith(day));assert.equal(item.status,'awaiting_approval');
      let schedule=(await (await other.context.request.get(origin+`/api/schedule?room_id=1&date=${day}`)).json()).data;assert.equal(schedule.total,0);
      await page.goto(origin+'/applications');await settle(page);assert.match(await page.locator('#applications-items').textContent(),/尚未占用/);await shot(page,'student-awaiting');
      assert.equal(await page.getByRole('heading',{name:'申请记录'}).count(),1);
      await page.locator('#applications-status').selectOption('processed');assert.equal(await page.locator(`[data-application-id="${item.id}"]`).count(),0);
      await page.locator('#applications-status').selectOption('awaiting_approval');assert.equal(await page.locator(`[data-application-id="${item.id}"]`).count(),1);
      await page.locator('#applications-date').fill('2026-01-01');assert.equal(await page.locator(`[data-application-id="${item.id}"]`).count(),0);
      await page.locator('#applications-date').fill(day);assert.equal(await page.locator(`[data-application-id="${item.id}"]`).count(),1);
      const otherMe=(await (await other.context.request.get(origin+'/api/me')).json()).data;
      assert.equal((await other.context.request.get(origin+`/api/applications/${item.id}`)).status(),404);
      assert.equal((await other.context.request.post(origin+`/api/applications/${item.id}/approve`,{data:{},headers:{Origin:origin,'X-CSRF-Token':otherMe.csrf_token}})).status(),404);
      await admin.page.goto(origin+'/applications');await settle(admin.page);assert.equal(await admin.page.getByRole('button',{name:'批准申请',exact:true}).count(),0);
      await teacher.page.goto(origin+'/applications');await settle(teacher.page);
      await teacher.page.locator(`[data-application-id="${item.id}"]`).getByRole('button',{name:'批准申请',exact:true}).focus();await teacher.page.keyboard.press('Enter');
      await teacher.page.waitForFunction(id=>document.querySelector(`[data-application-id="${id}"]`)?.textContent.includes('已批准'),item.id);await settle(teacher.page);await shot(teacher.page,'teacher-approved');
      await other.page.goto(origin+'/');await other.page.locator('#room_id').selectOption('1');await other.page.locator('#date').fill(day);await other.page.locator('#schedule-form button').click();
      await other.page.waitForFunction(()=>document.querySelector('#schedule-items').textContent.includes('所属导师：'));
      assert.match(await other.page.locator('#schedule-items').textContent(),/导师甲/);assert.doesNotMatch(await other.page.locator('#schedule-items').textContent(),/私有用途/);
      assert.equal(await other.page.locator('#schedule-items img').count(),0);await shot(other.page,'shared-schedule');
      await page.goto(origin+'/my');await page.locator('#history-items button').first().waitFor();
      await page.locator('#history-room').selectOption('1');assert.ok(await page.locator('#history-items li').count()>0);
      await page.locator('#history-date').fill('2026-01-01');assert.equal(await page.locator('#history-items li').count(),0);
      await page.locator('#history-date').fill(day);assert.ok(await page.locator('#history-items li').count()>0);
      await page.locator('#history-items button').first().click();await page.waitForFunction(()=>!document.querySelector('#detail-fields').hidden);
      assert.match(await page.locator('#detail-fields').textContent(),/审批申请编号/);assert.equal(await page.locator('#cancel-form').isVisible(),true);
      assert.match(await page.locator('#cancel-form').textContent(),/导师/);await shot(page,'student-approved-detail');
      const approved=(await (await student.context.request.get(origin+`/api/applications/${item.id}`)).json()).data;
      assert.equal((await other.context.request.get(origin+`/api/bookings/${approved.reservation_id}`)).status(),404);
      await page.goto(origin+'/');await page.locator('#start').fill(day+'T13:00');await page.locator('#end').fill(day+'T14:00');
      await page.locator('#attendees').fill('3');await page.locator('#availability-form button').click();
      await page.locator('.booking-select').first().click();await page.locator('#booking-name').fill('连续八周组会');
      await page.locator('#booking-purpose').fill('每周课题讨论');await page.locator('#booking-weeks').selectOption('8');
      assert.equal(await page.locator('#booking-dates li').count(),8);
      await page.locator('#booking-form button[type=submit]').click();
      await page.waitForFunction(()=>document.querySelector('#booking-feedback').textContent.includes('申请已提交'));
      const weekly=(await (await student.context.request.get(origin+'/api/applications')).json()).data.items.find(a=>a.weeks===8);
      assert.equal(weekly.occurrences.length,8);assert.equal(weekly.status,'awaiting_approval');
      await teacher.page.goto(origin+'/applications');await settle(teacher.page);
      const weeklyRow=teacher.page.locator(`[data-application-id="${weekly.id}"]`);
      assert.equal(await weeklyRow.getByText(/第 8 周/).count(),1);
      await weeklyRow.getByRole('button',{name:'批准申请',exact:true}).click();
      await teacher.page.waitForFunction(id=>document.querySelector(`[data-application-id="${id}"]`)?.textContent.includes('已批准'),weekly.id);
      const weeklyApproved=(await (await student.context.request.get(origin+`/api/applications/${weekly.id}`)).json()).data;
      assert.equal(new Set(weeklyApproved.occurrences.map(o=>o.reservation_id)).size,8);
      const third=weeklyApproved.occurrences[2],fifth=weeklyApproved.occurrences[4];
      const studentMe=(await (await student.context.request.get(origin+'/api/me')).json()).data;
      const cancel=await student.context.request.post(origin+`/api/bookings/${third.reservation_id}/cancellation-requests`,
        {data:{},headers:{Origin:origin,'X-CSRF-Token':studentMe.csrf_token}});
      assert.equal(cancel.status(),201);const cancellation=(await cancel.json()).data.cancellation_request;
      await teacher.page.goto(origin+'/applications');
      await teacher.page.getByRole('button',{name:'确认取消',exact:true}).first().waitFor();
      await teacher.page.locator('#cancellations-status').selectOption('processed');assert.equal(await teacher.page.locator(`[data-cancellation-id="${cancellation.id}"]:visible`).count(),0);
      await teacher.page.locator('#cancellations-status').selectOption('awaiting_approval');assert.equal(await teacher.page.locator(`[data-cancellation-id="${cancellation.id}"]:visible`).count(),1);
      await teacher.page.getByRole('button',{name:'确认取消',exact:true}).first().click();
      await teacher.page.waitForFunction(id=>document.querySelector('#cancellations-items')?.textContent.includes(`取消申请 #${id}`)&&document.querySelector('#cancellations-items')?.textContent.includes('已确认取消'),cancellation.id);
      const weeklyAfter=(await (await student.context.request.get(origin+`/api/applications/${weekly.id}`)).json()).data;
      assert.equal(weeklyAfter.occurrences[2].status,'cancelled');
      assert.equal(weeklyAfter.occurrences.filter(o=>o.status==='cancelled').length,1);
      assert.equal((await (await other.context.request.get(origin+`/api/schedule?room_id=1&date=${fifth.start_local.slice(0,10)}`)).json()).data.total,1);
      await shot(teacher.page,'weekly-third-cancelled');
      await admin.page.goto(origin+'/admin');
      await admin.page.locator('#batch-room_id').selectOption('1');
      await admin.page.locator('#batch-start').fill(day+'T10:00');
      await admin.page.locator('#batch-end').fill(day+'T14:00');
      await admin.page.locator('#batch-reason').fill('维修停用，统一取消当天两场');
      await admin.page.locator('#batch-preview').click();
      await admin.page.locator('#batch-review').waitFor({state:'visible'});
      assert.equal(await admin.page.locator('#batch-affected li').count(),2);
      await shot(admin.page,'maintenance-preview');
      await admin.page.locator('#batch-reason').fill('维修停用，重新核对两场');
      assert.equal(await admin.page.locator('#batch-review').isVisible(),false);
      await admin.page.locator('#batch-reason').fill('维修停用，统一取消当天两场');
      await admin.page.locator('#batch-preview').click();
      await admin.page.locator('#batch-review').waitFor({state:'visible'});
      let lostMaintenance=false;const confirmTokens=[];
      await admin.page.route('**/api/admin/blocks/confirm',async route=>{
        confirmTokens.push(route.request().postDataJSON().preview_token);
        if(!lostMaintenance){lostMaintenance=true;await route.fetch();return route.abort();}return route.continue();
      });
      await admin.page.locator('#batch-confirm').check();await admin.page.locator('#batch-submit').click();
      await admin.page.waitForFunction(()=>document.querySelector('#batch-feedback').textContent.includes('结果尚未确认'));
      await admin.page.locator('#batch-submit').click();
      await admin.page.waitForFunction(()=>document.querySelector('#batch-feedback').textContent.includes('已确认'));
      assert.equal(confirmTokens.length,2);assert.equal(confirmTokens[0],confirmTokens[1]);
      await admin.page.unroute('**/api/admin/blocks/confirm');
      const blockId=Number((await admin.page.locator('#batch-feedback').textContent()).match(/停用 #(\d+)/)[1]);
      const firstAfter=(await (await student.context.request.get(origin+`/api/bookings/${approved.reservation_id}`)).json()).data;
      assert.equal(firstAfter.status,'cancelled');assert.equal(firstAfter.cancel_reason,'维修停用，统一取消当天两场');
      const daySchedule=(await (await other.context.request.get(origin+`/api/schedule?room_id=1&date=${day}`)).json()).data;
      assert.equal(daySchedule.total,1);assert.equal(daySchedule.items[0].kind,'block');
      const adminMe=(await (await admin.context.request.get(origin+'/api/me')).json()).data;
      const revoked=await admin.context.request.post(origin+`/api/admin/blocks/${blockId}/revoke`,
        {data:{reason:'维修提前结束'},headers:{Origin:origin,'X-CSRF-Token':adminMe.csrf_token}});
      assert.equal(revoked.status(),200);
      assert.equal((await (await other.context.request.get(origin+`/api/schedule?room_id=1&date=${day}`)).json()).data.total,0);
      assert.equal((await (await other.context.request.get(origin+`/api/schedule?room_id=1&date=${fifth.start_local.slice(0,10)}`)).json()).data.total,1);
      await shot(admin.page,'maintenance-confirmed');
      assert.deepEqual(errors,[]);results.push({viewport,application_id:item.id,reservation_id:approved.reservation_id,unknown_retry_preserved_intent:true,cross_teacher_status:404,keyboard_approval:true,weekly_count:8,weekly_cancelled_one:true,maintenance_cancelled:2,maintenance_retry_preserved_token:true,revocation_did_not_restore:true});
      for(const context of contexts)await context.close();
    }
    process.stdout.write(JSON.stringify({result:'PASS',results}));
  } finally {await browser.close();}
})().catch(error=>{console.error(error.stack);process.exitCode=1;});
