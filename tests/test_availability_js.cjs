const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

function harness(initialFetch, selectBookingRoom) {
  let activeElement, submitHandler, fetchImplementation = initialFetch, timerId = 0;
  const timers = new Map(), fetches = [];
  function node(id = '') {
    const attributes = new Map();
    return {
      id, children: [], disabled: false, hidden: false, value: '', _text: '',
      get textContent() { return this._text + this.children.map(child => child.textContent).join(''); },
      set textContent(value) { this._text = value; this.children = []; },
      classList: { toggle() {} },
      setAttribute(key, value) { attributes.set(key, value); },
      removeAttribute(key) { attributes.delete(key); },
      getAttribute(key) { return attributes.get(key); },
      append(child) { this.children.push(child); },
      replaceChildren() { this.children = []; },
      focus() { if (!this.disabled) activeElement = this; },
      addEventListener(event, handler) { this[event] = handler; },
    };
  }
  const inputs = Object.fromEntries(['start', 'end', 'attendees'].map(name => [name, node(name)]));
  inputs.start.value = '2026-11-12T12:00'; inputs.end.value = '2026-11-12T12:30'; inputs.attendees.value = '10';
  const button = node('submit'); button.textContent = '查询可用会议室'; button.disabled = true;
  const form = node('availability-form'); form.elements = inputs;
  form.querySelector = selector => selector === 'button[type=submit]' ? button : Object.values(inputs).find(input => input.getAttribute('aria-invalid') === 'true');
  form.addEventListener = (event, callback) => { assert.equal(event, 'submit'); submitHandler = callback; };
  const nodes = Object.fromEntries(['availability-feedback', 'availability-results', 'availability-items', 'availability-conditions', 'availability-relogin', 'start-error', 'end-error', 'attendees-error'].map(id => [id, node(id)]));
  vm.runInNewContext(fs.readFileSync(path.join(__dirname, '../booking_app/static/availability.js'), 'utf8'), {
    AbortController, URLSearchParams,
    document: {
      querySelector: selector => selector === '#availability-form' ? form : nodes[selector.slice(1)],
      getElementById: id => nodes[id], createElement: () => node(),
    },
    window: {
      selectBookingRoom,
      setTimeout(callback, ms) { const id = ++timerId; timers.set(id, {callback, ms}); return id; },
      clearTimeout(id) { assert.equal(timers.delete(id), true); },
    },
    fetch: (url, options) => { fetches.push({url, options}); return fetchImplementation(url, options); },
  });
  return {
    inputs, button, form, nodes, timers, fetches,
    get activeElement() { return activeElement; },
    setFetch(value) { fetchImplementation = value; },
    submit() { let prevented = false; const pending = submitHandler({preventDefault() { prevented = true; }}); assert.equal(prevented, true); return pending; },
  };
}

function success(items = []) { return {ok: true, json: async () => ({ok: true, data: {items, total: items.length}})}; }
function assertPending(ui) {
  assert.equal(ui.button.disabled, true);
  for (const input of Object.values(ui.inputs)) assert.equal(input.disabled, true);
  assert.equal(ui.form.getAttribute('aria-busy'), 'true');
  assert.match(ui.nodes['availability-feedback'].textContent, /正在查询/);
}
function assertRestored(ui) {
  assert.equal(ui.button.disabled, false);
  assert.equal(ui.button.textContent, '查询可用会议室');
  for (const input of Object.values(ui.inputs)) assert.equal(input.disabled, false);
  assert.equal(ui.form.getAttribute('aria-busy'), undefined);
  assert.equal(ui.timers.size, 0);
  assert.equal(ui.inputs.start.value, '2026-11-12T12:00');
  assert.equal(ui.inputs.end.value, '2026-11-12T12:30');
  assert.equal(ui.inputs.attendees.value, '10');
}

for (const stage of ['response headers', 'response body']) {
  test(`availability stalled ${stage} aborts at 20 seconds, retains input, permits manual retry`, async () => {
    let signal;
    const ui = harness(async (_url, options) => {
      signal = options.signal;
      const stalled = () => new Promise((_resolve, reject) => signal.addEventListener('abort', () => reject(new Error('aborted')), {once: true}));
      return stage === 'response headers' ? stalled() : {ok: true, json: stalled};
    });
    const pending = ui.submit();
    await new Promise(setImmediate);
    assertPending(ui);
    await ui.submit();
    assert.equal(ui.fetches.length, 1);
    const timer = [...ui.timers.values()][0];
    assert.equal(timer.ms, 20000);
    timer.callback();
    await pending;
    assert.equal(signal.aborted, true);
    assertRestored(ui);
    assert.match(ui.nodes['availability-feedback'].textContent, /查询超时.*查询条件已保留/);
    assert.equal(ui.nodes['availability-feedback'].getAttribute('role'), 'alert');
    assert.equal(ui.activeElement, ui.nodes['availability-feedback']);
    assert.equal(ui.fetches.length, 1, 'Never retry automatically.');
    ui.setFetch(async () => success());
    await ui.submit();
    assertRestored(ui);
    assert.equal(ui.fetches.length, 2);
    assert.match(ui.nodes['availability-feedback'].textContent, /没有符合条件/);
    assert.equal(ui.nodes['availability-results'].hidden, false);
    assert.equal(ui.activeElement, ui.button, 'Empty success restores the query button focus.');
  });
}

for (const failure of ['network failure', 'bad JSON']) {
  test(`availability ${failure} restores controls without discarding conditions`, async () => {
    const ui = harness(async () => {
      if (failure === 'network failure') throw new TypeError('offline');
      return {ok: true, json: async () => { throw new SyntaxError('invalid JSON'); }};
    });
    await ui.submit();
    assertRestored(ui);
    assert.equal(ui.nodes['availability-results'].hidden, true);
    assert.match(ui.nodes['availability-feedback'].textContent, /查询条件已保留/);
    assert.equal(ui.activeElement, ui.nodes['availability-feedback']);
  });
}

test('availability field errors focus enabled input; success clears errors and safely renders literal room text', async () => {
  const ui = harness(async () => ({ok: false, json: async () => ({ok: false, error: {code: 'INVALID_INPUT', message: '请检查人数。', fields: {attendees: '须为正整数'}}})}));
  await ui.submit();
  assertRestored(ui);
  assert.equal(ui.inputs.attendees.getAttribute('aria-invalid'), 'true');
  assert.equal(ui.activeElement, ui.inputs.attendees);
  assert.equal(ui.nodes['attendees-error'].textContent, '须为正整数');
  ui.setFetch(async () => success([{id: 1, name: '<img src=x onerror=evil()>', location: '<script>evil()</script>', capacity: 10}]));
  await ui.submit();
  assertRestored(ui);
  assert.equal(ui.inputs.attendees.getAttribute('aria-invalid'), undefined);
  assert.equal(ui.activeElement, ui.button, 'Success restores the query button focus.');
  assert.equal(ui.nodes['attendees-error'].textContent, '');
  assert.equal(ui.nodes['availability-items'].children.length, 1);
  assert.match(ui.nodes['availability-items'].textContent, /<img src=x onerror=evil\(\)>/);
  assert.match(ui.nodes['availability-conditions'].textContent, /2026-11-12 12:00.*12:30.*北京时间.*10 人/);
  assert.match(ui.nodes['availability-feedback'].textContent, /不保留时段/);
  assert.equal(ui.fetches[0].url, '/api/availability?start=2026-11-12T12%3A00&end=2026-11-12T12%3A30&attendees=10');
});

test('availability expired session gives a login link, preserves input and hides old results', async () => {
  const ui = harness(async () => success([{id: 1, name: '合成房间', location: '合成楼', capacity: 10}]));
  await ui.submit();
  ui.setFetch(async () => ({ok: false, json: async () => ({ok: false, error: {code: 'AUTH_REQUIRED', message: '登录已失效，请重新登录。', fields: {}}})}));
  await ui.submit();
  assertRestored(ui);
  assert.equal(ui.nodes['availability-results'].hidden, true);
  assert.equal(ui.nodes['availability-items'].children.length, 0);
  assert.equal(ui.nodes['availability-relogin'].hidden, false);
  assert.equal(ui.activeElement, ui.nodes['availability-feedback']);
  assert.equal(ui.fetches.length, 2);
});


test('each room selection has a distinct accessible name containing room and location', async () => {
  const rooms=[{id:1,name:'合成 A',location:'101',capacity:10},{id:2,name:'合成 A',location:'202',capacity:20}];
  const selected=[];
  const ui=harness(async()=>success(rooms),(room,query)=>selected.push({room,query}));
  await ui.submit();
  const buttons=ui.nodes['availability-items'].children.map(row=>row.children.at(-1));
  assert.deepEqual(buttons.map(button=>button.getAttribute('aria-label')),
    ['选择 合成 A（101）并填写活动','选择 合成 A（202）并填写活动']);
  buttons[1].click();assert.equal(selected[0].room.id,2);
  assert.equal(selected[0].query.start,'2026-11-12T12:00');
});
