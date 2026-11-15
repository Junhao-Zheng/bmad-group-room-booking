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
      const page=student.page;await page.locator('#start').fill(day+'T10:00');await page.locator('#end').fill(day+'T11:00');await page.locator('#attendees').fill('3');
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
      await page.locator('#history-items button').first().click();await page.waitForFunction(()=>!document.querySelector('#detail-fields').hidden);
      assert.match(await page.locator('#detail-fields').textContent(),/审批申请编号/);assert.equal(await page.locator('#cancel-form').isVisible(),false);await shot(page,'student-approved-detail');
      const approved=(await (await student.context.request.get(origin+`/api/applications/${item.id}`)).json()).data;
      assert.equal((await other.context.request.get(origin+`/api/bookings/${approved.reservation_id}`)).status(),404);
      assert.deepEqual(errors,[]);results.push({viewport,application_id:item.id,reservation_id:approved.reservation_id,unknown_retry_preserved_intent:true,cross_teacher_status:404,keyboard_approval:true});
      for(const context of contexts)await context.close();
    }
    process.stdout.write(JSON.stringify({result:'PASS',results}));
  } finally {await browser.close();}
})().catch(error=>{console.error(error.stack);process.exitCode=1;});
