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
      let scheduleChecks, stalePage;
      if (scenario === 'schedule') {
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
        assert.match(await noScriptPage.locator('noscript').textContent(), /查询日程需要启用 JavaScript/);
        assert.equal(await noScriptPage.locator('#schedule-form button').isDisabled(), true);
        await noScriptContext.close();
        scheduleChecks = {scheduleWidth,labels:'PASS',loading:'PASS',pending_inputs_disabled_and_restored:'PASS',field_error:'PASS',keyboard_schedule_submit:'PASS',keyboard_room_and_date_error_focus:'PASS',fixed_clock_status_texts:'PASS',exact_api_intervals:'PASS',exact_display_intervals:'PASS',no_script_notice_and_readable_directory:'PASS',shared_contract:'PASS',literal_html_and_xss:'PASS',private_values_absent:'PASS',half_open_midnight:'PASS',empty_result:'PASS',error_retains_conditions:'PASS'};
        stalePage = await context.newPage();
        await stalePage.goto(`${origin}/`);
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
      if (scenario === 'schedule') {
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
        await stalePage.close();
      }
      await page.locator('button[type=submit]').focus();
      await page.keyboard.press('Enter');
      await page.waitForFunction(() => document.querySelector('#username').getAttribute('aria-invalid') === 'true');
      assert.equal(await page.evaluate(() => document.activeElement.id), 'username');
      assert.ok((await page.locator('#auth-feedback').textContent()).includes('检查账号和密码'));
      assert.equal(await page.locator('#auth-feedback').getAttribute('role'), 'alert');
      assert.deepEqual(errors, []);
      results.push({viewport,loginWidth,homeWidth,keyboard_login:'PASS',keyboard_logout:'PASS',identity_api:'PASS',logout_and_old_cookie:'PASS',empty_fields_feedback:'PASS',visible_labels:'PASS',page_errors:errors,...(scheduleChecks ? {schedule:scheduleChecks} : {})});
      await context.close();
    }
    console.log(JSON.stringify({result:'PASS',browser:await browser.version(),runner:`Playwright ${PINNED_PLAYWRIGHT} (external verification tool only)`,results},null,2));
  } finally {
    await browser.close();
  }
})().catch(error => { console.error(error.name); process.exitCode = 1; });
