// Only synthetic history responses are retained; never cookies, passwords or CSRF.
const {chromium} = require('playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const [origin,credentialsFile,outputDir,executablePath] = process.argv.slice(2);
const users=JSON.parse(fs.readFileSync(credentialsFile,'utf8')).users;
const fullKeys=['id','room','title','purpose','attendees','owner_id','owner_display_name','start_at','start_local','end_at','end_local','status','created_at','created_local','cancelled_at','cancelled_local','cancelled_by_id','cancelled_by_display_name','cancel_reason'].sort();
async function login(context,user){
  const page=await context.newPage();await page.goto(`${origin}/login`);
  await page.locator('#username').fill(user.username);await page.locator('#password').fill(user.password);
  await page.locator('#password').press('Enter');await page.waitForURL(`${origin}/`);return page;
}
async function width(page){const result=await page.evaluate(()=>({document:document.documentElement.scrollWidth,viewport:innerWidth}));assert.ok(result.document<=result.viewport);return result;}
const statusLabels={pending:'待开始',in_progress:'进行中',ended:'已结束',cancelled:'已取消'};
async function rows(page){
  return page.locator('#history-items > li').evaluateAll(nodes=>nodes.map(node=>({
    id:Number(node.querySelector('button').textContent.match(/编号 ([0-9]+)/)[1]),
    status:node.querySelector('.schedule-status').textContent,
  })));
}
async function renderedResponse(response,network){
  const result={source:'page-rendered-response',path:new URL(response.url()).pathname+new URL(response.url()).search,
    status:response.status(),body:await response.json()};
  if(network)network.push(result);
  return result;
}
async function filter(page,status,ids,network,expectedOutcome='success'){
  await page.locator('#history-status').selectOption(status);await page.locator('#history-status').focus();
  await page.keyboard.press('Tab');assert.equal(await page.evaluate(()=>document.activeElement.textContent),'查看预约');
  const response=expectedOutcome==='network'?null:page.waitForResponse(r=>new URL(r.url()).pathname==='/api/bookings/mine');
  await page.keyboard.press('Enter');
  const observed=response?await renderedResponse(await response,network):null;
  await page.waitForFunction(()=>!document.querySelector('#history-form').hasAttribute('aria-busy'));
  assert.deepEqual(await rows(page),ids.map(id=>({id,status:statusLabels[status]})));
  if(expectedOutcome==='success'){
    assert.equal(observed.status,200);assert.deepEqual(observed.body.data.items.map(b=>b.id),ids);
    assert.ok(observed.body.data.items.every(b=>b.status===status));
    // Do not repair focus here: check the focus actually restored by the handler.
    assert.equal(await page.evaluate(()=>document.activeElement===document.querySelector('#history-form button')),true);
    await page.keyboard.press('Shift+Tab');assert.equal(await page.evaluate(()=>document.activeElement.id),'history-status');
    await page.keyboard.press('Tab');assert.equal(await page.evaluate(()=>document.activeElement===document.querySelector('#history-form button')),true);
    if(ids.length){
      await page.keyboard.press('Tab');
      assert.equal(await page.evaluate(()=>document.activeElement===document.querySelector('#history-items button')),true);
    }
  }else assert.equal(await page.evaluate(()=>document.activeElement.id),'history-feedback');
  return observed;
}
(async()=>{
  assert.equal(require('playwright/package.json').version,'1.58.2');
  const browser=await chromium.launch({headless:true,...(executablePath?{executablePath}:{})});const results=[];
  try{
    for(const viewport of [{width:1280,height:800},{width:390,height:844}]){
      const context=await browser.newContext({viewport});const page=await login(context,users[0]);
      const errors=[];page.on('pageerror',error=>errors.push(error.name));
      const network=[];
      async function api(url){const response=await context.request.get(origin+url);const body=await response.json();
        network.push({path:url,status:response.status(),body});return {status:response.status(),body};}
      const screenshot=async name=>{await page.evaluate(()=>window.scrollTo(0,0));await page.screenshot({path:path.join(outputDir,`${name}-${viewport.width}.png`),fullPage:true});};
      let release;const gate=new Promise(resolve=>{release=resolve;});
      await page.route('**/api/bookings/mine',async route=>{await gate;await route.continue();});
      await page.locator('.brand').focus();await page.keyboard.press('Tab');
      assert.equal(await page.evaluate(()=>document.activeElement.textContent),'预约');await page.keyboard.press('Tab');
      assert.equal(await page.evaluate(()=>document.activeElement.textContent),'我的预约');
      const initialResponse=page.waitForResponse(r=>new URL(r.url()).pathname==='/api/bookings/mine');
      await page.keyboard.press('Enter');
      await page.waitForURL(`${origin}/my`);await page.waitForFunction(()=>document.querySelector('#history-form').getAttribute('aria-busy')==='true');
      assert.equal(await page.locator('#history-status').isDisabled(),true);await screenshot('loading');release();
      await renderedResponse(await initialResponse,network);
      await page.waitForFunction(()=>document.querySelector('#history-items').children.length===6);
      assert.deepEqual(await rows(page),[{id:106,status:'已取消'},{id:105,status:'已取消'},{id:104,status:'待开始'},
        {id:103,status:'待开始'},{id:102,status:'进行中'},{id:101,status:'已结束'}]);
      await page.unroute('**/api/bookings/mine');
      const all=await api('/api/bookings/mine?user_id=2');assert.equal(all.status,200);
      assert.deepEqual(all.body.data.items.map(b=>b.id),[106,105,104,103,102,101]);
      for(const b of all.body.data.items){assert.deepEqual(Object.keys(b).sort(),fullKeys);assert.equal(b.owner_id,1);
        assert.deepEqual(Object.keys(b.room).sort(),['capacity','id','location','name']);}
      const listWidth=await width(page);await screenshot('all');
      const observed={};
      for(const [status,ids] of Object.entries({pending:[104,103],in_progress:[102],ended:[101],cancelled:[106,105]})){
        const response=await filter(page,status,ids,network);
        assert.equal(response.status,200);assert.deepEqual(response.body.data.items.map(b=>b.id),ids);
        assert.ok(response.body.data.items.every(b=>b.status===status));observed[status]=ids;await width(page);
      }
      await page.locator('#history-items button').filter({hasText:'105'}).click();
      await page.waitForFunction(()=>!document.querySelector('#detail-fields').hidden);
      const cancelText=await page.locator('#detail-fields').textContent();assert.ok(cancelText.includes('合成管理员取消原因'));
      assert.ok(cancelText.includes('演示管理员'));assert.equal(await page.locator('#detail-fields svg').count(),0);await screenshot('cancelled-detail');
      await filter(page,'pending',[104,103],network);await page.keyboard.press('Enter');
      await page.waitForFunction(()=>!document.querySelector('#detail-fields').hidden);
      assert.equal(await page.evaluate(()=>document.activeElement.id),'detail-title');
      assert.equal(await page.locator('#history-items img, #detail-fields script').count(),0);
      assert.equal(await page.evaluate(()=>window.historyXss),undefined);
      const detail=await api('/api/bookings/104');assert.equal(detail.status,200);assert.equal(detail.body.data.title.length,80);assert.equal(detail.body.data.purpose.length,500);
      assert.ok((await page.locator('#detail-fields').textContent()).includes(detail.body.data.purpose));
      assert.ok((await page.locator('#detail-fields').textContent()).includes('无（未取消）'));
      const detailWidth=await width(page);await screenshot('long-text-detail');
      await page.route('**/api/bookings/104',route=>route.abort());
      await page.locator('#history-items button').filter({hasText:'104'}).click();
      await page.waitForFunction(()=>!document.querySelector('#detail-retry').hidden);
      assert.equal(await page.locator('#history-status').isDisabled(),false);assert.equal(await page.locator('#detail-fields').isVisible(),false);
      await screenshot('detail-error');await page.unroute('**/api/bookings/104');await page.locator('#detail-retry').click();
      await page.waitForFunction(()=>!document.querySelector('#detail-fields').hidden);
      await page.route('**/api/bookings/mine?**',route=>route.abort());await filter(page,'cancelled',[],network,'network');
      assert.match(await page.locator('#history-feedback').textContent(),/筛选条件已保留/);await screenshot('list-error');
      await page.unroute('**/api/bookings/mine?**');await filter(page,'cancelled',[106,105],network);
      const denied=await api('/api/bookings/201'),missing=await api('/api/bookings/999');
      assert.equal(denied.status,404);assert.deepEqual(denied,missing);
      assert.equal((await api('/api/bookings/9223372036854775808')).status,400);
      const stale=await context.newPage();await stale.goto(`${origin}/my`);await stale.waitForFunction(()=>document.querySelector('#history-items').children.length===6);
      await page.locator('.brand').focus();for(let i=0;i<3;i++)await page.keyboard.press('Tab');
      assert.equal(await page.evaluate(()=>document.activeElement.textContent),'退出登录');await page.keyboard.press('Enter');
      await page.waitForURL(`${origin}/login?logged_out=1`);assert.match(await page.locator('.notice').textContent(),/已退出登录/);
      assert.equal((await api('/api/bookings/mine?status=bad')).status,401);
      await filter(stale,'pending',[],network,'expired');assert.match(await stale.locator('#history-feedback').textContent(),/登录已失效/);
      assert.equal(await stale.locator('#history-relogin').isVisible(),true);
      assert.match(await stale.locator('#detail-feedback').textContent(),/登录已失效.*列表与详情已清空/);
      await stale.screenshot({path:path.join(outputDir,`session-expired-${viewport.width}.png`),fullPage:true});
      await page.goto(`${origin}/my`);assert.ok(page.url().includes('/login'));
      await context.close();
      const otherContext=await browser.newContext({viewport});const other=await login(otherContext,users[1]);
      await other.goto(`${origin}/my`);await other.waitForFunction(()=>document.querySelector('#history-items').children.length===1);
      await filter(other,'cancelled',[],network);assert.match(await other.locator('#history-feedback').textContent(),/暂无已取消/);
      await width(other);await other.screenshot({path:path.join(outputDir,`empty-${viewport.width}.png`),fullPage:true});await otherContext.close();
      const emptyContext=await browser.newContext({viewport});const empty=await login(emptyContext,users[3]);
      await empty.goto(`${origin}/my`);await empty.waitForFunction(()=>document.querySelector('#history-feedback').textContent.includes('还没有预约记录'));
      assert.equal(await empty.locator('#history-items > li').count(),0);await width(empty);
      await empty.screenshot({path:path.join(outputDir,`empty-all-${viewport.width}.png`),fullPage:true});await emptyContext.close();
      const adminContext=await browser.newContext({viewport});const admin=await login(adminContext,users[2]);await admin.goto(`${origin}/my`);
      await admin.waitForFunction(()=>document.querySelector('#history-items').children.length===1);
      const adminList=await adminContext.request.get(`${origin}/api/bookings/mine?user_id=1`);assert.deepEqual((await adminList.json()).data.items.map(b=>b.id),[301]);
      const adminDetail=await adminContext.request.get(`${origin}/api/bookings/105`);assert.equal(adminDetail.status(),200);
      const adminBody=await adminDetail.json();assert.equal(adminBody.data.owner_id,1);assert.ok(adminBody.data.cancel_reason.includes('合成管理员取消原因'));
      network.push({role:'admin',path:'/api/bookings/105',status:200,body:adminBody});await adminContext.close();
      fs.writeFileSync(path.join(outputDir,`history-network-${viewport.width}.jsonl`),network.map(row=>JSON.stringify(row)).join('\n')+'\n');
      assert.deepEqual(errors,[]);results.push({viewport,listWidth,detailWidth,filters:observed,exact_dto:'PASS',literal_long_text:'PASS',
        keyboard_navigation_detail_logout:'PASS',list_detail_error_recovery:'PASS',empty:'PASS',member_privacy_admin_read:'PASS',session_expiry:'PASS',page_errors:errors});
    }
    console.log(JSON.stringify({result:'PASS',browser:await browser.version(),runner:'Playwright 1.58.2',node_version:process.version,playwright_version:require('playwright/package.json').version,results},null,2));
  }finally{await browser.close();}
})().catch(error=>{
  const source=String(error.stack).match(/verify_history_browser\.cjs:[0-9]+:[0-9]+/);
  fs.writeFileSync(path.join(outputDir,'browser-failure.json'),JSON.stringify({error_type:error.name,source:source?source[0]:null},null,2));
  console.error(error.name);process.exitCode=1;
});
