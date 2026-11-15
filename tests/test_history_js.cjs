// Run the real history.js handlers, including automatic initial loading and detail retry.
const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const booking = {supervisor_id:null,supervisor_display_name:null,supervisor_source:'legacy',application_id:null,approved_at:null,approved_by:null,start_at:1794456000,end_at:1794459600,created_at:1794362400,id:104,title:'<img src=x onerror="evil()">',purpose:'<script>evil()</script>',attendees:5,
  room:{id:2,name:'合成房间',location:'演示楼',capacity:20},owner_id:1,owner_display_name:'成员',
  start_local:'2026-11-12T12:00:00+08:00',end_local:'2026-11-12T13:00:00+08:00',
  created_local:'2026-11-11T10:00:00+08:00',status:'pending',cancelled_at:null,
  cancelled_local:null,cancelled_by_id:null,cancelled_by_display_name:null,cancel_reason:null};

const expectedFields = [
  ['预约编号','104'],['活动名称','<img src=x onerror="evil()">'],['用途','<script>evil()</script>'],
  ['预计人数','5 人'],['会议室','合成房间'],['会议室编号','2'],['位置','演示楼'],['当前容量','20 人'],
  ['所属导师','历史未绑定'],['审批申请编号','无（直接预约或历史记录）'],['批准时间','无'],['批准人编号','无'],['预约人','成员'],['预约人编号','1'],['开始时间（北京时间）','2026-11-12 12:00:00'],
  ['结束时间（北京时间）','2026-11-12 13:00:00'],['状态','待开始'],['创建时间（北京时间）','2026-11-11 10:00:00'],
  ['取消时间（北京时间）','未取消'],['取消操作者','无（未取消）'],['取消操作者编号','无（未取消）'],['取消原因','无（未取消）'],
];
function fieldPairs(fields){
  assert.equal(fields.children.length,44);
  const result=[];
  for(let i=0;i<fields.children.length;i+=2){
    assert.equal(fields.children[i].tag,'dt');assert.equal(fields.children[i+1].tag,'dd');
    result.push([fields.children[i].textContent,fields.children[i+1].textContent]);
  }
  return result;
}
const list = (items=[]) => ({items,total:items.length});
const ok = data => ({ok:true,json:async()=>({ok:true,data})});
const fail = (code,fields={}) => ({ok:false,json:async()=>({ok:false,error:{code,message:'合成错误',fields,conflicts:[]}})});
const tick = () => new Promise(setImmediate);
function harness(initialFetch) {
  let activeElement, fetchImpl=initialFetch, timerId=0;
  const timers=new Map(), fetches=[];
  function node(id='',tag='') {
    const attrs=new Map(), handlers={};
    return {id,tag,attrs,handlers,children:[],_disabled:false,hidden:false,value:'',_text:'',
      set disabled(value){this._disabled=value;if(value&&activeElement===this)activeElement=undefined;},
      get disabled(){return this._disabled;},
      set textContent(v){this._text=String(v);this.children=[];},
      get textContent(){return this._text+this.children.map(c=>c.textContent).join('');},
      set innerHTML(v){throw new Error('User data must stay plain text');},
      classList:{toggle(){}},
      append(child){this.children.push(child);},replaceChildren(){this.children=[];},
      setAttribute(k,v){attrs.set(k,v);},removeAttribute(k){attrs.delete(k);},getAttribute(k){return attrs.get(k);},
      addEventListener(event,handler){handlers[event]=handler;},
      querySelectorAll(tag){return this.children.flatMap(c=>[...(c.tag===tag?[c]:[]),...c.querySelectorAll(tag)]);},
      focus(){if(!this.disabled)activeElement=this;}};
  }
  const nodes=Object.fromEntries(['history-form','history-items','history-feedback','history-status-error','history-relogin',
    'history-detail','detail-title','detail-feedback','detail-fields','detail-relogin','detail-retry',
    'cancel-form','cancel-confirm','cancel-submit','cancel-feedback','logout-form'].map(id=>[id,node(id)]));
  nodes['logout-form'].elements={csrf_token:{value:'synthetic-csrf'}};
  const form=nodes['history-form'], select=node('history-status'), submit=node('submit','button');
  form.elements={status:select};form.querySelector=()=>submit;
  vm.runInNewContext(fs.readFileSync(path.join(__dirname,'../booking_app/static/contracts.js'),'utf8')+'\n'+fs.readFileSync(path.join(__dirname,'../booking_app/static/history.js'),'utf8'),{
    AbortController,URLSearchParams,
    document:{body:{getAttribute:()=> 'teacher'},get activeElement(){return activeElement;},querySelector:selector=>nodes[selector.slice(1)],createElement:tag=>node('',tag)},
    window:{setTimeout(callback,ms){const id=++timerId;timers.set(id,{callback,ms});return id;},clearTimeout(id){timers.delete(id);}},
    fetch:(url,opts)=>{fetches.push({url,opts});return fetchImpl(url,opts);}
  });
  return {nodes,form,select,submit,timers,fetches,get activeElement(){return activeElement;},
    setFetch(f){fetchImpl=f;},filter(value='pending'){select.value=value;submit.focus();return form.handlers.submit({preventDefault(){}});},
    detail(){return nodes['history-items'].querySelectorAll('button')[0].handlers.click();},
    cancel(){return nodes['cancel-form'].handlers.submit({preventDefault(){}});},
    retry(){return nodes['detail-retry'].handlers.click();}};
}
function restored(ui){assert.equal(ui.submit.disabled,false);assert.equal(ui.select.disabled,false);
  assert.equal(ui.form.getAttribute('aria-busy'),undefined);assert.equal(ui.nodes['history-detail'].getAttribute('aria-busy'),undefined);
  assert.equal(ui.timers.size,0);}
for(const phase of ['headers','body']) {
  test(`history list timeout in ${phase} restores controls and permits explicit retry`,async()=>{
    const ui=harness(async(_url,{signal})=>{
      const stalled=()=>new Promise((_r,reject)=>signal.addEventListener('abort',()=>reject(new Error('aborted')),{once:true}));
      return phase==='headers'?stalled():{ok:true,json:stalled};
    });
    await tick();assert.equal(ui.submit.disabled,true);assert.equal(ui.form.getAttribute('aria-busy'),'true');
    await ui.filter();assert.equal(ui.fetches.length,1);
    const timer=[...ui.timers.values()][0];assert.equal(timer.ms,20000);timer.callback();await tick();
    restored(ui);assert.match(ui.nodes['history-feedback'].textContent,/筛选条件已保留/);
    assert.equal(ui.fetches.length,1);ui.setFetch(async()=>ok(list()));await ui.filter();restored(ui);
    assert.match(ui.nodes['history-feedback'].textContent,/暂无待开始/);
    assert.equal(ui.fetches[1].url,'/api/bookings/mine?status=pending');
  });
}
for(const failure of ['network','bad-json']) {
  test(`history ${failure} clears results and allows manual recovery`,async()=>{
    const ui=harness(async()=>{if(failure==='network')throw new TypeError('offline');return {ok:true,json:async()=>{throw new SyntaxError();}};});
    await tick();restored(ui);assert.equal(ui.nodes['history-feedback'].getAttribute('role'),'alert');
    ui.setFetch(async()=>ok(list([booking])));await ui.filter('');restored(ui);
    assert.equal(ui.nodes['history-items'].querySelectorAll('button').length,1);
    assert.equal(ui.nodes['history-items'].querySelectorAll('img').length,0);
    assert.ok(ui.nodes['history-items'].textContent.includes(booking.title));
  });
}
test('status field error focuses enabled select; successful empty filter clears error',async()=>{
  const ui=harness(async()=>fail('INVALID_INPUT',{status:'状态错误'}));await tick();restored(ui);
  assert.equal(ui.activeElement,ui.select);assert.equal(ui.select.getAttribute('aria-invalid'),'true');
  ui.setFetch(async()=>ok(list()));await ui.filter('cancelled');
  assert.equal(ui.select.getAttribute('aria-invalid'),undefined);assert.equal(ui.nodes['history-status-error'].textContent,'');
  assert.match(ui.nodes['history-feedback'].textContent,/暂无已取消/);
});
test('detail is plain text, focus moves to heading, and all uncancelled nulls have meaning',async()=>{
  const ui=harness(async()=>ok(list([booking])));await tick();ui.setFetch(async()=>ok(booking));await ui.detail();restored(ui);
  const fields=ui.nodes['detail-fields'];assert.equal(fields.hidden,false);assert.ok(fields.textContent.includes(booking.purpose));
  assert.equal(fields.querySelectorAll('script').length,0);assert.equal(ui.activeElement,ui.nodes['detail-title']);
  assert.deepEqual(fieldPairs(fields), expectedFields);
  assert.match(ui.nodes['history-feedback'].textContent,/列表是本次查询的状态快照.*查看预约.*刷新/);
  assert.match(ui.nodes['detail-feedback'].textContent,/状态以本次读取为准.*列表快照不同.*查看预约.*刷新/);
  assert.equal(ui.fetches[1].url,'/api/bookings/104');
});
for(const failure of ['network','bad-json','not-found','timeout']) {
  test(`detail ${failure} restores filters and offers only an explicit read retry`,async()=>{
    const ui=harness(async()=>ok(list([booking])));await tick();
    ui.setFetch(async(_url,{signal})=>{
      if(failure==='network')throw new TypeError();
      if(failure==='bad-json')return {ok:true,json:async()=>{throw new SyntaxError();}};
      if(failure==='not-found')return fail('NOT_FOUND');
      return {ok:true,json:()=>new Promise((_r,reject)=>signal.addEventListener('abort',()=>reject(new Error()),{once:true}))};
    });
    const pending=ui.detail();await tick();
    if(failure==='timeout'){
      assert.equal(ui.select.disabled,true);assert.equal(ui.nodes['history-detail'].getAttribute('aria-busy'),'true');
      await ui.filter();assert.equal(ui.fetches.length,2);[...ui.timers.values()][0].callback();
    }
    await pending;restored(ui);assert.equal(ui.nodes['detail-fields'].hidden,true);assert.equal(ui.nodes['detail-retry'].hidden,false);
    assert.equal(ui.fetches.length,2);ui.setFetch(async()=>ok({...booking,status:'cancelled',cancelled_at:1794445200,
      cancelled_local:'2026-11-12T09:00:00+08:00',cancelled_by_id:1,cancelled_by_display_name:'成员'}));
    await ui.retry();restored(ui);assert.match(ui.nodes['detail-fields'].textContent,/未填写（本人取消无需原因）/);
    assert.equal(ui.fetches.length,3);assert.ok(ui.fetches.every(f=>!f.opts.method));
  });
}
for(const area of ['list','detail']) {
  test(`${area} session loss clears personal data and does not retry automatically`,async()=>{
    const ui=harness(async()=>ok(list([booking])));await tick();ui.setFetch(async()=>fail('AUTH_REQUIRED'));
    if(area==='list')await ui.filter();else await ui.detail();restored(ui);
    assert.equal(ui.nodes['history-items'].children.length,0);assert.equal(ui.nodes['detail-fields'].hidden,true);
    assert.equal(ui.nodes['history-relogin'].hidden,false);assert.equal(ui.nodes['detail-relogin'].hidden,false);
    assert.equal(ui.nodes['detail-retry'].hidden,true);assert.equal(ui.fetches.length,2);
    for(const id of ['history-feedback','detail-feedback']){
      assert.match(ui.nodes[id].textContent,/登录已失效.*列表与详情已清空/);
      assert.doesNotMatch(ui.nodes[id].textContent,/查询成功|共 1 条|已读取预约/);
      assert.equal(ui.nodes[id].getAttribute('role'),'alert');
    }
    assert.equal(ui.activeElement,ui.nodes[area==='list'?'history-feedback':'detail-feedback']);
  });
}

for(const empty of [false,true]) {
  test(`successful ${empty?'empty':'populated'} keyboard filter restores submit focus after unlocking`,async()=>{
    const ui=harness(async()=>ok(list()));await tick();
    let resolve;ui.setFetch(()=>new Promise(done=>{resolve=done;}));
    const pending=ui.filter('pending');assert.equal(ui.submit.disabled,true);assert.equal(ui.activeElement,undefined);
    resolve(ok(list(empty?[]:[booking])));await pending;restored(ui);
    assert.equal(ui.activeElement,ui.submit);
  });
}
for(const member of [false,true]) {
  test(`complete ${member?'member':'admin'} cancellation detail uses each independent label/value`,async()=>{
    const ui=harness(async()=>ok(list([booking])));await tick();
    ui.setFetch(async()=>ok({...booking,status:'cancelled',cancelled_at:1794446142,cancelled_local:'2026-11-12T09:15:42+08:00',
      cancelled_by_id:member?1:3,cancelled_by_display_name:member?'成员':'管理员',cancel_reason:member?null:'设备检修'}));
    await ui.detail();
    assert.deepEqual(fieldPairs(ui.nodes['detail-fields']),expectedFields.slice(0,16).concat([
      ['状态','已取消'],['创建时间（北京时间）','2026-11-11 10:00:00'],['取消时间（北京时间）','2026-11-12 09:15:42'],
      ['取消操作者',member?'成员':'管理员'],['取消操作者编号',member?'1':'3'],
      ['取消原因',member?'未填写（本人取消无需原因）':'设备检修'],
    ]));
  });
}
test('detail can cross a boundary while list retains its stated snapshot until explicit refresh',async()=>{
  const ui=harness(async()=>ok(list([booking])));await tick();
  ui.setFetch(async()=>ok({...booking,status:'in_progress'}));await ui.detail();
  assert.match(ui.nodes['history-items'].textContent,/待开始/);
  assert.equal(fieldPairs(ui.nodes['detail-fields']).find(([label])=>label==='状态')[1],'进行中');
  assert.match(ui.nodes['detail-feedback'].textContent,/本次读取.*列表快照不同.*查看预约.*刷新/);
  assert.equal(ui.fetches.length,2);
  ui.setFetch(async()=>ok(list([{...booking,status:'in_progress'}])));await ui.filter('');
  assert.match(ui.nodes['history-items'].textContent,/进行中/);assert.equal(ui.fetches.length,3);
});

async function cancellationUi(status='pending') {
  const ui=harness(async()=>ok(list([booking])));await tick();
  ui.setFetch(async()=>ok({...booking,status}));await ui.detail();
  ui.nodes['cancel-confirm'].checked=true;return ui;
}
const cancelledBooking={...booking,status:'cancelled',cancelled_at:1794448800,
  cancelled_local:'2026-11-12T10:00:00+08:00',cancelled_by_id:1,cancelled_by_display_name:'成员'};
test('cancellation requires confirmation, posts only an empty object and refreshes current list',async()=>{
  const ui=await cancellationUi();ui.nodes['cancel-confirm'].checked=false;await ui.cancel();assert.equal(ui.fetches.length,2);
  ui.nodes['cancel-confirm'].checked=true;
  ui.setFetch(async(url,opts)=>opts.method?ok(cancelledBooking):ok(list([cancelledBooking])));
  await ui.cancel();restored(ui);
  const request=ui.fetches[2];assert.equal(request.url,'/api/bookings/104/cancel');assert.equal(request.opts.method,'POST');
  assert.equal(request.opts.body,'{}');assert.equal(request.opts.headers['X-CSRF-Token'],'synthetic-csrf');
  assert.equal(ui.fetches[3].url,'/api/bookings/mine');assert.match(ui.nodes['history-items'].textContent,/已取消/);
  assert.equal(fieldPairs(ui.nodes['detail-fields']).find(([label])=>label==='状态')[1],'已取消');
  assert.equal(ui.nodes['cancel-confirm'].checked,false);assert.match(ui.nodes['cancel-feedback'].textContent,/时段已释放/);
});
for(const failure of ['network','bad-json','wrong-record','incomplete-response','headers-timeout','body-timeout','500','409','403','404']) {
  test(`cancellation ${failure} preserves details and restores controls for explicit same-record retry`,async()=>{
    const ui=await cancellationUi();const previous=fieldPairs(ui.nodes['detail-fields']);
    ui.setFetch(async(_url,{signal})=>{
      if(failure==='network')throw new TypeError();
      if(failure==='bad-json')return {ok:true,json:async()=>{throw new SyntaxError();}};
      if(failure==='wrong-record')return ok({...cancelledBooking,id:99});
      if(failure==='incomplete-response')return ok({id:104,status:'cancelled',cancelled_at:1,cancelled_by_id:1});
      if(failure.endsWith('timeout')){
        const stalled=()=>new Promise((_resolve,reject)=>signal.addEventListener('abort',()=>reject(new Error('timeout')),{once:true}));
        return failure==='headers-timeout'?stalled():{ok:true,json:stalled};
      }
      return fail({'500':'INTERNAL_ERROR','409':'TRANSITION_CLOSED','403':'CSRF_REJECTED','404':'NOT_FOUND'}[failure]);
    });
    const pending=ui.cancel();await tick();
    if(failure.endsWith('timeout')){
      assert.equal(ui.nodes['cancel-submit'].disabled,true);assert.equal(ui.nodes['cancel-confirm'].disabled,true);
      await ui.cancel();assert.equal(ui.fetches.length,3);[...ui.timers.values()][0].callback();
    }
    await pending;restored(ui);assert.deepEqual(fieldPairs(ui.nodes['detail-fields']),previous);
    assert.equal(ui.nodes['cancel-confirm'].disabled,false);assert.equal(ui.nodes['cancel-submit'].disabled,false);
    assert.equal(ui.nodes['cancel-form'].getAttribute('aria-busy'),undefined);assert.equal(ui.fetches.length,3);
    ui.setFetch(async(_url,opts)=>opts.method?ok(cancelledBooking):ok(list([cancelledBooking])));
    await ui.cancel();assert.equal(ui.fetches[3].url,'/api/bookings/104/cancel');assert.equal(ui.fetches.length,5);
  });
}
test('cancellation success does not steal focus and list-refresh failure preserves committed detail',async()=>{
  const ui=await cancellationUi();let resolve;
  ui.setFetch((_url,opts)=>opts.method?new Promise(done=>{resolve=done;}):Promise.reject(new TypeError()));
  const pending=ui.cancel();ui.nodes['logout-form'].focus();resolve(ok(cancelledBooking));await pending;
  assert.equal(ui.activeElement,ui.nodes['logout-form']);assert.match(ui.nodes['history-feedback'].textContent,/取消已成功.*列表刷新失败/);
  assert.equal(fieldPairs(ui.nodes['detail-fields']).find(([label])=>label==='状态')[1],'已取消');restored(ui);
});
test('cancellation session loss clears sensitive details and never retries',async()=>{
  const ui=await cancellationUi();ui.setFetch(async()=>fail('AUTH_REQUIRED'));await ui.cancel();
  assert.equal(ui.nodes['cancel-form'].hidden,true);assert.equal(ui.nodes['detail-fields'].hidden,true);
  assert.equal(ui.nodes['history-items'].children.length,0);assert.equal(ui.nodes['detail-relogin'].hidden,false);
  assert.equal(ui.fetches.length,3);restored(ui);
});
for(const status of ['in_progress','ended'])test(`${status} explains cancellation is unavailable`,async()=>{
  const ui=await cancellationUi(status);assert.equal(ui.nodes['cancel-form'].hidden,true);
  assert.match(ui.nodes['cancel-feedback'].textContent,/已开始或结束.*不能取消/);
});

for(const action of ['list','detail'])test(`delayed history ${action} success preserves focus moved to another form`,async()=>{
  const ui=harness(async()=>ok(list([booking])));await tick();let resolve;
  ui.setFetch(()=>new Promise(done=>{resolve=done;}));
  const pending=action==='list'?ui.filter('pending'):ui.detail();
  ui.nodes['logout-form'].focus();resolve(ok(action==='list'?list([booking]):booking));await pending;
  assert.equal(ui.activeElement,ui.nodes['logout-form']);restored(ui);
});

test('mismatched detail ID never renders or enables cancellation of the selected record',async()=>{
  const ui=harness(async()=>ok(list([booking])));await tick();
  ui.setFetch(async()=>ok({...booking,id:999}));await ui.detail();
  assert.equal(ui.nodes['detail-fields'].hidden,true);assert.equal(ui.nodes['detail-fields'].children.length,0);
  assert.equal(ui.nodes['cancel-form'].hidden,true);assert.equal(ui.nodes['detail-retry'].hidden,false);
  ui.nodes['cancel-confirm'].checked=true;await ui.cancel();assert.equal(ui.fetches.length,2);restored(ui);
});
for(const omitted of ['attendees','room.capacity'])test(`cancel success missing ${omitted} preserves prior detail and offers same-record confirmation`,async()=>{
  const ui=await cancellationUi();const before=fieldPairs(ui.nodes['detail-fields']);
  const data={...cancelledBooking,room:{...cancelledBooking.room}};
  if(omitted==='attendees')delete data.attendees;else delete data.room.capacity;
  ui.setFetch(async()=>ok(data));await ui.cancel();
  assert.deepEqual(fieldPairs(ui.nodes['detail-fields']),before);assert.match(ui.nodes['cancel-feedback'].textContent,/未能确认.*104/);
  assert.equal(ui.nodes['cancel-submit'].textContent,'重试确认原预约取消');assert.equal(ui.fetches.length,3);restored(ui);
});
const malformedEnvelopes=[
  ['empty',{}],['null',null],['missing-error',{ok:false}],['null-error',{ok:false,error:null}],
  ['missing-code',{ok:false,error:{message:'bad',fields:{},conflicts:[]}}],
  ['missing-fields',{ok:false,error:{code:'AUTH_REQUIRED',message:'bad',conflicts:[]}}],
  ['invalid-conflicts',{ok:false,error:{code:'INTERNAL_ERROR',message:'bad',fields:{},conflicts:{}}}],
];
for(const [name,body] of malformedEnvelopes)test(`HTTP 200 ${name} envelope is an unknown cancellation result`,async()=>{
  const ui=await cancellationUi();const before=fieldPairs(ui.nodes['detail-fields']);
  ui.setFetch(async()=>({ok:true,json:async()=>body}));await ui.cancel();
  assert.deepEqual(fieldPairs(ui.nodes['detail-fields']),before);assert.match(ui.nodes['cancel-feedback'].textContent,/未能确认.*104.*不会自动重试/);
  assert.equal(ui.nodes['cancel-submit'].textContent,'重试确认原预约取消');assert.equal(ui.fetches.length,3);
  ui.setFetch(async(_url,opts)=>opts.method?ok(cancelledBooking):ok(list([cancelledBooking])));await ui.cancel();
  assert.equal(ui.fetches[3].url,'/api/bookings/104/cancel');restored(ui);
});
test('POST AUTH_REQUIRED clears protected detail and focuses a populated expiry explanation',async()=>{
  const ui=await cancellationUi();ui.nodes['cancel-submit'].focus();ui.setFetch(async()=>fail('AUTH_REQUIRED'));await ui.cancel();
  assert.equal(ui.nodes['detail-fields'].hidden,true);assert.equal(ui.nodes['history-items'].children.length,0);
  assert.equal(ui.activeElement,ui.nodes['detail-feedback']);assert.match(ui.activeElement.textContent,/登录已失效.*已清空/);
  assert.doesNotMatch(ui.nodes['cancel-feedback'].textContent,/取消已成功/);assert.equal(ui.fetches.length,3);restored(ui);
});
test('successful cancellation then refresh AUTH_REQUIRED retains a generic confirmed outcome after clearing data',async()=>{
  const ui=await cancellationUi();ui.nodes['cancel-submit'].focus();
  ui.setFetch(async(_url,opts)=>opts.method?ok(cancelledBooking):fail('AUTH_REQUIRED'));await ui.cancel();
  assert.equal(ui.nodes['detail-fields'].hidden,true);assert.equal(ui.nodes['history-items'].children.length,0);
  for(const id of ['cancel-feedback','detail-feedback','history-feedback']){
    assert.match(ui.nodes[id].textContent,/取消已成功.*登录已失效/);assert.ok(!ui.nodes[id].textContent.includes('104'));
  }
  assert.equal(ui.activeElement,ui.nodes['detail-feedback']);assert.equal(ui.fetches.length,4);restored(ui);
});
for(const succeeded of [true,false])test(`keyboard cancellation ${succeeded?'success':'failure'} restores meaningful focus after disabled button loses it`,async()=>{
  const ui=await cancellationUi();ui.nodes['cancel-submit'].focus();let resolve;
  ui.setFetch((_url,opts)=>opts.method?new Promise(done=>{resolve=done;}):Promise.resolve(ok(list([cancelledBooking]))));
  const pending=ui.cancel();assert.equal(ui.activeElement,undefined);
  resolve(succeeded?ok(cancelledBooking):fail('CSRF_REJECTED'));await pending;
  assert.equal(ui.activeElement,ui.nodes['cancel-feedback']);assert.ok(ui.activeElement.textContent.length>0);restored(ui);
});
test('cancelling the last pending record retains the filter, renders explicit empty feedback and keeps cancelled details',async()=>{
  const ui=harness(async()=>ok(list([booking])));await tick();
  await ui.filter('pending');ui.setFetch(async()=>ok(booking));await ui.detail();ui.nodes['cancel-confirm'].checked=true;
  ui.setFetch(async(_url,opts)=>opts.method?ok(cancelledBooking):ok(list()));await ui.cancel();
  assert.equal(ui.select.value,'pending');assert.equal(ui.fetches.at(-1).url,'/api/bookings/mine?status=pending');
  assert.equal(ui.nodes['history-items'].children.length,0);assert.match(ui.nodes['history-feedback'].textContent,/暂无待开始的预约/);
  assert.equal(fieldPairs(ui.nodes['detail-fields']).find(([label])=>label==='状态')[1],'已取消');restored(ui);
});
