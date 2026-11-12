// Invoked by the Python launcher; credentials are temporary, private, and never logged.
const { chromium } = require('playwright');
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const PINNED_PLAYWRIGHT = '1.58.2';

(async () => {
  assert.equal(require('playwright/package.json').version, PINNED_PLAYWRIGHT);
  const [origin, credentialsFile, outputDir, executablePath] = process.argv.slice(2);
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
      assert.ok((await page.locator('h1').textContent()).includes(users[0].display_name));
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
      await page.keyboard.press('Tab');
      await page.keyboard.press('Tab');
      await page.keyboard.press('Tab');
      assert.equal(await page.evaluate(() => document.activeElement.textContent), '退出登录');
      await page.keyboard.press('Enter');
      await page.waitForURL(`${origin}/login?logged_out=1`);
      assert.ok((await page.locator('.notice').textContent()).includes('已退出登录'));
      assert.equal((await context.request.get(`${origin}/api/me`)).status(), 401);
      const replay = await context.request.get(`${origin}/api/me`, {headers:{Cookie:`grb_session=${oldCookie.value}`}});
      assert.equal(replay.status(), 401);
      await page.locator('button[type=submit]').focus();
      await page.keyboard.press('Enter');
      await page.waitForFunction(() => document.querySelector('#username').getAttribute('aria-invalid') === 'true');
      assert.equal(await page.evaluate(() => document.activeElement.id), 'username');
      assert.ok((await page.locator('#auth-feedback').textContent()).includes('检查账号和密码'));
      assert.equal(await page.locator('#auth-feedback').getAttribute('role'), 'alert');
      assert.deepEqual(errors, []);
      results.push({viewport,loginWidth,homeWidth,keyboard_login:'PASS',keyboard_logout:'PASS',identity_api:'PASS',logout_and_old_cookie:'PASS',empty_fields_feedback:'PASS',visible_labels:'PASS',page_errors:errors});
      await context.close();
    }
    console.log(JSON.stringify({result:'PASS',browser:await browser.version(),runner:`Playwright ${PINNED_PLAYWRIGHT} (external verification tool only)`,results},null,2));
  } finally {
    await browser.close();
  }
})().catch(error => { console.error(error.name); process.exitCode = 1; });
