// Invoked by the Python launcher; credentials are temporary, private, and never logged.
const { chromium } = require('playwright');
const fs = require('node:fs');
const path = require('node:path');
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
      if (scenario === 'schedule' || scenario === 'availability') {
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
      if (scenario === 'availability') {
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
        assert.equal(await page.evaluate(() => document.activeElement.id), 'room_id');
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
      if (scenario === 'schedule' || scenario === 'availability') {
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
        if (scenario === 'availability') {
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
      results.push({viewport,loginWidth,homeWidth,keyboard_login:'PASS',keyboard_logout:'PASS',identity_api:'PASS',logout_and_old_cookie:'PASS',empty_fields_feedback:'PASS',visible_labels:'PASS',page_errors:errors,...(scheduleChecks ? {schedule:scheduleChecks} : {}),...(availabilityChecks ? {availability:availabilityChecks} : {})});
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
