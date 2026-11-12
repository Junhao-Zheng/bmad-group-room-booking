// Real Chromium paths on private synthetic users; only business responses enter evidence.
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const [origin,credentialsFile,outputDir,executablePath]=process.argv.slice(2);
let stage='startup';
async function main(){
  const {chromium}=require('playwright'),users=JSON.parse(fs.readFileSync(credentialsFile,'utf8')).users;
  const browser=await chromium.launch({headless:true,executablePath}),results=[];
  try{
    for(const viewport of [{width:1280,height:800},{width:390,height:844}]){
      const context=await browser.newContext({viewport}),page=await context.newPage(),network=[],errors=[],displayed=[];
      let auditRequests=0;
      page.on('request',request=>{if(new URL(request.url()).pathname==='/api/admin/audit')auditRequests++;});
      page.on('pageerror',e=>errors.push(e.name));
      async function login(user){await page.goto(origin+'/login');await page.locator('#username').fill(user.username);await page.locator('#password').fill(user.password);await page.locator('#password').press('Enter');await page.waitForURL(origin+'/');}
      async function query(){const waiting=page.waitForResponse(r=>r.url().includes('/api/admin/audit'));await page.locator('#audit-submit').click();const r=await waiting;network.push({url:new URL(r.url()).pathname+new URL(r.url()).search,status:r.status(),body:await r.json()});await page.waitForFunction(()=>!document.querySelector('#audit-form').hasAttribute('aria-busy'));return network.at(-1);}
      async function shot(name){assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);await page.locator('section[aria-labelledby="audit-title"]').screenshot({path:path.join(outputDir,`${name}-${viewport.width}.png`)});}
      async function assertDisplayed(items){
        const labels={'room.created':'新增会议室','room.updated':'修改会议室','booking.created':'创建预约',
          'booking.cancelled_by_member':'本人取消预约','booking.cancelled_by_admin':'管理员取消预约','block.created':'创建停用','block.revoked':'撤销停用'};
        const rows=page.locator('#audit-items tr');assert.equal(await rows.count(),items.length);
        for(let index=0;index<items.length;index++){
          const item=items[index],cells=rows.nth(index).locator('td');assert.equal(await cells.count(),6);
          const actual=[];
          for(let column=0;column<6;column++){
            const cell=cells.nth(column),details=cell.locator('details');
            if(await details.count()){
              await details.locator('summary').click();assert.equal(await details.locator('pre').isVisible(),true);
              actual.push(await details.locator('pre').textContent());await details.locator('summary').click();
            }else actual.push(await cell.textContent());
          }
          const expected=[`#${item.id} · ${item.occurred_local.slice(0,10)} ${item.occurred_local.slice(11,19)}`,
            `${item.actor_display_name}（${item.actor_id}）`,`${labels[item.action]} · ${item.action}\n${item.target_type} #${item.target_id}`,
            item.before===null?'无（创建前）':JSON.stringify(item.before,null,2),JSON.stringify(item.after,null,2),item.reason===null?'无':item.reason];
          assert.deepEqual(actual,expected);
          displayed.push({event_id:item.id,action:item.action,actual_cells:actual,expected_cells:expected});
        }
        // Fixture facts are independent of DTO rendering and include distinct transitions.
        const updated=items.find(item=>item.action==='room.updated');assert.ok(updated);
        assert.equal(updated.before.location,'L');assert.equal(updated.after.location,'已修改 <script>text</script>');
        const cancelled=items.find(item=>item.action==='booking.cancelled_by_admin');assert.ok(cancelled);
        assert.equal(cancelled.before.cancelled_at,null);assert.ok(Number.isInteger(cancelled.after.cancelled_at));
        assert.equal(cancelled.after.cancel_reason,'管理员取消 <img src=x>'+'长'.repeat(200));
        const revoked=items.find(item=>item.action==='block.revoked');assert.ok(revoked);
        assert.equal(revoked.before.revoked_at,null);assert.ok(Number.isInteger(revoked.after.revoked_at));
        assert.equal(revoked.after.revoke_reason,'完成维护');
        for(const item of items){
          const reason={'booking.cancelled_by_admin':'管理员取消 <img src=x>'+'长'.repeat(200),'block.created':'合成维护','block.revoked':'完成维护'}[item.action]??null;
          assert.equal(item.reason,reason);
        }
      }
      async function assertFilterInvalidated(requestCount){
        assert.equal(await page.locator('#audit-items tr').count(),0);assert.equal(await page.locator('#audit-results').isVisible(),false);
        assert.match(await page.locator('#audit-feedback').textContent(),/筛选条件已修改.*重新查询/);
        assert.equal(auditRequests,requestCount);
      }
      stage='login';await login(users[2]);await page.goto(origin+'/admin');assert.match(await page.locator('#audit-feedback').textContent(),/尚未查询/);
      stage='all';const all=await query();assert.equal(all.status,200);assert.equal(all.body.data.total,10);
      const expectedKeys='action,actor_display_name,actor_id,after,before,id,occurred_at,occurred_local,reason,target_id,target_type';
      for(const row of all.body.data.items){assert.equal(Object.keys(row).sort().join(','),expectedKeys);assert.equal(typeof row.after,'object');}
      assert.equal(await page.locator('#audit-items tr').count(),10);assert.equal(await page.locator('#audit-items img,#audit-items script,#audit-items svg').count(),0);
      assert.equal(await page.evaluate(()=>window.auditXss),undefined);
      stage='display-bindings';await assertDisplayed(all.body.data.items);
      await page.locator('#audit-items details').first().locator('summary').click();assert.match(await page.locator('#audit-items').textContent(),/展开完整内容/);await shot('all-records');
      assert.equal(await page.locator('#audit-results').evaluate(el=>el.scrollWidth>=el.clientWidth),true);
      stage='filter';let previousRequests=auditRequests;await page.locator('#audit-target_type').selectOption('booking');await assertFilterInvalidated(previousRequests);
      assert.equal(await page.locator('#audit-target_type').inputValue(),'booking');
      await page.locator('#audit-date').fill(all.body.data.items[0].occurred_local.slice(0,10));await assertFilterInvalidated(previousRequests);
      const filtered=await query();assert.equal(filtered.body.data.total,5);assert.ok(filtered.body.data.items.every(e=>e.target_type==='booking'));await shot('filtered');
      previousRequests=auditRequests;await page.locator('#audit-date').fill('2000-01-01');await assertFilterInvalidated(previousRequests);
      assert.equal(await page.locator('#audit-date').inputValue(),'2000-01-01');await shot('filters-invalidated');
      assert.equal((await query()).body.data.total,0);assert.match(await page.locator('#audit-feedback').textContent(),/没有符合/);await shot('empty');
      stage='error';await page.route('**/api/admin/audit?**',route=>route.fulfill({status:500,contentType:'application/json',body:JSON.stringify({ok:false,error:{code:'INTERNAL_ERROR',message:'private SQL must not display',fields:{},conflicts:[]}})}));
      await query();assert.match(await page.locator('#audit-feedback').textContent(),/查询失败/);assert.doesNotMatch(await page.locator('#audit-feedback').textContent(),/private SQL/);assert.equal(await page.locator('#audit-date').inputValue(),'2000-01-01');await shot('error');await page.unroute('**/api/admin/audit?**');
      stage='loading';await page.locator('#audit-date').fill('');let release;const gate=new Promise(r=>{release=r;});await page.route('**/api/admin/audit?**',async route=>{await gate;await route.continue();});const pending=query();
      await page.waitForFunction(()=>document.querySelector('#audit-form').hasAttribute('aria-busy'));assert.equal(await page.locator('#audit-submit').isDisabled(),true);await shot('loading');release();assert.equal((await pending).body.data.total,5);await page.unroute('**/api/admin/audit?**');
      stage='invalid-filter';const invalid=await context.request.get(origin+'/api/admin/audit?date=2026-02-30');assert.equal(invalid.status(),400);
      stage='logout';await page.locator('#logout-form button').click();await page.waitForURL(origin+'/login?logged_out=1');await login(users[2]);await page.goto(origin+'/admin');await query();
      stage='auth-lost';const me=(await (await context.request.get(origin+'/api/me')).json()).data;
      assert.equal((await context.request.post(origin+'/api/logout',{data:{},headers:{Origin:origin,'X-CSRF-Token':me.csrf_token}})).status(),200);
      assert.equal((await query()).status,401);assert.equal(await page.locator('#audit-items tr').count(),0);assert.equal(await page.locator('#audit-submit').isDisabled(),true);assert.equal(await page.locator('#room-submit').isDisabled(),true);await shot('auth-lost');
      stage='member';await login(users[0]);assert.equal((await context.request.get(origin+'/api/admin/audit?date=bad')).status(),403);assert.equal((await page.goto(origin+'/admin')).status(),403);
      assert.deepEqual(errors,[]);fs.writeFileSync(path.join(outputDir,`network-${viewport.width}.json`),JSON.stringify(network,null,2));
      fs.writeFileSync(path.join(outputDir,`display-bindings-${viewport.width}.json`),JSON.stringify(displayed,null,2));
      results.push({...viewport,exact_dto:true,complete_display_bindings:true,distinct_update_cancel_revoke:true,per_action_reasons:true,safe_text:true,filters:true,filter_edits_invalidate:true,empty:true,loading:true,error_recovery:true,logged_out_session_rejected:true,member_403:true,login_logout:true,no_page_overflow:true,page_errors:errors});await context.close();
    }
    return {result:'PASS',completed:true,browser_version:browser.version(),viewports:results};
  }finally{await browser.close();}
}
main().then(result=>process.stdout.write(JSON.stringify(result))).catch(error=>{
  // Never print Playwright locator logs, fill values, response headers or credentials.
  const result={stage,error_type:error.name};fs.writeFileSync(path.join(outputDir,'failure.json'),JSON.stringify(result));process.stderr.write(JSON.stringify(result));process.exitCode=1;
});
