// Execute the real registered submit handler with controllable time and I/O.
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

function harness(initialFetch) {
  let activeElement, submitHandler, fetchImplementation = initialFetch;
  let fetches = [], timerId = 0;
  const timers = new Map();
  function node(id = '') {
    const attributes = new Map();
    return {
      id, attributes, children: [], disabled: false, hidden: false, value: '', _text: '',
      get textContent() { return this._text + this.children.map(child => child.textContent).join(''); },
      set textContent(value) { this._text = value; this.children = []; },
      classList: { toggle() {} },
      setAttribute(key, value) { attributes.set(key, value); },
      removeAttribute(key) { attributes.delete(key); },
      getAttribute(key) { return attributes.get(key); },
      append(child) { this.children.push(child); },
      replaceChildren() { this.children = []; },
      focus() { if (!this.disabled) activeElement = this; },
    };
  }
  const room = node('room_id'), date = node('date'), button = node('submit');
  room.value = '10'; room.selectedOptions = [{textContent: '合成会议室'}];
  date.value = '2026-11-12'; button.textContent = '查看日程'; button.disabled = true;
  const elements = {room_id: room, date, namedItem(name) { return this[name]; }};
  const form = node('schedule-form');
  form.elements = elements;
  form.querySelector = selector => selector === 'button[type=submit]' ? button : [room, date].find(input => input.getAttribute('aria-invalid') === 'true');
  form.addEventListener = (event, callback) => { assert.equal(event, 'submit'); submitHandler = callback; };
  const nodes = Object.fromEntries(['schedule-feedback', 'schedule-results', 'schedule-items', 'schedule-conditions', 'schedule-relogin', 'room_id-error', 'date-error'].map(id => [id, node(id)]));
  const context = vm.createContext({
    AbortController, URLSearchParams,
    document: {
      querySelector: selector => selector === '#schedule-form' ? form : nodes[selector.slice(1)],
      getElementById: id => nodes[id], createElement: () => node(),
    },
    window: {
      setTimeout(callback, ms) { const id = ++timerId; timers.set(id, {callback, ms}); return id; },
      clearTimeout(id) { assert.equal(timers.delete(id), true); },
    },
    fetch: (url, options) => { fetches.push({url, options}); return fetchImplementation(url, options); },
  });
  vm.runInContext(fs.readFileSync(path.join(__dirname, '../booking_app/static/schedule.js'), 'utf8'), context);
  assert.equal(typeof submitHandler, 'function');
  return {
    room, date, button, form, nodes, timers, fetches,
    get activeElement() { return activeElement; },
    setFetch(value) { fetchImplementation = value; },
    submit() { let prevented = false; const pending = submitHandler({preventDefault() { prevented = true; }}); assert.equal(prevented, true); return pending; },
    userEdit(input, value) { if (!input.disabled) input.value = value; },
  };
}

function success(items = []) { return {ok: true, json: async () => ({ok: true, data: {items, total: items.length}})}; }
function assertPending(ui) {
  assert.equal(ui.button.disabled, true);
  assert.equal(ui.room.disabled, true);
  assert.equal(ui.date.disabled, true);
  assert.equal(ui.form.getAttribute('aria-busy'), 'true');
  assert.match(ui.nodes['schedule-feedback'].textContent, /正在查询/);
}
function assertRestored(ui) {
  assert.equal(ui.button.disabled, false);
  assert.equal(ui.button.textContent, '查看日程');
  assert.equal(ui.room.disabled, false);
  assert.equal(ui.date.disabled, false);
  assert.equal(ui.form.getAttribute('aria-busy'), undefined);
  assert.equal(ui.timers.size, 0);
  assert.equal(ui.room.value, '10');
  assert.equal(ui.date.value, '2026-11-12');
}
async function retrySuccessfully(ui) {
  ui.setFetch(async () => success());
  await ui.submit();
  assertRestored(ui);
  assert.equal(ui.fetches.length, 2);
  assert.match(ui.nodes['schedule-feedback'].textContent, /当天暂无/);
  assert.equal(ui.nodes['schedule-results'].hidden, false);
}

for (const stage of ['response headers', 'response body']) {
  test(`schedule stalled ${stage} aborts at 20 seconds and can be queried again`, async () => {
    let signal;
    const ui = harness(async (_url, options) => {
      signal = options.signal;
      const stalled = () => new Promise((_resolve, reject) => signal.addEventListener('abort', () => reject(new Error('aborted')), {once: true}));
      return stage === 'response headers' ? stalled() : {ok: true, json: stalled};
    });
    const pending = ui.submit();
    await new Promise(setImmediate);
    assertPending(ui);
    const timer = [...ui.timers.values()][0];
    assert.equal(timer.ms, 20000);
    timer.callback();
    await pending;
    assert.equal(signal.aborted, true);
    assertRestored(ui);
    assert.equal(ui.fetches.length, 1, 'No automatic retry.');
    assert.match(ui.nodes['schedule-feedback'].textContent, /未能查询日程.*查询条件已保留/);
    assert.equal(ui.nodes['schedule-feedback'].getAttribute('role'), 'alert');
    await retrySuccessfully(ui);
  });
}

for (const failure of ['network failure', 'bad JSON']) {
  test(`schedule ${failure} preserves conditions, restores controls, and permits retry`, async () => {
    const ui = harness(async () => {
      if (failure === 'network failure') throw new TypeError('offline');
      return {ok: true, json: async () => { throw new SyntaxError('invalid JSON'); }};
    });
    await ui.submit();
    assertRestored(ui);
    assert.equal(ui.fetches.length, 1);
    assert.match(ui.nodes['schedule-feedback'].textContent, /查询条件已保留/);
    assert.equal(ui.nodes['schedule-results'].hidden, true);
    await retrySuccessfully(ui);
  });
}

test('pending conditions cannot be edited and a field error focuses the restored original input', async () => {
  let resolveResponse;
  const ui = harness(() => new Promise(resolve => { resolveResponse = resolve; }));
  const pending = ui.submit();
  assertPending(ui);
  ui.userEdit(ui.room, '30');
  ui.userEdit(ui.date, '2026-11-13');
  await ui.submit();
  assert.equal(ui.fetches.length, 1, 'An in-flight submit cannot start a second query.');
  assert.equal(ui.room.value, '10');
  assert.equal(ui.date.value, '2026-11-12');
  assert.equal(ui.fetches[0].url, '/api/schedule?room_id=10&date=2026-11-12');
  resolveResponse({ok: false, json: async () => ({ok: false, error: {code: 'INVALID_INPUT', message: '请检查查询日期。', fields: {date: '原查询日期错误'}}})});
  await pending;
  assertRestored(ui);
  assert.equal(ui.date.getAttribute('aria-invalid'), 'true');
  assert.equal(ui.nodes['date-error'].textContent, '原查询日期错误');
  assert.equal(ui.activeElement, ui.date, 'Error focus occurs only after the input is enabled again.');
  ui.userEdit(ui.room, '30');
  ui.userEdit(ui.date, '2026-11-13');
  ui.setFetch(async () => success());
  await ui.submit();
  assert.equal(ui.fetches[1].url, '/api/schedule?room_id=30&date=2026-11-13');
  assert.equal(ui.date.getAttribute('aria-invalid'), undefined);
  assert.equal(ui.nodes['date-error'].textContent, '');
  assert.match(ui.nodes['schedule-conditions'].textContent, /2026-11-13/);
  assert.equal(ui.room.disabled, false);
  assert.equal(ui.date.disabled, false);
  assert.equal(ui.button.disabled, false);
  assert.equal(ui.form.getAttribute('aria-busy'), undefined);
});
