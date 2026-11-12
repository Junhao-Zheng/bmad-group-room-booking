// Invoked by the Python launcher; credentials are temporary, private, and never logged.
const { chromium } = require('playwright');
const fs = require('node:fs');
const path = require('node:path');
const {createHash} = require('node:crypto');
const assert = require('node:assert/strict');
const PINNED_PLAYWRIGHT = '1.58.2';

async function submitSchedule(page) {
  await page.locator('#schedule-form button').focus();
  assert.equal(await page.evaluate(() => document.activeElement === document.querySelector('#schedule-form button')), true);
  await page.keyboard.press('Enter');
}

async function submitAvailability(page) {
  await page.locator('#availability-form button').focus();
  await page.keyboard.press('Enter');
}

(async () => {
  assert.equal(require('playwright/package.json').version, PINNED_PLAYWRIGHT);
  const [origin, credentialsFile, outputDir, executablePath, scenario] = process.argv.slice(2);
  const users = JSON.parse(fs.readFileSync(credentialsFile, 'utf8')).users;
  const browser = await chromium.launch({ headless: true, ...(executablePath ? { executablePath } : {}) });
  const results = [];
  try {
    for (const viewport of [{width:1280,height:800},{width:390,height:844}]) {
      const context = await browser.newContext({viewport});
      const page = await context.newPage();
      const errors = [];
      page.on('pageerror', error => errors.push(error.name));
      await page.goto(`${origin}/login`);
      await page.keyboard.press('Tab');
      await page.keyboard.press('Tab');
      await page.keyboard.press('Tab');
      assert.equal(await page.evaluate(() => document.activeElement.id), 'username');
      const loginWidth = await page.evaluate(() => ({document:document.documentElement.scrollWidth,viewport:innerWidth}));
      assert.ok(loginWidth.document <= loginWidth.viewport);
      assert.equal(await page.locator('label[for=username]').textContent(), '账号');
      assert.equal(await page.locator('label[for=password]').textContent(), '密码');
      await page.screenshot({path:path.join(outputDir,`login-${viewport.width}.png`),fullPage:true});
      await page.keyboard.type(users[0].username);
      await page.keyboard.press('Tab');
      assert.equal(await page.evaluate(() => document.activeElement.id), 'password');
      await page.keyboard.type(users[0].password);
      await page.keyboard.press('Enter');
      await page.waitForURL(`${origin}/`);
      assert.ok((await page.locator('.account-name').textContent()).includes(users[0].display_name));
      assert.equal(await page.locator('.role').textContent(), '成员');
      const me = await context.request.get(`${origin}/api/me`);
      assert.equal(me.status(), 200);
      const identity = (await me.json()).data;
      assert.equal(identity.display_name, users[0].display_name);
      assert.equal(identity.role, 'member');
      const oldCookie = (await context.cookies()).find(cookie => cookie.name === 'grb_session');
      assert.ok(oldCookie);
      const homeWidth = await page.evaluate(() => ({document:document.documentElement.scrollWidth,viewport:innerWidth}));
      assert.ok(homeWidth.document <= homeWidth.viewport);
      await page.screenshot({path:path.join(outputDir,`home-${viewport.width}.png`),fullPage:true});
      let scheduleChecks, availabilityChecks, stalePage;
      if (scenario === 'schedule' || scenario === 'availability' || scenario === 'booking') {
        assert.equal(await page.locator('label[for=room_id]').textContent(), '会议室');
        assert.equal(await page.locator('label[for=date]').textContent(), '日期（北京时间）');
        await submitSchedule(page);
        await page.waitForFunction(() => document.querySelector('#room_id').getAttribute('aria-invalid') === 'true');
        assert.equal(await page.evaluate(() => document.activeElement.id), 'room_id');
        await page.locator('#room_id').selectOption('10');
        await submitSchedule(page);
        await page.waitForFunction(() => document.querySelector('#date').getAttribute('aria-invalid') === 'true');
        assert.equal(await page.evaluate(() => document.activeElement.id), 'date');
        await page.locator('#date').fill('2026-11-12');
        let releaseQuery;
        const queryGate = new Promise(resolve => { releaseQuery = resolve; });
        await page.route('**/api/schedule?**', async route => { await queryGate; await route.continue(); });
        await submitSchedule(page);
        assert.equal(await page.locator('#schedule-form').getAttribute('aria-busy'), 'true');
        assert.equal(await page.locator('#schedule-form button').isDisabled(), true);
        assert.equal(await page.locator('#room_id').isDisabled(), true);
        assert.equal(await page.locator('#date').isDisabled(), true);
        assert.match(await page.locator('#schedule-feedback').textContent(), /正在查询/);
        releaseQuery();
        await page.waitForFunction(() => document.querySelector('#schedule-feedback').textContent.includes('查询成功'));
        await page.unroute('**/api/schedule?**');
        assert.equal(await page.locator('#room_id').isDisabled(), false);
        assert.equal(await page.locator('#date').isDisabled(), false);
        assert.equal(await page.locator('#schedule-form button').isDisabled(), false);
        assert.equal(await page.locator('#schedule-form').getAttribute('aria-busy'), null);
        assert.equal(await page.locator('#schedule-items > li').count(), 5);
        assert.match(await page.locator('#schedule-conditions').textContent(), /合成 A.*2026-11-12.*北京时间/);
        assert.ok((await page.locator('#schedule-items').textContent()).includes('<img src=x onerror="window.fixtureXss=1">合成活动'));
        assert.ok((await page.locator('#schedule-items').textContent()).includes('<script>window.fixtureXss=2</script>演示乙'));
        assert.equal(await page.locator('#schedule-items img, #schedule-items script').count(), 0);
        assert.equal(await page.evaluate(() => window.fixtureXss), undefined);
        const schedule = (await (await context.request.get(`${origin}/api/schedule?room_id=10&date=2026-11-12`)).json()).data;
        assert.deepEqual(schedule.items.map(item => item.record.status), ['ended', 'ended', 'in_progress', 'pending', 'pending']);
        assert.deepEqual(await page.locator('.schedule-status').allTextContents(), ['停用 · 已结束', '预约 · 已结束', '预约 · 进行中', '预约 · 待开始', '停用 · 待开始']);
        const block = schedule.items[0].record, booking = schedule.items[2].record;
        assert.deepEqual([block.start_at, block.end_at, block.start_local, block.end_local], [1794409200, 1794416400, '2026-11-11T23:00:00+08:00', '2026-11-12T01:00:00+08:00']);
        assert.deepEqual([booking.start_at, booking.end_at, booking.start_local, booking.end_local], [1794448800, 1794452400, '2026-11-12T10:00:00+08:00', '2026-11-12T11:00:00+08:00']);
        assert.equal(await page.locator('#schedule-items > li').nth(0).locator('p').first().textContent(), '2026-11-11 23:00 — 2026-11-12 01:00');
        assert.equal(await page.locator('#schedule-items > li').nth(2).locator('p').first().textContent(), '2026-11-12 10:00 — 2026-11-12 11:00');
        const common = ['room_id','room_name','start_at','start_local','end_at','end_local','status'];
        for (const item of schedule.items) {
          assert.deepEqual(Object.keys(item).sort(), ['kind','record']);
          assert.deepEqual(Object.keys(item.record).sort(), [...common,...(item.kind === 'booking' ? ['title','owner_display_name'] : ['id','reason'])].sort());
        }
        const dom = await page.content();
        for (const privateValue of ['PRIVATE_PURPOSE_NEVER_SHARED','PRIVATE_CANCELLATION_NEVER_SHARED',users[1].username]) assert.ok(!dom.includes(privateValue));
        const scheduleWidth = await page.evaluate(() => ({document:document.documentElement.scrollWidth,viewport:innerWidth}));
        assert.ok(scheduleWidth.document <= scheduleWidth.viewport);
        await page.evaluate(() => window.scrollTo(0, 0));
        await page.screenshot({path:path.join(outputDir,`schedule-${viewport.width}.png`),fullPage:true});
        await page.locator('#date').fill('2026-11-13');
        await submitSchedule(page);
        await page.waitForFunction(() => document.querySelector('#schedule-feedback').textContent.includes('共 1 项'));
        assert.equal(await page.locator('#schedule-items > li').count(), 1);
        assert.match(await page.locator('#schedule-items').textContent(), /2026-11-13 00:00/);
        await page.locator('#room_id').selectOption('30');
        await page.locator('#date').fill('2026-11-12');
        await submitSchedule(page);
        await page.waitForFunction(() => document.querySelector('#schedule-feedback').textContent.includes('当天暂无'));
        assert.equal(await page.locator('#schedule-items > li').count(), 0);
        assert.equal(await page.locator('#date').inputValue(), '2026-11-12');
        assert.equal(await page.locator('#room_id').inputValue(), '30');
        await page.evaluate(() => window.scrollTo(0, 0));
        await page.screenshot({path:path.join(outputDir,`empty-${viewport.width}.png`),fullPage:true});
        // A real server-side 404 retains the selected date and makes the error actionable.
        await page.locator('#room_id').evaluate(select => { const option = new Option('不存在的合成房间', '999'); select.add(option); select.value = '999'; });
        await submitSchedule(page);
        await page.waitForFunction(() => document.querySelector('#schedule-feedback').textContent.includes('会议室不存在'));
        assert.equal(await page.locator('#schedule-feedback').getAttribute('role'), 'alert');
        assert.equal(await page.locator('#date').inputValue(), '2026-11-12');
        // With scripts disabled, the directory remains readable and submission is unavailable.
        const noScriptContext = await browser.newContext({viewport, javaScriptEnabled: false, storageState: await context.storageState()});
        const noScriptPage = await noScriptContext.newPage();
        await noScriptPage.goto(`${origin}/`);
        assert.equal(await noScriptPage.locator('.room-list > li').count(), 3);
        assert.match((await noScriptPage.locator('noscript').allTextContents()).join(' '), /查询日程需要启用 JavaScript/);
        assert.equal(await noScriptPage.locator('#schedule-form button').isDisabled(), true);
        assert.equal(await noScriptPage.locator('#availability-form button').isDisabled(), true);
        await noScriptContext.close();
        scheduleChecks = {scheduleWidth,labels:'PASS',loading:'PASS',pending_inputs_disabled_and_restored:'PASS',field_error:'PASS',keyboard_schedule_submit:'PASS',keyboard_room_and_date_error_focus:'PASS',fixed_clock_status_texts:'PASS',exact_api_intervals:'PASS',exact_display_intervals:'PASS',no_script_notice_and_readable_directory:'PASS',shared_contract:'PASS',literal_html_and_xss:'PASS',private_values_absent:'PASS',half_open_midnight:'PASS',empty_result:'PASS',error_retains_conditions:'PASS'};
        stalePage = await context.newPage();
        await stalePage.goto(`${origin}/`);
      }
      if (scenario === 'availability' || scenario === 'booking') {
        for (const name of ['start', 'end', 'attendees']) {
          assert.equal(await page.locator(`label[for=${name}]`).count(), 1);
          assert.equal(await page.locator(`#${name}`).evaluate(input => input.required), true);
        }
        assert.equal(await page.locator('#start').getAttribute('step'), '1800');
        assert.equal(await page.locator('#end').getAttribute('step'), '1800');
        assert.equal(await page.locator('#attendees').getAttribute('min'), '1');
        await submitAvailability(page);
        await page.waitForFunction(() => document.querySelector('#start').getAttribute('aria-invalid') === 'true');
        assert.equal(await page.evaluate(() => document.activeElement.id), 'start');
        await page.locator('#start').fill('2026-11-12T12:00');
        await page.locator('#end').fill('2026-11-12T12:30');
        await page.locator('#attendees').fill('0');
        await submitAvailability(page);
        await page.waitForFunction(() => document.querySelector('#attendees').getAttribute('aria-invalid') === 'true');
        assert.equal(await page.evaluate(() => document.activeElement.id), 'attendees');
        await page.locator('#attendees').fill('10');
        let release;
        const gate = new Promise(resolve => { release = resolve; });
        await page.route('**/api/availability?**', async route => { await gate; await route.continue(); });
        await submitAvailability(page);
        assert.equal(await page.locator('#availability-form').getAttribute('aria-busy'), 'true');
        for (const name of ['start', 'end', 'attendees']) assert.equal(await page.locator(`#${name}`).isDisabled(), true);
        assert.match(await page.locator('#availability-feedback').textContent(), /正在查询/);
        await page.screenshot({path:path.join(outputDir,`availability-loading-${viewport.width}.png`),fullPage:true});
        release();
        await page.waitForFunction(() => document.querySelector('#availability-feedback').textContent.includes('找到 3 间'));
        assert.equal(await page.evaluate(() => document.activeElement === document.querySelector('#availability-form button')), true);
        await page.keyboard.press('Tab');
        assert.equal(await page.evaluate(() => document.activeElement.classList.contains('booking-select')), true);
        await page.unroute('**/api/availability?**');
        assert.equal(await page.locator('#availability-items > li').count(), 3);
        assert.match(await page.locator('#availability-items').textContent(), /合成 C <讨论室>/);
        assert.equal(await page.locator('#availability-items 讨论室').count(), 0);
        assert.match(await page.locator('#availability-conditions').textContent(), /2026-11-12 12:00.*12:30.*北京时间.*10 人/);
        assert.match(await page.locator('#availability-feedback').textContent(), /不保留时段/);
        for (const name of ['start', 'end', 'attendees']) assert.equal(await page.locator(`#${name}`).isDisabled(), false);
        const availableWidth = await page.evaluate(() => ({document:document.documentElement.scrollWidth,viewport:innerWidth}));
        assert.ok(availableWidth.document <= availableWidth.viewport);
        await page.evaluate(() => window.scrollTo(0, 0));
        await page.screenshot({path:path.join(outputDir,`availability-${viewport.width}.png`),fullPage:true});
        await page.locator('#attendees').fill('1001');
        await submitAvailability(page);
        await page.waitForFunction(() => document.querySelector('#availability-feedback').textContent.includes('没有符合条件'));
        assert.equal(await page.evaluate(() => document.activeElement === document.querySelector('#availability-form button')), true);
        await page.keyboard.press('Tab');
        assert.equal(await page.evaluate(() => document.activeElement.id), 'room_id');
        assert.equal(await page.locator('#availability-items > li').count(), 0);
        assert.equal(await page.locator('#attendees').inputValue(), '1001');
        await page.screenshot({path:path.join(outputDir,`availability-empty-${viewport.width}.png`),fullPage:true});
        await page.locator('#start').fill('2026-11-12T23:30');
        await page.locator('#end').fill('2026-11-13T00:00');
        await submitAvailability(page);
        await page.waitForFunction(() => document.querySelector('#end').getAttribute('aria-invalid') === 'true');
        assert.equal(await page.evaluate(() => document.activeElement.id), 'end');
        assert.match(await page.locator('#end-error').textContent(), /同一.*00:00/);
        assert.equal(await page.locator('#end').inputValue(), '2026-11-13T00:00');
        await page.screenshot({path:path.join(outputDir,`availability-error-${viewport.width}.png`),fullPage:true});
        await page.locator('#start').fill('2026-11-12T12:00');
        await page.locator('#end').fill('2026-11-12T12:30');
        await page.route('**/api/availability?**', route => route.abort());
        await submitAvailability(page);
        await page.waitForFunction(() => document.querySelector('#availability-feedback').textContent.includes('检查网络'));
        assert.equal(await page.locator('#attendees').inputValue(), '1001');
        assert.equal(await page.locator('#availability-form button').isDisabled(), false);
        await page.unroute('**/api/availability?**');
        availabilityChecks = {availableWidth,labels:'PASS',required_semantics:'PASS',half_hour_controls:'PASS',keyboard_submit:'PASS',loading:'PASS',restored_controls:'PASS',success_and_empty_button_focus:'PASS',success_and_empty_next_tab:'PASS',success_exact_conditions:'PASS',literal_room_text:'PASS',empty_result:'PASS',time_and_attendees_field_errors:'PASS',network_failure_retains_conditions:'PASS',query_does_not_reserve_notice:'PASS'};
      }
      let bookingChecks;
      if (scenario === 'booking') {
        const date = viewport.width === 1280 ? '2026-11-16' : '2026-11-17';
        async function selectRoom(target) {
          await target.locator('#start').fill(`${date}T12:00`);
          await target.locator('#end').fill(`${date}T13:00`);
          await target.locator('#attendees').fill('5');
          await submitAvailability(target);
          await target.waitForFunction(() => document.querySelectorAll('.booking-select').length === 3);
          const labels = await target.locator('.booking-select').evaluateAll(buttons => buttons.map(button => button.getAttribute('aria-label')));
          assert.deepEqual(labels, ['选择 合成 A（演示楼 101）并填写活动','选择 合成 A（演示楼 202）并填写活动','选择 合成 C <讨论室>（演示楼 303）并填写活动']);
          await target.locator('.booking-select').last().click();
          assert.equal(await target.evaluate(() => document.activeElement.id), 'booking-name');
        }
        await selectRoom(page);
        const competing = await context.newPage();
        await competing.goto(`${origin}/`);
        await selectRoom(competing);
        const title = '<img src=x onerror="window.bookingXss=1">中文讨论 🧪';
        const purpose = '  <script>window.bookingXss=2</script> 合成用途  ';
        await page.locator('#booking-name').fill(title);
        await page.locator('#booking-purpose').fill(purpose);
        let bookingRequests = 0, queryRequests = 0;
        page.on('request', request => {
          if (request.url().endsWith('/api/bookings')) bookingRequests++;
          if (request.url().includes('/api/availability?')) queryRequests++;
        });
        // Query first: preserve its disabled state and reject creation before any POST.
        let releaseQuery;
        const queryGate = new Promise(resolve => { releaseQuery = resolve; });
        await page.route('**/api/availability?**', async route => { await queryGate; await route.continue(); });
        await submitAvailability(page);
        await page.waitForFunction(() => document.querySelector('#availability-form').getAttribute('aria-busy') === 'true');
        await page.locator('#booking-form button[type=submit]').click();
        assert.match(await page.locator('#booking-feedback').textContent(), /仍在查询.*稍候/);
        assert.equal(bookingRequests, 0);
        assert.equal(await page.locator('#booking-form').getAttribute('aria-busy'), null);
        assert.equal(await page.locator('#availability-form button').isDisabled(), true);
        releaseQuery();
        await page.waitForFunction(() => document.querySelector('#availability-feedback').textContent.includes('找到 3 间'));
        await page.unroute('**/api/availability?**');
        assert.equal(await page.locator('#availability-form button').isDisabled(), false);
        let release;
        const gate = new Promise(resolve => { release = resolve; });
        await page.route('**/api/bookings', async route => { await gate; await route.continue(); });
        await page.locator('#booking-form button[type=submit]').click();
        await page.waitForFunction(() => document.querySelector('#booking-form').getAttribute('aria-busy') === 'true');
        for (const selector of ['#booking-name','#booking-purpose','#booking-new','#booking-form button[type=submit]','#availability-form button','.booking-select']) {
          assert.equal(await page.locator(selector).first().isDisabled(), true);
        }
        // Creation first: even an explicit submit event cannot start a read until controls restore.
        const queriesBefore = queryRequests;
        await page.locator('#availability-form').evaluate(form => form.requestSubmit());
        assert.equal(queryRequests, queriesBefore);
        assert.equal(await page.locator('#availability-form').getAttribute('aria-busy'), null);
        await page.evaluate(() => window.scrollTo(0, 0));
        await page.screenshot({path:path.join(outputDir,`booking-loading-${viewport.width}.png`),fullPage:true});
        release();
        await page.waitForFunction(() => document.querySelector('#booking-feedback').textContent.includes('预约成功'));
        await page.unroute('**/api/bookings');
        assert.match(await page.locator('#booking-feedback').textContent(), /编号.*12:00.*13:00/);
        assert.ok((await page.locator('#booking-feedback').textContent()).includes(title));
        assert.equal(await page.locator('#booking-feedback img, #booking-feedback script').count(), 0);
        assert.equal(await page.evaluate(() => window.bookingXss), undefined);
        assert.equal(await page.locator('#booking-form button[type=submit]').isDisabled(), false);
        assert.equal(bookingRequests, 1);
        const repeatResponse=page.waitForResponse(response=>response.url().endsWith('/api/bookings'));
        await page.locator('#booking-form button[type=submit]').click();
        assert.equal((await repeatResponse).status(),200);
        await page.waitForFunction(()=>document.querySelector('#booking-feedback').textContent.includes('已确认原预约'));
        assert.equal(bookingRequests,2);
        for (const selector of ['#start','#end','#attendees','#availability-form button']) {
          assert.equal(await page.locator(selector).isDisabled(), false);
        }
        const width = await page.evaluate(() => ({document:document.documentElement.scrollWidth,viewport:innerWidth}));
        assert.ok(width.document <= width.viewport);
        await page.evaluate(() => window.scrollTo(0, 0));
        await page.screenshot({path:path.join(outputDir,`booking-success-${viewport.width}.png`),fullPage:true});
        await competing.locator('#booking-name').fill('冲突输入保留');
        await competing.locator('#booking-purpose').fill('用途保留 🧪');
        await competing.locator('#booking-form button[type=submit]').click();
        await competing.waitForFunction(() => document.querySelector('#booking-feedback').textContent.includes('已被占用'));
        assert.equal(await competing.locator('#booking-name').inputValue(), '冲突输入保留');
        assert.equal(await competing.locator('#booking-purpose').inputValue(), '用途保留 🧪');
        assert.equal(await competing.locator('#booking-form button[type=submit]').isDisabled(), false);
        assert.ok((await competing.locator('#booking-conditions').textContent()).includes(`${date} 12:00`));
        await competing.evaluate(() => window.scrollTo(0, 0));
        await competing.screenshot({path:path.join(outputDir,`booking-conflict-${viewport.width}.png`),fullPage:true});
        // A separate legal POST commits on the server, then loses only its response.
        await competing.locator('#start').fill(`${date}T14:00`);
        await competing.locator('#end').fill(`${date}T15:00`);
        await submitAvailability(competing);
        await competing.waitForFunction(() => document.querySelector('#availability-feedback').textContent.includes('找到 3 间'));
        await competing.locator('.booking-select').last().click();
        assert.equal(await competing.locator('#booking-feedback').getAttribute('role'), 'status');
        assert.equal(await competing.locator('#booking-feedback').evaluate(node => node.classList.contains('error')), false);
        const lostTitle = `响应丢失的合成活动 ${viewport.width}`;
        await competing.locator('#booking-name').fill(lostTitle);
        await competing.locator('#booking-purpose').fill('成功提交但响应丢失，保留输入 🧪');
        let attempted = 0, committed;
        const network=[];
        const networkFile=path.join(outputDir,`replay-network-${viewport.width}.jsonl`);
        fs.writeFileSync(networkFile,'');
        await competing.route('**/api/bookings', async route => {
          attempted++;
          const response = await route.fetch();
          const observed = {status:response.status(), body:await response.json()};
          const request=route.request().postDataJSON();
          const {intent_key,...fields}=request;
          network.push({phase:attempted===1?'committed_response_lost':attempted===2?'same_intent_retry':'edited_new_intent',
            method:'POST',path:'/api/bookings',request:{...fields,intent_key_sha256:createHash('sha256').update(intent_key).digest('hex')},
            delivery:attempted===1?'aborted_after_server_commit':'fulfilled',...observed});
          fs.appendFileSync(networkFile,JSON.stringify(network.at(-1))+'\n');
          if(attempted===1) {committed=observed;await route.abort();}
          else await route.fulfill({response});
        });
        await competing.locator('#booking-form button[type=submit]').click();
        await competing.waitForFunction(() => document.querySelector('#booking-feedback').textContent.includes('未能确认'));
        assert.equal(committed.status, 201);
        assert.equal(committed.body.ok, true);
        assert.equal(attempted, 1);
        assert.equal(await competing.locator('#booking-form button[type=submit]').isDisabled(), false);
        assert.equal(await competing.locator('#booking-name').inputValue(), lostTitle);
        assert.equal(await competing.locator('#booking-purpose').inputValue(), '成功提交但响应丢失，保留输入 🧪');
        for (const selector of ['#start','#end','#attendees','#availability-form button']) {
          assert.equal(await competing.locator(selector).isDisabled(), false);
        }
        const committedBooking = committed.body.data.booking;
        const lostResponse = {http_status:committed.status, request_count:attempted, booking_id:committedBooking.id,
          room_id:committedBooking.room.id, start_at:committedBooking.start_at, end_at:committedBooking.end_at, title:lostTitle};
        await competing.evaluate(() => window.scrollTo(0, 0));
        await competing.screenshot({path:path.join(outputDir,`booking-committed-response-lost-${viewport.width}.png`),fullPage:true});
        // Python-equivalent whitespace preserves the key even after the committed response was lost.
        await competing.locator('#booking-name').fill(`\u0085\u001c ${lostTitle} \u001f`);
        await competing.locator('#booking-form button[type=submit]').click();
        await competing.waitForFunction(()=>document.querySelector('#booking-feedback').textContent.includes('已确认原预约'));
        assert.equal(attempted,2);
        assert.equal(network[1].status,200);
        assert.equal(network[1].body.data.replayed,true);
        assert.equal(network[1].body.data.booking.id,committedBooking.id);
        assert.equal(network[0].request.intent_key_sha256,network[1].request.intent_key_sha256);
        const fullKeys=['id','room','title','purpose','attendees','owner_id','owner_display_name','start_at','start_local',
          'end_at','end_local','status','created_at','created_local','cancelled_at','cancelled_local',
          'cancelled_by_id','cancelled_by_display_name','cancel_reason'].sort();
        assert.deepEqual(Object.keys(network[1].body.data.booking).sort(),fullKeys);
        assert.deepEqual(Object.keys(network[1].body.data.booking.room).sort(),['id','name','location','capacity'].sort());
        await competing.evaluate(() => window.scrollTo(0, 0));
        await competing.screenshot({path:path.join(outputDir,`booking-replayed-${viewport.width}.png`),fullPage:true});
        // A material edit and explicit new room selection produce a new intent and a new record.
        await competing.locator('#booking-purpose').fill('实质编辑后的新预约用途');
        assert.match(await competing.locator('#booking-feedback').textContent(),/新预约意图/);
        await competing.locator('#start').fill(`${date}T16:00`);
        await competing.locator('#end').fill(`${date}T17:00`);
        await submitAvailability(competing);
        await competing.waitForFunction(()=>document.querySelector('#availability-feedback').textContent.includes('找到 3 间'));
        await competing.locator('.booking-select').last().click();
        await competing.locator('#booking-form button[type=submit]').click();
        await competing.waitForFunction(()=>document.querySelector('#booking-feedback').textContent.includes('预约成功'));
        assert.equal(attempted,3);assert.equal(network[2].status,201);
        assert.equal(network[2].body.data.replayed,false);
        assert.notEqual(network[2].body.data.booking.id,committedBooking.id);
        assert.notEqual(network[2].request.intent_key_sha256,network[0].request.intent_key_sha256);
        const editedBooking=network[2].body.data.booking;
        const replayEvidence={original_id:committedBooking.id,replayed_id:network[1].body.data.booking.id,
          new_id:editedBooking.id,key_retained:true,edited_key_changed:true,
          request_hashes:network.map(row=>row.request.intent_key_sha256),
          statuses:network.map(row=>row.status),new_booking:editedBooking,network_file:path.basename(networkFile)};
        const replayWidth=await competing.evaluate(()=>({document:document.documentElement.scrollWidth,viewport:innerWidth}));
        assert.ok(replayWidth.document<=replayWidth.viewport);
        await competing.evaluate(() => window.scrollTo(0, 0));
        await competing.screenshot({path:path.join(outputDir,`booking-new-intent-${viewport.width}.png`),fullPage:true});
        await competing.locator('#booking-new').click();
        assert.equal(await competing.locator('#booking-panel').isVisible(),false);
        assert.equal(await competing.locator('#booking-name').inputValue(),'');
        assert.equal(await competing.evaluate(()=>document.activeElement.id),'start');
        // This first request is aborted before route.fetch/continue: it never reaches Waitress.
        await competing.unroute('**/api/bookings');
        await competing.locator('#start').fill(`${date}T18:00`);
        await competing.locator('#end').fill(`${date}T19:00`);
        await submitAvailability(competing);
        await competing.waitForFunction(()=>document.querySelector('#availability-feedback').textContent.includes('找到 3 间'));
        await competing.locator('.booking-select').last().click();
        const notSentTitle=`首次请求未送达 ${viewport.width}`;
        await competing.locator('#booking-name').fill(notSentTitle);
        await competing.locator('#booking-purpose').fill('仅在主动原键重试时到达服务端');
        const notSentNetwork=[];
        const notSentFile=path.join(outputDir,`not-delivered-network-${viewport.width}.jsonl`);
        fs.writeFileSync(notSentFile,'');
        await competing.route('**/api/bookings', async route=>{
          const {intent_key,...fields}=route.request().postDataJSON();
          const first=notSentNetwork.length===0;
          let observed={status:null,body:null}, response;
          if(!first) {response=await route.fetch();observed={status:response.status(),body:await response.json()};}
          notSentNetwork.push({phase:first?'request_not_delivered':'explicit_same_key_retry',method:'POST',path:'/api/bookings',
            request:{...fields,intent_key_sha256:createHash('sha256').update(intent_key).digest('hex')},
            delivery:first?'aborted_before_server':'fulfilled',...observed});
          fs.appendFileSync(notSentFile,JSON.stringify(notSentNetwork.at(-1))+'\n');
          if(first) await route.abort();else await route.fulfill({response});
        });
        await competing.locator('#booking-form button[type=submit]').click();
        await competing.waitForFunction(()=>document.querySelector('#booking-feedback').textContent.includes('未能确认'));
        assert.equal(notSentNetwork.length,1);
        const beforeRetry=await context.request.get(`${origin}/api/schedule?room_id=30&date=${date}`);
        assert.equal(beforeRetry.status(),200);
        const preRetryMatches=(await beforeRetry.json()).data.items.filter(item=>item.kind==='booking'&&item.record.title===notSentTitle);
        assert.equal(preRetryMatches.length,0);
        assert.equal(await competing.locator('#booking-form button[type=submit]').textContent(),'重试确认原预约');
        await competing.locator('#booking-form button[type=submit]').click();
        await competing.waitForFunction(()=>document.querySelector('#booking-feedback').textContent.includes('预约成功'));
        assert.equal(notSentNetwork.length,2);
        assert.equal(notSentNetwork[1].status,201);
        assert.equal(notSentNetwork[1].body.data.replayed,false);
        assert.equal(notSentNetwork[0].request.intent_key_sha256,notSentNetwork[1].request.intent_key_sha256);
        const notSentBooking=notSentNetwork[1].body.data.booking;
        const notDeliveredEvidence={booking_id:notSentBooking.id,room_id:notSentBooking.room.id,title:notSentTitle,
          start_at:notSentBooking.start_at,end_at:notSentBooking.end_at,key_retained:true,pre_retry_matching_records:0,
          statuses:notSentNetwork.map(row=>row.status),request_hashes:notSentNetwork.map(row=>row.request.intent_key_sha256),
          network_file:path.basename(notSentFile)};
        await competing.evaluate(()=>window.scrollTo(0,0));
        await competing.screenshot({path:path.join(outputDir,`booking-not-delivered-retry-${viewport.width}.png`),fullPage:true});
        await competing.close();
        // Newly created plain text is visible in shared schedule, without purpose.
        await page.locator('#room_id').selectOption('30');
        await page.locator('#date').fill(date);
        await submitSchedule(page);
        await page.waitForFunction(() => document.querySelector('#schedule-feedback').textContent.includes('共 4 项'));
        assert.ok((await page.locator('#schedule-items').textContent()).includes(title));
        assert.equal(await page.locator('#schedule-items img, #schedule-items script').count(), 0);
        assert.equal(await page.evaluate(() => window.bookingXss), undefined);
        bookingChecks = {width,query_first_blocks_creation:'PASS',creation_first_blocks_query:'PASS',neutral_room_selection_feedback:'PASS',room_selection_accessible_names:'PASS',committed_response_lost:lostResponse,explicit_new_booking:'PASS',created:'PASS',conflict_retains_inputs:'PASS',loading_disables_controls:'PASS',literal_unicode_xss:'PASS',explicit_retry_same_intent:replayEvidence,not_delivered_retry:notDeliveredEvidence,schedule_updated:'PASS'};
      }
      // Start from the stable header link, then traverse to logout by keyboard.
      await page.locator('.brand').focus();
      await page.keyboard.press('Tab');
      assert.equal(await page.evaluate(() => document.activeElement.textContent), '退出登录');
      await page.keyboard.press('Enter');
      await page.waitForURL(`${origin}/login?logged_out=1`);
      assert.ok((await page.locator('.notice').textContent()).includes('已退出登录'));
      assert.equal((await context.request.get(`${origin}/api/me`)).status(), 401);
      const replay = await context.request.get(`${origin}/api/me`, {headers:{Cookie:`grb_session=${oldCookie.value}`}});
      assert.equal(replay.status(), 401);
      if (scenario === 'schedule' || scenario === 'availability' || scenario === 'booking') {
        assert.equal((await context.request.get(`${origin}/api/rooms`)).status(), 401);
        assert.equal((await context.request.get(`${origin}/api/schedule?room_id=10&date=2026-11-12`, {headers:{Cookie:`grb_session=${oldCookie.value}`}})).status(), 401);
        scheduleChecks.logout_rejects_queries = 'PASS';
        await stalePage.locator('#room_id').selectOption('10');
        await stalePage.locator('#date').fill('2026-11-12');
        await submitSchedule(stalePage);
        await stalePage.waitForFunction(() => document.querySelector('#schedule-feedback').textContent.includes('登录已失效'));
        assert.equal(await stalePage.locator('#schedule-relogin').isVisible(), true);
        assert.equal(await stalePage.locator('#date').inputValue(), '2026-11-12');
        scheduleChecks.session_loss_feedback = 'PASS';
        if (scenario === 'availability' || scenario === 'booking') {
          assert.equal((await context.request.get(`${origin}/api/availability?start=bad&end=bad&attendees=bad`, {headers:{Cookie:`grb_session=${oldCookie.value}`}})).status(), 401);
          await stalePage.locator('#start').fill('2026-11-12T12:00');
          await stalePage.locator('#end').fill('2026-11-12T12:30');
          await stalePage.locator('#attendees').fill('10');
          await submitAvailability(stalePage);
          await stalePage.waitForFunction(() => document.querySelector('#availability-feedback').textContent.includes('登录已失效'));
          assert.equal(await stalePage.locator('#availability-relogin').isVisible(), true);
          assert.equal(await stalePage.locator('#start').inputValue(), '2026-11-12T12:00');
          assert.equal(await stalePage.locator('#attendees').inputValue(), '10');
          availabilityChecks.session_loss_and_old_cookie = 'PASS';
        }
        await stalePage.close();
      }
      await page.locator('button[type=submit]').focus();
      await page.keyboard.press('Enter');
      await page.waitForFunction(() => document.querySelector('#username').getAttribute('aria-invalid') === 'true');
      assert.equal(await page.evaluate(() => document.activeElement.id), 'username');
      assert.ok((await page.locator('#auth-feedback').textContent()).includes('检查账号和密码'));
      assert.equal(await page.locator('#auth-feedback').getAttribute('role'), 'alert');
      assert.deepEqual(errors, []);
      results.push({viewport,loginWidth,homeWidth,...(bookingChecks ? {booking:bookingChecks} : {}),keyboard_login:'PASS',keyboard_logout:'PASS',identity_api:'PASS',logout_and_old_cookie:'PASS',empty_fields_feedback:'PASS',visible_labels:'PASS',page_errors:errors,...(scheduleChecks ? {schedule:scheduleChecks} : {}),...(availabilityChecks ? {availability:availabilityChecks} : {})});
      await context.close();
    }
    console.log(JSON.stringify({result:'PASS',browser:await browser.version(),runner:`Playwright ${PINNED_PLAYWRIGHT} (external verification tool only)`,results},null,2));
  } finally {
    await browser.close();
  }
})().catch(error => {
  const source = String(error.stack).match(/verify_auth_browser\.cjs:[0-9]+:[0-9]+/);
  // Persist only the error type and source line, never input values or raw diagnostics.
  fs.writeFileSync(path.join(process.argv[4], 'browser-failure.json'), JSON.stringify({error_type:error.name, source:source ? source[0] : null}, null, 2));
  console.error(error.name);
  process.exitCode = 1;
});
