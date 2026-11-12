// Focused timeout checks without browser dependencies or a 20-second wall-clock wait.
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

for (const stage of ['response headers', 'response body']) {
  test(`stalled ${stage} aborts at 20 seconds and restores manual controls`, async () => {
    const button = { disabled: false, textContent: '登录' };
    const attributes = new Map();
    const form = {
      elements: { csrf_token: { value: 'synthetic-csrf' } },
      querySelector: () => button,
      setAttribute: (key, value) => attributes.set(key, value),
      removeAttribute: (key) => attributes.delete(key),
      addEventListener: () => {},
    };
    const feedback = { textContent: '', classList: { toggle: () => {} }, setAttribute: () => {}, focus: () => {} };
    const relogin = { hidden: true };
    let timeoutCallback, timeoutMs, cleared = false, fetches = 0, signal;
    const context = vm.createContext({
      AbortController,
      document: { querySelector: selector => ({ '#login-form': form, '#logout-form': null, '#auth-feedback': feedback, '#relogin-link': relogin })[selector] },
      window: {
        setTimeout: (callback, ms) => { timeoutCallback = callback; timeoutMs = ms; return 1; },
        clearTimeout: id => { assert.equal(id, 1); cleared = true; },
        location: { assign: () => assert.fail('Timeout must not navigate or imply success.') },
      },
      fetch: async (_url, options) => {
        fetches++;
        signal = options.signal;
        const stalled = () => new Promise((_resolve, reject) => signal.addEventListener('abort', () => reject(new Error('aborted')), { once: true }));
        return stage === 'response headers' ? stalled() : { ok: true, json: stalled };
      },
      form,
    });
    vm.runInContext(fs.readFileSync(path.join(__dirname, '../booking_app/static/auth.js'), 'utf8'), context);
    const pending = vm.runInContext('submitAuth(form, "/api/login", {}, "/")', context);
    await new Promise(setImmediate);
    assert.equal(timeoutMs, 20000);
    assert.equal(button.disabled, true);
    assert.equal(attributes.get('aria-busy'), 'true');
    timeoutCallback();
    await pending;
    assert.equal(signal.aborted, true);
    assert.equal(button.disabled, false);
    assert.equal(button.textContent, '登录');
    assert.equal(attributes.has('aria-busy'), false);
    assert.equal(relogin.hidden, false);
    assert.match(feedback.textContent, /未能确认操作结果/);
    assert.equal(cleared, true);
    assert.equal(fetches, 1, 'Never retry automatically.');
  });
}
