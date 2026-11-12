// Real browser interaction on isolated synthetic data; never emit credentials.
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const [origin,credentialsFile,outputDir,executablePath]=process.argv.slice(2);
const STAGES=new Set(['startup','fault','login','select','validation','csrf','waiting','success','unknown','expired','complete']);
const SAFE_TYPES=new Set(['AssertionError','Error','TypeError','TimeoutError','SyntaxError','RangeError']);
let currentStage='startup';
function safeDiagnostic(error,stage=currentStage){
  let source=null;
  for(const line of String(error?.stack||'').split('\n')){
    if(!/^\s+at /.test(line))continue;
    const marker=line.lastIndexOf(__filename+':');if(marker<0)continue;
    const match=line.slice(marker+__filename.length+1).match(/^([0-9]+):([0-9]+)\)?$/);
    if(match&&Number(match[1])>0&&Number(match[1])<1000000&&Number(match[2])>0&&Number(match[2])<1000000){source={file:'scripts/verify_block_revoke_browser.cjs',line:Number(match[1]),column:Number(match[2])};break;}
  }
  return {stage:STAGES.has(stage)?stage:'startup',error_type:SAFE_TYPES.has(error?.name)?error.name:'Error',source};
}
function stage(name,viewport){currentStage=name;fs.writeFileSync(path.join(outputDir,'progress.json'),JSON.stringify({stage:name,viewport}));}
async function main(){
  const {chromium}=require('playwright');
  const users=JSON.parse(fs.readFileSync(credentialsFile,'utf8')).users;
  const browser=await chromium.launch({headless:true,executablePath});const browserVersion=browser.version(),results=[];
  try{
    if(process.env.REVOKE_BROWSER_FAULT){
      stage('fault');
      if(process.env.REVOKE_BROWSER_FAULT==='timeout')await new Promise(()=>{});
      throw Error('fill '+process.env.REVOKE_BROWSER_SENTINEL+' '+users[2].password);
    }
    for(const viewport of [{width:1280,height:800},{width:390,height:844}]){
      const {width,height}=viewport;stage('login',viewport);
      const context=await browser.newContext({viewport}),page=await context.newPage(),errors=[],network=[];
      page.on('pageerror',e=>errors.push(SAFE_TYPES.has(e.name)?e.name:'Error'));let posts=0;
      page.on('request',r=>{if(r.method()==='POST'&&r.url().endsWith('/revoke'))posts++;});
      await page.goto(origin+'/login');await page.locator('#username').fill(users[2].username);await page.locator('#password').fill(users[2].password);
      await page.locator('#password').press('Enter');await page.waitForURL(origin+'/');await page.goto(origin+'/admin');
      async function settled(){await page.waitForFunction(()=>!document.querySelector('#revoke-form').hasAttribute('aria-busy'));}
      async function query(){await page.locator('#admin-blocks-submit').click();await page.waitForFunction(()=>!document.querySelector('#admin-blocks-form').hasAttribute('aria-busy'));}
      async function submit(){const wait=page.waitForResponse(r=>r.request().method()==='POST'&&r.url().endsWith('/revoke'));await page.locator('#revoke-submit').click();const response=await wait;const body=await response.json();network.push({path:new URL(response.url()).pathname,status:response.status(),body});await settled();return {status:response.status(),body};}
      async function shot(name){assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);await page.locator('#revoke-panel').screenshot({path:path.join(outputDir,`${name}-${width}.png`)});}
      stage('select',viewport);
      async function assertSummary(start,end){const lines=(await page.locator('#revoke-summary').textContent()).split('\n');assert.equal(lines[2],`北京时间：2026-11-12 ${start}:00 至 2026-11-12 ${end}:00`);assert.equal(lines[3],'原停用原因：合成维护 <检查设备>');}
      await query();assert.equal(await page.getByRole('button',{name:'选择撤销停用 101',exact:true}).count(),0);
      assert.equal(await page.getByRole('button',{name:'选择撤销停用 110',exact:true}).count(),0);
      const id=width===1280?113:112,unknownId=width===1280?114:115;
      await page.getByRole('button',{name:`选择撤销停用 ${id}`,exact:true}).click();
      await assertSummary(width===1280?'12:00':'09:00',width===1280?'14:00':'11:00');
      await page.locator('#revoke-reason').fill('保留查询草稿');await page.locator('#revoke-confirm').check();await query();
      assert.equal(await page.locator('#revoke-summary').textContent(),'');assert.equal(await page.locator('#revoke-reason').inputValue(),'保留查询草稿');assert.equal(await page.locator('#revoke-submit').isDisabled(),true);
      await page.getByRole('button',{name:`选择撤销停用 ${id}`,exact:true}).click();await page.locator('#revoke-reason').fill('保留筛选草稿');await page.locator('#revoke-confirm').check();
      await page.locator('#admin-blocks-status').selectOption('pending');assert.equal(await page.locator('#revoke-summary').textContent(),'');assert.equal(await page.locator('#revoke-reason').inputValue(),'保留筛选草稿');assert.equal(await page.locator('#revoke-submit').isDisabled(),true);
      await page.locator('#admin-blocks-status').selectOption('');await query();await page.getByRole('button',{name:`选择撤销停用 ${id}`,exact:true}).click();
      await assertSummary(width===1280?'12:00':'09:00',width===1280?'14:00':'11:00');
      assert.equal(await page.locator('#revoke-confirm').isChecked(),false);
      assert.match(await page.locator('#revoke-summary').textContent(),/原停用原因：合成维护 <检查设备>/);
      assert.equal(await page.locator('#revoke-summary img,#revoke-summary script').count(),0);
      stage('validation',viewport);await page.locator('#revoke-reason').fill('   ');await page.locator('#revoke-submit').click();assert.equal(posts,0);
      await page.locator('#revoke-confirm').check();const rejected=await submit();assert.equal(rejected.status,400);
      assert.equal(await page.locator('#revoke-reason').inputValue(),'   ');assert.equal(await page.evaluate(()=>document.activeElement.id),'revoke-reason');await shot('validation-error');
      const reason=`  <img src=x onerror="window.revokeXss=1">完成维护 ${width}  `;
      await page.locator('#revoke-reason').fill(reason);await page.locator('#revoke-confirm').check();
      await page.locator('#revoke-reason').fill(reason+'!');assert.equal(await page.locator('#revoke-confirm').isChecked(),false);await page.locator('#revoke-reason').fill(reason);
      stage('csrf',viewport);await page.route('**/api/admin/blocks/*/revoke',async route=>{const headers=route.request().headers();delete headers['x-csrf-token'];await route.continue({headers});});
      await page.locator('#revoke-confirm').check();assert.equal((await submit()).status,403);assert.equal(await page.locator('#revoke-reason').inputValue(),reason);
      assert.equal(await page.locator('#revoke-relogin').isVisible(),true);await page.unroute('**/api/admin/blocks/*/revoke');
      stage('waiting',viewport);let release;const gate=new Promise(resolve=>{release=resolve;});
      await page.route('**/api/admin/blocks/*/revoke',async route=>{await gate;await route.continue();});
      await page.locator('#revoke-confirm').check();const pending=submit();
      await page.waitForFunction(()=>document.querySelector('#revoke-form').hasAttribute('aria-busy'));
      assert.equal(await page.locator('#revoke-reason').isDisabled(),true);assert.equal(await page.locator('#block-submit').isDisabled(),true);
      assert.equal(await page.locator('#admin-blocks-submit').isDisabled(),true);assert.match(await page.locator('#revoke-feedback').textContent(),/正在撤销/);await shot('waiting');
      stage('success',viewport);release();const success=await pending;assert.equal(success.status,200);assert.equal(success.body.data.status,'revoked');assert.equal(success.body.data.revoke_reason,reason.trim());
      assert.equal(await page.locator('#revoke-form').isVisible(),false);assert.match(await page.locator('#revoke-summary').textContent(),/首次撤销：.*演示管理员/);
      assert.equal(await page.locator('#revoke-summary img,#revoke-summary script').count(),0);assert.equal(await page.evaluate(()=>window.revokeXss),undefined);await shot('success');
      await page.unroute('**/api/admin/blocks/*/revoke');
      stage('unknown',viewport);await page.getByRole('button',{name:`选择撤销停用 ${unknownId}`,exact:true}).click();await assertSummary(width===1280?'12:00':'14:00',width===1280?'13:00':'15:00');await page.locator('#revoke-reason').fill('首次撤销原因');await page.locator('#revoke-confirm').check();
      let committed;
      await page.route('**/api/admin/blocks/*/revoke',async route=>{const response=await route.fetch();assert.equal(response.status(),200);committed=(await response.json()).data;await route.abort();});
      const previousPosts=posts;await page.locator('#revoke-submit').click();
      await page.waitForFunction(()=>document.querySelector('#revoke-feedback').textContent.includes('未能确认'));await settled();
      assert.equal(await page.locator('#revoke-reason').inputValue(),'首次撤销原因');assert.equal(await page.locator('#revoke-confirm').isChecked(),false);assert.equal(posts,previousPosts+1);await shot('unknown-outcome');
      await page.unroute('**/api/admin/blocks/*/revoke');await page.locator('#revoke-reason').fill('后续不同撤销原因');await page.locator('#revoke-confirm').check();
      const repeated=await submit();assert.equal(repeated.status,200);assert.deepEqual(repeated.body.data,committed);assert.match(await page.locator('#revoke-summary').textContent(),/撤销原因：首次撤销原因/);
      stage('expired',viewport);await page.getByRole('button',{name:'选择撤销停用 108',exact:true}).click();await page.locator('#revoke-reason').fill('失效身份仍保留草稿');await page.locator('#revoke-confirm').check();
      const identity=(await (await context.request.get(origin+'/api/me')).json()).data;
      assert.equal((await context.request.post(origin+'/api/logout',{data:{},headers:{Origin:origin,'X-CSRF-Token':identity.csrf_token}})).status(),200);
      assert.equal((await submit()).status,401);assert.equal(await page.locator('#revoke-reason').inputValue(),'失效身份仍保留草稿');assert.equal(await page.locator('#revoke-submit').isDisabled(),true);
      assert.equal(await page.locator('#admin-blocks-items > li').count(),0);await shot('expired-session');
      assert.deepEqual(errors,[]);fs.writeFileSync(path.join(outputDir,`network-${width}.json`),JSON.stringify(network,null,2));
      results.push({width,height,exact_selected_intervals:true,refresh_and_filter_invalidate:true,validation:true,confirmation:true,csrf:true,waiting:true,success:true,unknown_then_idempotent_retry:true,expired_session:true,safe_text:true,no_horizontal_overflow:true,page_errors:errors});
      await context.close();
    }
  }finally{await browser.close();}
  stage('complete');process.stdout.write(JSON.stringify({result:'PASS',browser_version:browserVersion,viewports:results}));
}
if(require.main===module)main().catch(error=>{
  const diagnostics=safeDiagnostic(error);
  try{fs.writeFileSync(path.join(outputDir,'failure-diagnostics.json'),JSON.stringify(diagnostics));}catch{}
  process.stderr.write(JSON.stringify(diagnostics)+'\n');process.exitCode=1;
});
module.exports={safeDiagnostic};
