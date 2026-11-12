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
    let submitHandler;
    const form = {
      elements: { csrf_token: { value: 'synthetic-csrf' }, username: {disabled:false,value:'synthetic-user',removeAttribute(){}}, password: {disabled:false,value:'synthetic-password',removeAttribute(){}} },
      querySelector: () => button,
      setAttribute: (key, value) => attributes.set(key, value),
      removeAttribute: (key) => attributes.delete(key),
      addEventListener: (_event,handler) => {submitHandler=handler;},
    };
    const feedback = { textContent: '', classList: { toggle: () => {} }, setAttribute: () => {}, focus: () => {} };
    const relogin = { hidden: true };
    let timeoutCallback, timeoutMs, cleared = false, fetches = 0, signal;
    const context = vm.createContext({
      AbortController,
      document: { querySelector: selector => ({ '#login-form': form, '#logout-form': null, '#auth-feedback': feedback, '#relogin-link': relogin })[selector],getElementById:()=>({textContent:''}) },
      window: {
        setTimeout: (callback, ms) => { timeoutCallback = callback; timeoutMs = ms; return 1; },
        clearTimeout: id => { assert.equal(id, 1); cleared = true; },
        location: { assign: () => assert.fail('Timeout must not navigate or imply success.') },
      },
      fetch: async (_url, options) => {
        fetches++;
        assert.deepEqual(JSON.parse(options.body),{username:'synthetic-user',password:'synthetic-password'});
        signal = options.signal;
        const stalled = () => new Promise((_resolve, reject) => signal.addEventListener('abort', () => reject(new Error('aborted')), { once: true }));
        return stage === 'response headers' ? stalled() : { ok: true, json: stalled };
      },
      form,
    });
    vm.runInContext(fs.readFileSync(path.join(__dirname, '../booking_app/static/auth.js'), 'utf8'), context);
    submitHandler({preventDefault(){}});
    await new Promise(setImmediate);
    assert.equal(timeoutMs, 20000);
    assert.equal(button.disabled, true);
    assert.equal(form.elements.username.disabled, true);
    assert.equal(form.elements.password.disabled, true);
    await vm.runInContext('submitAuth(form, "/api/login", {}, "/")', context);
    assert.equal(fetches, 1);
    assert.equal(attributes.get('aria-busy'), 'true');
    timeoutCallback();
    await new Promise(setImmediate);
    assert.equal(form.elements.username.value,'synthetic-user');
    assert.equal(form.elements.password.value,'synthetic-password');
    assert.equal(signal.aborted, true);
    assert.equal(button.disabled, false);
    assert.equal(form.elements.username.disabled, false);
    assert.equal(form.elements.password.disabled, false);
    assert.equal(button.textContent, '登录');
    assert.equal(attributes.has('aria-busy'), false);
    assert.equal(relogin.hidden, false);
    assert.match(feedback.textContent, /未能确认操作结果/);
    assert.equal(cleared, true);
    assert.equal(fetches, 1, 'Never retry automatically.');
  });
}

for (const failure of ['field', 'network']) {
  test(`login ${failure} failure unlocks credentials before focus and preserves submitted values`, async () => {
    let active, handler, resolve, calls=0;
    function input(value) { const attrs=new Map(); return {value,disabled:false,setAttribute:(k,v)=>attrs.set(k,v),removeAttribute:k=>attrs.delete(k),getAttribute:k=>attrs.get(k),focus(){if(!this.disabled)active=this;}}; }
    const username=input('synthetic-user'),password=input('synthetic-password');
    const button={disabled:false,textContent:'登录'};
    const form={elements:{username,password,csrf_token:{value:'synthetic-csrf'},namedItem(name){return this[name];}},
      querySelector:s=>s==='button[type=submit]'?button:[username,password].find(i=>i.getAttribute('aria-invalid')==='true'),
      setAttribute(){},removeAttribute(){},addEventListener:(_e,h)=>handler=h};
    const feedback={textContent:'',classList:{toggle(){}},setAttribute(){},focus(){active=this;}};
    const hints={'username-error':{textContent:''},'password-error':{textContent:''}};
    const relogin={hidden:true};
    const context=vm.createContext({AbortController,
      document:{querySelector:s=>({'#login-form':form,'#logout-form':null,'#auth-feedback':feedback,'#relogin-link':relogin})[s],getElementById:id=>hints[id]},
      window:{setTimeout:()=>1,clearTimeout(){},location:{assign(){assert.fail('Failure cannot navigate');}}},
      fetch:(_u,o)=>{calls++;assert.deepEqual(JSON.parse(o.body),{username:'synthetic-user',password:'synthetic-password'});return new Promise((yes,no)=>{resolve=failure==='network'?()=>no(new TypeError('offline')):()=>yes({ok:false,json:async()=>({ok:false,error:{code:'INVALID_INPUT',message:'请检查账号',fields:{username:'账号错误'}}})});});}, form});
    vm.runInContext(fs.readFileSync(path.join(__dirname,'../booking_app/static/auth.js'),'utf8'),context);
    handler({preventDefault(){}});
    assert.equal(username.disabled,true); assert.equal(password.disabled,true);
    handler({preventDefault(){}}); assert.equal(calls,1);
    resolve(); await new Promise(setImmediate);
    assert.equal(username.disabled,false); assert.equal(password.disabled,false); assert.equal(button.disabled,false);
    assert.equal(username.value,'synthetic-user'); assert.equal(password.value,'synthetic-password');
    assert.equal(active,failure==='field'?username:feedback);
    if(failure==='field') assert.equal(hints['username-error'].textContent,'账号错误');
    else assert.equal(relogin.hidden,false);
  });
}
