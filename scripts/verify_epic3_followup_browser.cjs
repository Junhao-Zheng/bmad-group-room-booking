// Real Chrome interactions. Credentials and storage state remain in temporary memory/files only.
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const [origin,credentialsFile,outputDir,executablePath]=process.argv.slice(2);
let stage='startup';
async function main(){
  const {chromium}=require('playwright'),fixture=JSON.parse(fs.readFileSync(credentialsFile,'utf8'));
  const browser=await chromium.launch({headless:true,executablePath}),results=[];
  try{
    for(const [index,viewport] of [{width:1280,height:900},{width:390,height:844}].entries()){
      const roomId=index+1,context=await browser.newContext({viewport}),page=await context.newPage(),errors=[],network=[];
      page.on('pageerror',error=>errors.push(error.name));
      stage='login';await page.goto(origin+'/login');await page.locator('#username').fill(fixture.users[2].username);
      await page.locator('#password').fill(fixture.users[2].password);await page.locator('#password').press('Enter');await page.waitForURL(origin+'/');
      const state=await context.storageState();
      for(const mode of ['no-js','rooms-script-failed']){
        stage=mode;const guarded=await browser.newContext({viewport,storageState:state,javaScriptEnabled:mode!=='no-js'}),tab=await guarded.newPage();
        const requests=[];let scriptAborted=false;
        if(mode==='rooms-script-failed')await tab.route('**/static/rooms.js',async route=>{scriptAborted=true;await route.abort();});
        tab.on('request',request=>{const url=new URL(request.url());if(url.pathname==='/admin'||url.pathname.startsWith('/api/admin/rooms'))requests.push({method:request.method(),path:url.pathname+url.search});});
        await tab.goto(origin+'/admin');await tab.waitForLoadState('networkidle');
        for(const id of ['room-name','room-location','room-capacity','room-confirm','room-submit','room-cancel'])assert.equal(await tab.locator('#'+id).isDisabled(),true);
        assert.equal(await tab.locator('#room-script-unavailable').isVisible(),true);
        assert.equal(await tab.locator('#room-fields').getAttribute('disabled'),'');
        await tab.locator('#room-submit').click({force:true});await tab.keyboard.press('Enter');
        assert.equal(tab.url(),origin+'/admin');assert.deepEqual(requests,[{method:'GET',path:'/admin'}]);
        if(mode==='rooms-script-failed'){assert.equal(scriptAborted,true);assert.equal(await tab.locator('#block-fields').getAttribute('disabled'),null);}
        await tab.locator('section[aria-labelledby="room-form-title"]').screenshot({path:path.join(outputDir,`${mode}-${viewport.width}.png`)});
        network.push({mode,requests,no_native_get:true,write_controls_disabled:true});await guarded.close();
      }
      async function shot(name,selector){
        assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
        await page.locator(selector).screenshot({path:path.join(outputDir,`${name}-${viewport.width}.png`)});
      }
      async function done(id){await page.waitForFunction(id=>!document.getElementById(id).hasAttribute('aria-busy'),id);}
      stage='prepare-confirmation';await page.goto(origin+'/admin');
      assert.equal(await page.locator('#room-fields').getAttribute('disabled'),null);assert.equal(await page.locator('#room-script-unavailable').isVisible(),false);
      await page.locator('#block-room_id').selectOption(String(roomId));await page.locator('#block-start').fill(fixture.day+'T10:00');
      await page.locator('#block-end').fill(fixture.day+'T11:00');await page.locator('#block-reason').fill('合成维护原因，成员可见');
      assert.match(await page.locator('label[for="block-reason"]').textContent(),/所有已登录成员可见/);
      assert.match(await page.locator('#block-summary').textContent(),/所有已登录成员可见/);await page.locator('#block-confirm').check();
      const blockDraft=await page.locator('#block-form').evaluate(form=>Object.fromEntries(new FormData(form)));
      stage='room-save';await page.locator('#admin-rooms button').filter({hasText:`编辑会议室 ${roomId}`}).click();
      await page.locator('#room-name').fill(`更新后的会议室 ${roomId}`);await page.locator('#room-confirm').check();
      stage='committed-response-held';let committed,releaseResponse;
      const committedResponse=new Promise(resolve=>{committed=resolve;}),responseGate=new Promise(resolve=>{releaseResponse=resolve;});
      await page.route('**/api/admin/rooms/*',async route=>{
        // Forward once to the actual server, wait for its committed 200, then drop only the response.
        const response=await route.fetch();committed({status:response.status(),body:await response.json()});
        await responseGate;await route.abort();
      });
      const dependentRequests=[];
      const watchDependent=request=>{const url=new URL(request.url());if(url.pathname==='/api/rooms'||url.pathname==='/api/admin/blocks')dependentRequests.push({method:request.method(),path:url.pathname});};
      page.on('request',watchDependent);await page.locator('#room-submit').click();const committedResult=await committedResponse;
      assert.equal(committedResult.status,200);assert.equal(committedResult.body.data.name,`更新后的会议室 ${roomId}`);
      assert.equal(await page.locator('#room-form').getAttribute('aria-busy'),'true');
      assert.equal(await page.locator('#block-confirm').isChecked(),false);
      for(const selector of ['#block-confirm','#block-submit','#block-rooms-refresh','#admin-blocks-submit','#admin-bookings-submit'])assert.equal(await page.locator(selector).isDisabled(),true);
      await page.locator('#block-submit').click({force:true});await page.locator('#block-rooms-refresh').click({force:true});
      assert.deepEqual(dependentRequests,[]);await shot('committed-response-held','section[aria-labelledby="block-form-title"]');
      releaseResponse();await page.waitForFunction(()=>document.getElementById('room-feedback').textContent.includes('未能确认'));await done('room-form');
      await page.unroute('**/api/admin/rooms/*');assert.deepEqual(dependentRequests,[]);
      assert.equal(await page.locator('#block-confirm').isDisabled(),true);assert.equal(await page.locator('#block-submit').isDisabled(),true);
      assert.equal(await page.locator('#block-rooms-refresh').isDisabled(),false);assert.equal(await page.locator('#room-confirm').isChecked(),false);
      assert.equal(await page.locator('#room-name').inputValue(),`更新后的会议室 ${roomId}`);
      await page.locator('#block-submit').click({force:true});assert.deepEqual(dependentRequests,[]);
      const persisted=(await (await context.request.get(origin+'/api/rooms')).json()).data.items.find(room=>room.id===roomId);
      assert.deepEqual(persisted,committedResult.body.data);
      network.push({operation:'committed-room-update-response-discarded',status:committedResult.status,data:persisted,
        waiting_prevents_dependent_requests:true,unknown_keeps_block_confirmation_disabled:true,dependent_requests:dependentRequests.slice()});
      await shot('committed-response-lost','section[aria-labelledby="block-form-title"]');page.off('request',watchDependent);
      // A deliberate directory check then identical save confirms the same facts without another mutation.
      await page.locator('#rooms-refresh').click();await done('room-form');
      assert.equal(await page.locator('#block-confirm').isDisabled(),true);
      stage='no-change-room-save';await page.locator('#room-confirm').check();
      const saveResponse=page.waitForResponse(response=>new URL(response.url()).pathname===`/api/admin/rooms/${roomId}`);
      await page.locator('#room-submit').click();const saved=await saveResponse;assert.equal(saved.status(),200);await done('room-form');
      network.push({operation:'room-save',status:saved.status(),data:(await saved.json()).data});
      assert.equal(await page.locator('#block-confirm').isChecked(),false);assert.equal(await page.locator('#block-confirm').isDisabled(),true);
      assert.equal(await page.locator('#block-submit').isDisabled(),true);assert.equal(await page.locator('#block-rooms-refresh').isDisabled(),false);
      assert.deepEqual(await page.locator('#block-form').evaluate(form=>Object.fromEntries(new FormData(form))),blockDraft);
      assert.match(await page.locator('#block-rooms-feedback').textContent(),/旧核对已失效/);assert.match(await page.locator('#block-summary').textContent(),/选项已过期/);
      assert.doesNotMatch(await page.locator('#block-rooms-feedback').textContent(),/资料已更改|资料已保存/);
      await shot('confirmation-invalidated','section[aria-labelledby="block-form-title"]');
      stage='refresh-failure';await page.route('**/api/rooms',route=>route.fulfill({status:503,contentType:'application/json',body:JSON.stringify({ok:false,error:{code:'STORE_BUSY',message:'合成刷新失败',fields:{},conflicts:[]}})}));
      await page.locator('#block-rooms-refresh').click();await page.waitForFunction(()=>document.getElementById('block-rooms-feedback').textContent.includes('刷新失败'));
      assert.equal(await page.locator('#block-confirm').isDisabled(),true);assert.match(await page.locator('#block-rooms-feedback').textContent(),/旧核对仍已失效/);
      await shot('refresh-failed','section[aria-labelledby="block-form-title"]');await page.unroute('**/api/rooms');
      stage='refresh-reconfirm';await page.locator('#block-rooms-refresh').click();await page.waitForFunction(()=>document.getElementById('block-rooms-feedback').textContent.includes('选项已刷新'));
      assert.equal(await page.locator('#block-confirm').isChecked(),false);assert.equal(await page.locator('#block-confirm').isDisabled(),false);
      for(const selector of ['#block-room_id','#admin-bookings-room_id','#admin-blocks-room_id'])assert.equal(await page.locator(`${selector} option[value="${roomId}"]`).textContent(),`更新后的会议室 ${roomId} · 合成楼`);
      assert.match(await page.locator('#block-summary').textContent(),new RegExp(`更新后的会议室 ${roomId}`));
      await shot('refreshed-unconfirmed','section[aria-labelledby="block-form-title"]');
      await page.locator('#block-confirm').check();const createdResponse=page.waitForResponse(response=>new URL(response.url()).pathname==='/api/admin/blocks'&&response.request().method()==='POST');
      await page.locator('#block-submit').click();const created=await createdResponse;assert.equal(created.status(),201);await done('block-form');
      assert.match(await page.locator('#block-feedback').textContent(),/已创建/);assert.equal(await page.locator('#block-confirm').isChecked(),false);
      assert.equal(await page.locator('#admin-blocks-items li').count(),index+1);network.push({operation:'create-after-reconfirmation',status:created.status(),data:(await created.json()).data});
      await shot('created','section[aria-labelledby="block-form-title"]');
      stage='unknown-room-save';let unknownRequests=0;await page.route('**/api/admin/rooms/*',async route=>{unknownRequests++;await route.abort();});
      await page.locator('#room-name').fill('未知结果草稿');await page.locator('#room-confirm').check();await page.locator('#room-submit').click();
      await page.waitForFunction(()=>document.getElementById('room-feedback').textContent.includes('未能确认'));
      assert.equal(await page.locator('#room-name').inputValue(),'未知结果草稿');assert.equal(await page.locator('#room-confirm').isChecked(),false);
      assert.match(await page.locator('#room-feedback').textContent(),/刷新目录核对.*重新勾选确认/);
      await page.locator('#room-submit').click();assert.equal(unknownRequests,1);await shot('unknown-room-save','section[aria-labelledby="room-form-title"]');
      assert.deepEqual(errors,[]);fs.writeFileSync(path.join(outputDir,`observations-${viewport.width}.json`),JSON.stringify(network,null,2));
      results.push({...viewport,room_save:true,confirmation_invalidated:true,failed_refresh_remains_stale:true,explicit_refresh_and_reconfirm:true,
        committed_room_update_response_discarded:true,pending_blocks_reconfirmation_and_refresh:true,no_change_save_requires_recheck:true,
        disabled_js_guard:true,failed_script_guard:true,no_native_get:true,reason_visibility:true,unknown_save_clears_confirmation:true,page_errors:errors});await context.close();
    }
    return {result:'PASS',completed:true,browser_version:browser.version(),viewports:results};
  }finally{await browser.close();}
}
main().then(result=>process.stdout.write(JSON.stringify(result))).catch(error=>{
  // Do not output Playwright call logs, fill values, credentials, cookies or headers.
  const location=String(error.stack).match(/verify_epic3_followup_browser\.cjs:(\d+):(\d+)/);
  const safe={stage,error_type:error.name,source:location?{line:Number(location[1]),column:Number(location[2])}:null};
  fs.writeFileSync(path.join(outputDir,'failure.json'),JSON.stringify(safe));process.exitCode=1;
});
