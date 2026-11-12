const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const {webcrypto} = require('node:crypto');

function harness(initialFetch) {
  let active, implementation=initialFetch, timerId=0;
  const fetches=[],timers=new Map();
  function node(id='') {
    const attrs=new Map(),classes=new Set(),listeners=new Map();
    return {id,value:'',_text:'',children:[],disabled:false,hidden:false,
      get textContent(){return this._text+this.children.map(child=>child.textContent).join('');},
      set textContent(value){this._text=value;this.children=[];},
      classList:{toggle(name,on){on?classes.add(name):classes.delete(name);},contains(name){return classes.has(name);}},
      setAttribute(k,v){attrs.set(k,v);},removeAttribute(k){attrs.delete(k);},getAttribute(k){return attrs.get(k);},
      focus(){if(!this.disabled) active=this;},append(child){this.children.push(child);},replaceChildren(){this.children=[];},
      addEventListener(event,handler){listeners.set(event,handler);},
      dispatch(event){return listeners.get(event)?.({preventDefault(){}});}};
  }
  const form=node('booking-form'),button=node('submit');
  const inputs={title:node('booking-name'),purpose:node('booking-purpose'),csrf_token:node('csrf')};
  inputs.csrf_token.value='synthetic-csrf';inputs.title.value='  中文 🧪 <img>  ';inputs.purpose.value='用途';
  form.elements=inputs;form.querySelector=()=>button;
  const nodes=Object.fromEntries(['booking-panel','booking-feedback','booking-relogin','booking-conditions','booking-title-error','booking-purpose-error',
    'availability-feedback','availability-results','availability-items','availability-conditions','availability-relogin','start-error','end-error','attendees-error'].map(id=>[id,node(id)]));
  const others=[node('start'),node('end'),node('attendees'),node('query'),node('select')];
  const availabilityForm=node('availability-form');
  availabilityForm.elements=Object.fromEntries(['start','end','attendees'].map((name,i)=>[name,others[i]]));
  others[0].value='2026-11-12T12:00';others[1].value='2026-11-12T13:00';others[2].value='5';
  availabilityForm.querySelector=selector=>selector==='button[type=submit]'?others[3]:others.find(n=>n.getAttribute('aria-invalid')==='true');
  const window={crypto:webcrypto,setTimeout(cb,ms){const id=++timerId;timers.set(id,{cb,ms});return id;},clearTimeout(id){timers.delete(id);}};
  const context=vm.createContext({Uint8Array,AbortController,URLSearchParams,window,
    document:{querySelector:s=>s==='#booking-form'?form:s==='#availability-form'?availabilityForm:nodes[s.slice(1)],
      querySelectorAll:()=>others,getElementById:id=>nodes[id],createElement:()=>node()},
    fetch:(url,options)=>{fetches.push({url,options});return implementation(url,options);}});
  for(const file of ['availability.js','booking.js']) vm.runInContext(fs.readFileSync(path.join(__dirname,'../booking_app/static',file),'utf8'),context);
  const select=()=>window.selectBookingRoom({id:1,name:'合成 <房间>',location:'101'},
      {start:'2026-11-12T12:00',end:'2026-11-12T13:00',attendees:'5'});
  return {form,button,inputs,nodes,others,fetches,timers,select,availabilityForm,get active(){return active;},
    setFetch(f){implementation=f;},submit:()=>form.dispatch('submit'),query:()=>availabilityForm.dispatch('submit')};
}
const successBody=()=>({ok:true,data:{booking:{id:7,title:'<img>中文 🧪',start_local:'2026-11-12T12:00:00+08:00',end_local:'2026-11-12T13:00:00+08:00'},replayed:false}});
const success=()=>({ok:true,status:201,json:async()=>successBody()});
const statuses={INVALID_INPUT:400,AUTH_REQUIRED:401,OCCUPANCY_CONFLICT:409,CAPACITY_CONFLICT:409,INTERNAL_ERROR:500};
const failure=(code,fields={})=>({ok:false,status:statuses[code]||500,json:async()=>({ok:false,error:{code,message:code,fields,conflicts:[]}})});
const available=()=>({ok:true,status:200,json:async()=>({ok:true,data:{items:[],total:0}})});

test('selected query creates 32-byte intent; pending disables controls and success is plain text',async()=>{
  let release; const ui=harness(()=>new Promise(r=>{release=r;}));ui.select();
  assert.equal(ui.active.id,'booking-name');assert.match(ui.nodes['booking-conditions'].textContent,/<房间>.*12:00.*13:00.*5 人/);
  const pending=ui.submit();
  for(const n of [ui.button,ui.inputs.title,ui.inputs.purpose,...ui.others]) assert.equal(n.disabled,true);
  await ui.submit();assert.equal(ui.fetches.length,1);
  const request=ui.fetches[0];assert.equal(request.url,'/api/bookings');assert.equal(request.options.method,'POST');
  assert.equal(request.options.headers['X-CSRF-Token'],'synthetic-csrf');
  const payload=JSON.parse(request.options.body);assert.match(payload.intent_key,/^[a-f0-9]{64}$/);
  assert.equal(payload.attendees,5);assert.equal(payload.room_id,1);assert.equal(payload.title,ui.inputs.title.value);
  release(success());await pending;
  assert.match(ui.nodes['booking-feedback'].textContent,/预约成功.*编号 7.*<img>中文 🧪/);
  assert.equal(ui.button.disabled,true);assert.equal(ui.timers.size,0);
  await ui.submit();assert.equal(ui.fetches.length,1);
  ui.select();assert.equal(ui.button.textContent,'确认预约');ui.setFetch(async()=>success());await ui.submit();
  assert.notEqual(JSON.parse(ui.fetches[1].options.body).intent_key,payload.intent_key);
});

test('field validation focuses restored control; conflicts and internal failure preserve content and key',async()=>{
  const ui=harness(async()=>failure('INVALID_INPUT',{title:'活动名错误'}));ui.select();await ui.submit();
  assert.equal(ui.inputs.title.getAttribute('aria-invalid'),'true');assert.equal(ui.active,ui.inputs.title);
  assert.equal(ui.nodes['booking-title-error'].textContent,'活动名错误');
  for(const code of ['OCCUPANCY_CONFLICT','CAPACITY_CONFLICT','INTERNAL_ERROR']) {
    ui.setFetch(async()=>failure(code));await ui.submit();assert.equal(ui.button.disabled,false);
    assert.equal(ui.inputs.title.value,'  中文 🧪 <img>  ');assert.equal(ui.inputs.purpose.value,'用途');
  }
  assert.equal(new Set(ui.fetches.map(r=>JSON.parse(r.options.body).intent_key)).size,1);
});

test('unknown network and malformed response lock repeat submission without claiming failure',async()=>{
  for(const f of [async()=>{throw Error();},async()=>({ok:true,json:async()=>{throw Error();}}),async()=>({ok:false,json:async()=>({})})]) {
    const ui=harness(f);ui.select();await ui.submit();
    assert.match(ui.nodes['booking-feedback'].textContent,/未能确认.*输入已保留.*不支持可靠重试/);
    assert.equal(ui.button.disabled,true);assert.equal(ui.inputs.title.value,'  中文 🧪 <img>  ');
    ui.select();await ui.submit();assert.equal(ui.fetches.length,1);assert.equal(ui.timers.size,0);
  }
});

test('20-second timeout covers stalled response body and does not resend',async()=>{
  let signal;
  const ui=harness(async(_url,opts)=>{signal=opts.signal;return {ok:true,json:()=>new Promise((_resolve,reject)=>signal.addEventListener('abort',()=>reject(Error())))}});
  ui.select();const pending=ui.submit();await new Promise(setImmediate);
  const timer=[...ui.timers.values()][0];assert.equal(timer.ms,20000);timer.cb();await pending;
  assert.equal(signal.aborted,true);assert.equal(ui.button.disabled,true);assert.equal(ui.fetches.length,1);
});

test('session loss shows relogin and never automatically submits again',async()=>{
  const ui=harness(async()=>failure('AUTH_REQUIRED'));ui.select();await ui.submit();
  assert.equal(ui.nodes['booking-relogin'].hidden,false);assert.equal(ui.fetches.length,1);
  assert.equal(ui.inputs.purpose.value,'用途');
});


test('a query in progress blocks creation; after it settles creation restores all controls',async()=>{
  let release;
  const ui=harness(()=>new Promise(resolve=>{release=resolve;}));ui.select();
  const pendingQuery=ui.query();
  assert.equal(ui.availabilityForm.getAttribute('aria-busy'),'true');
  await ui.submit();
  assert.equal(ui.fetches.length,1);assert.match(ui.fetches[0].url,/^\/api\/availability/);
  assert.match(ui.nodes['booking-feedback'].textContent,/仍在查询.*稍候/);
  assert.equal(ui.form.getAttribute('aria-busy'),undefined);
  assert.equal(ui.others[3].disabled,true);
  release(available());await pendingQuery;
  ui.setFetch(async()=>failure('OCCUPANCY_CONFLICT'));await ui.submit();
  assert.equal(ui.fetches.length,2);assert.equal(ui.button.disabled,false);
  for(const control of ui.others) assert.equal(control.disabled,false);
});

test('creation in progress blocks queries; unknown result then permits queries without permitting another write',async()=>{
  let reject;
  const ui=harness(()=>new Promise((_resolve,rejection)=>{reject=rejection;}));ui.select();
  const writing=ui.submit();await ui.query();
  assert.equal(ui.fetches.length,1);assert.equal(ui.others[3].disabled,true);
  reject(Error('response lost'));await writing;
  for(const control of ui.others) assert.equal(control.disabled,false);
  assert.equal(ui.button.disabled,true);assert.equal(ui.inputs.title.disabled,true);
  ui.setFetch(async()=>available());await ui.query();
  assert.equal(ui.fetches.length,2);assert.match(ui.fetches[1].url,/^\/api\/availability/);
  const conditions=ui.nodes['booking-conditions'].textContent;
  ui.select();await ui.submit();
  assert.equal(ui.nodes['booking-conditions'].textContent,conditions);
  assert.equal(ui.fetches.length,2);assert.equal(ui.inputs.title.value,'  中文 🧪 <img>  ');
});

test('selecting a room after a field error resets feedback style and role',async()=>{
  const ui=harness(async()=>failure('INVALID_INPUT',{title:'活动名错误'}));ui.select();await ui.submit();
  const feedback=ui.nodes['booking-feedback'];
  assert.equal(feedback.getAttribute('role'),'alert');assert.equal(feedback.classList.contains('error'),true);
  ui.select();
  assert.equal(feedback.getAttribute('role'),'status');assert.equal(feedback.classList.contains('error'),false);
  assert.equal(ui.nodes['booking-title-error'].textContent,'');
  assert.equal(ui.inputs.title.getAttribute('aria-invalid'),undefined);
});

test('malformed success envelopes or displayed fields never claim success',async()=>{
  const mutations=[body=>{delete body.data.booking.id;},body=>{delete body.data.booking.title;},
    body=>{body.data.booking.id='7';},body=>{body.data.booking.id=0;},body=>{body.data.booking.id=true;},
    body=>{body.data.booking.title=17;},body=>{body.data.booking.title='  ';},
    body=>{body.data.booking.start_local=null;},body=>{body.data.booking.end_local='2026-11-12T13:00Z';},
    body=>{body.data.booking.start_local='2026-02-30T12:00:00+08:00';},
    body=>{body.data.booking.end_local=body.data.booking.start_local;},
    body=>{body.ok=1;},body=>{body.extra='unexpected';},body=>{delete body.data.replayed;},body=>{body.data.replayed=true;}];
  for(const mutate of mutations) {
    const body=successBody();mutate(body);
    const ui=harness(async()=>({ok:true,status:201,json:async()=>body}));ui.select();await ui.submit();
    assert.match(ui.nodes['booking-feedback'].textContent,/未能确认/);
    assert.doesNotMatch(ui.nodes['booking-feedback'].textContent,/预约成功|undefined/);
    assert.equal(ui.button.disabled,true);assert.equal(ui.others[3].disabled,false);
  }
});

test('unknown codes, inconsistent status, and malformed error envelopes are unknown outcomes',async()=>{
  const cases=[failure('NEW_UNRECOGNIZED_CODE'),{...failure('INTERNAL_ERROR'),status:502},
    {ok:true,status:201,json:async()=>({ok:false,error:{code:'INTERNAL_ERROR',message:'error',fields:{},conflicts:[]}})},
    {ok:false,status:500,json:async()=>({ok:false,error:{code:'INTERNAL_ERROR',message:'error',fields:[],conflicts:[]}})},
    {ok:false,status:500,json:async()=>({ok:false,error:{code:'INTERNAL_ERROR',message:'error',fields:{}}})}];
  for(const response of cases) {
    const ui=harness(async()=>response);ui.select();await ui.submit();
    assert.match(ui.nodes['booking-feedback'].textContent,/未能确认/);
    await ui.submit();assert.equal(ui.fetches.length,1);
  }
});
