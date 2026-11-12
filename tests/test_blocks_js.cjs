// Actual Story 3.2 handlers, with controlled transport/body failures and focus.
const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const block={id:120,room:{id:30,name:'<img src=x>',location:'楼',capacity:20},creator_id:3,creator_display_name:'管理员',reason:'<script>纯文本</script>',
  start_at:1794535200,start_local:'2026-11-13T10:00:00+08:00',end_at:1794643200,end_local:'2026-11-14T16:00:00+08:00',status:'pending',created_at:1794448800,created_local:'2026-11-12T10:00:00+08:00',
  revoked_at:null,revoked_local:null,revoked_by_id:null,revoked_by_display_name:null,revoke_reason:null};
const ok=data=>({ok:true,json:async()=>({ok:true,data})});
const fail=(code,fields={},conflicts=[])=>({ok:false,json:async()=>({ok:false,error:{code,message:'合成错误',fields,conflicts}})});
const tick=()=>new Promise(setImmediate);
function harness({combined=false,transform=source=>source}={}){
  let active,impl=async(url,options)=>ok(options.method?block:{items:[block],total:1}),timer=0;
  const timers=new Map(),fetches=[],n={};
  function node(id='',tag=''){
    const attrs=new Map(),handlers={};let text='',disabled=false;
    return {id,tag,attrs,handlers,children:[],dataset:{},name:'',checked:false,hidden:false,value:'',selectedIndex:0,options:[{textContent:'会议室30'}],classList:{toggle(){}},
      get disabled(){return disabled;},set disabled(v){disabled=v;if(v&&active===this)active=undefined;},
      get textContent(){return text+this.children.map(c=>c.textContent).join('');},set textContent(v){text=String(v);this.children=[];},
      set innerHTML(v){throw new Error('Unsafe HTML');},append(...children){this.children.push(...children);},replaceChildren(...children){this.children=children;},
      setAttribute(k,v){attrs.set(k,v);},removeAttribute(k){attrs.delete(k);},getAttribute(k){return attrs.get(k);},
      addEventListener(k,f){handlers[k]=f;},querySelectorAll(tag){return this.children.flatMap(c=>[...(c.tag===tag?[c]:[]),...c.querySelectorAll(tag)]);},contains(target){return this===target||this.children.some(c=>c.contains(target));},focus(){if(!disabled)active=this;}};
  }
  for(const id of ['block-fields','block-script-unavailable','block-form','block-submit','block-confirm','block-feedback','block-conflicts','block-relogin','block-summary','block-rooms-refresh','block-rooms-feedback','logout-form','room-name'])n[id]=node(id);
  for(const name of ['form','panel','title','reason','reason-error','confirm','submit','feedback','summary','relogin'])n['revoke-'+name]=node('revoke-'+name);
  n['revoke-form'].append(n['revoke-reason'],n['revoke-confirm'],n['revoke-submit']);
  const inputs=['room_id','start','end','reason'].map((name,i)=>{const item=n['block-'+name]=node('block-'+name);item.name=name;item.value=['30','2026-11-13T10:00','2026-11-14T16:00',block.reason][i];n['block-'+name+'-error']=node();return item;});
  n['block-form'].append(...inputs,n['block-submit'],n['block-confirm']);n['block-form'].elements={namedItem:name=>n['block-'+name]};
  for(const kind of ['bookings','blocks']){
    for(const suffix of ['form','items','feedback','submit'])n[`admin-${kind}-${suffix}`]=node(`admin-${kind}-${suffix}`);
    const controls=['room_id','date','status'].map(name=>{const id=`admin-${kind}-${name}`,item=n[id]=node(id);item.name=name;n[`admin-${kind}-${name}-error`]=node();return item;});
    n[`admin-${kind}-form`].append(...controls,n[`admin-${kind}-submit`]);n[`admin-${kind}-form`].elements={namedItem:name=>n[`admin-${kind}-${name}`]};
  }
  n['logout-form'].elements={csrf_token:{value:'synthetic'}};const body=node('body'),events=new Map();
  for (const suffix of ['form','panel','title','summary','fields','reason','reason-error','confirm','submit','feedback','relogin']) n['admin-cancel-'+suffix]=node('admin-cancel-'+suffix);
  n['admin-cancel-form'].append(n['admin-cancel-fields']);
  n['admin-cancel-fields'].append(n['admin-cancel-reason'],n['admin-cancel-confirm'],n['admin-cancel-submit']);
  const document={getElementById:id=>n[id],querySelector:s=>n[s.slice(1)],createElement:tag=>node('',tag),body,get activeElement(){return active;},
    addEventListener(name,handler){if(!events.has(name))events.set(name,[]);events.get(name).push(handler);},
    dispatchEvent(event){for(const handler of events.get(event.type)||[])handler(event);}};
  const environment={AbortController,URLSearchParams,CustomEvent:class {constructor(type,options){this.type=type;this.detail=options.detail;}},document,
    window:{setTimeout(fn,ms){timers.set(++timer,{fn,ms});return timer;},clearTimeout(id){timers.delete(id);}},
    fetch:(url,options)=>{fetches.push({url,options});return impl(url,options);}};
  if(combined){
    for(const id of ['room-form','admin-rooms','room-form-title','room-submit','room-cancel','room-confirm','rooms-refresh','room-feedback','rooms-feedback','room-conflicts','room-relogin'])n[id]=node(id);
    for(const name of ['name','location','capacity']){const input=n['room-'+name]=node('room-'+name);input.name=name;input.value=String(block.room[name]);n['room-'+name+'-error']=node();n['room-form'].append(input);}
    n['room-form'].append(n['room-submit'],n['room-cancel'],n['room-confirm']);n['room-form'].elements={namedItem:name=>n['room-'+name]};
    const edit=node('edit','button');edit.dataset.room=JSON.stringify(block.room);n['admin-rooms'].append(edit);
    vm.runInNewContext(fs.readFileSync(path.join(__dirname,'../booking_app/static/rooms.js'),'utf8'),environment);
  }
  n['block-fields'].disabled=true;n['block-submit'].disabled=true;
  vm.runInNewContext(transform(fs.readFileSync(path.join(__dirname,'../booking_app/static/blocks.js'),'utf8')),environment);
  return {n,inputs,timers,fetches,document,get active(){return active;},setFetch:f=>{impl=f;},
    submit(){n['block-confirm'].checked=true;n['block-submit'].focus();return n['block-form'].handlers.submit({preventDefault(){}});},
    refresh(){n['block-rooms-refresh'].focus();return n['block-rooms-refresh'].handlers.click();},
    roomSubmit(){n['room-confirm'].checked=true;n['room-submit'].focus();return n['room-form'].handlers.submit({preventDefault(){}});},
    choose(index=0){return n['admin-bookings-items'].children[index].querySelectorAll('button')[0].handlers.click();},
    cancel(){n['admin-cancel-confirm'].checked=true;n['admin-cancel-submit'].focus();return n['admin-cancel-form'].handlers.submit({preventDefault(){}});},
    load(kind='blocks'){n[`admin-${kind}-submit`].focus();return n[`admin-${kind}-form`].handlers.submit({preventDefault(){}});}};
}
function restored(ui){assert.equal(ui.n['block-submit'].disabled,false);assert.equal(ui.n['block-form'].getAttribute('aria-busy'),undefined);assert.equal(ui.timers.size,0);}
for(const operation of ['create','query'])for(const phase of ['headers','body'])test(`${operation} ${phase} timeout restores controls and draft, with one request`,async()=>{
  const ui=harness();ui.setFetch(async(_url,{signal})=>{const stall=()=>new Promise((_resolve,reject)=>signal.addEventListener('abort',()=>reject(Error())));return phase==='headers'?stall():{ok:true,json:stall};});
  const pending=operation==='create'?ui.submit():ui.load();await tick();assert.equal(ui.n['block-submit'].disabled,true);
  const timer=[...ui.timers.values()][0];assert.equal(timer.ms,20000);timer.fn();await pending;restored(ui);assert.equal(ui.fetches.length,1);assert.equal(ui.inputs[3].value,block.reason);
  assert.match(ui.n[operation==='create'?'block-feedback':'admin-blocks-feedback'].textContent,operation==='create'?/未能确认.*不会自动重试/:/查询失败/);
});
for(const failure of ['network','bad-json','extra-key','missing-null','bad-null','malformed-error'])test(`create ${failure} preserves input and restores controls`,async()=>{
  const ui=harness();ui.setFetch(async()=>{
    if(failure==='network')throw Error();if(failure==='bad-json')return {ok:true,json:async()=>{throw Error();}};
    if(failure==='malformed-error')return fail('OCCUPANCY_CONFLICT',{},[null]);
    const data={...block};if(failure==='extra-key')data.cancelled_at=null;if(failure==='missing-null')delete data.revoked_local;if(failure==='bad-null')data.revoke_reason='unexpected';return ok(data);
  });await ui.submit();restored(ui);assert.match(ui.n['block-feedback'].textContent,/未能确认/);assert.equal(ui.fetches.length,1);assert.equal(ui.inputs[3].value,block.reason);
});
test('successful create lists complete plain text fields',async()=>{
  const ui=harness();await ui.submit();restored(ui);assert.equal(ui.n['block-confirm'].checked,false);assert.match(ui.n['block-feedback'].textContent,/已创建/);
  assert.match(ui.n['admin-blocks-items'].textContent,/<script>纯文本<\/script>/);assert.match(ui.n['admin-blocks-items'].textContent,/未撤销/);assert.equal(ui.fetches.length,2);
});
test('field rejection focuses enabled field and retry restores success',async()=>{
  const ui=harness();ui.setFetch(async()=>fail('INVALID_INPUT',{reason:'原因无效'}));await ui.submit();restored(ui);assert.equal(ui.active,ui.inputs[3]);assert.equal(ui.inputs[3].value,block.reason);
  ui.setFetch(async(_url,options)=>ok(options.method?block:{items:[block],total:1}));await ui.submit();restored(ui);assert.equal(ui.inputs[3].getAttribute('aria-invalid'),undefined);
});
const conflict={id:10,type:'booking',room_id:30,start_at:block.start_at,start_local:block.start_local,end_at:block.end_at,end_local:block.end_local,status:'pending',attendees:5,reason:null};
test('booking and block conflicts display required facts as text and preserve original input',async()=>{
  const ui=harness();ui.setFetch(async()=>fail('OCCUPANCY_CONFLICT',{},[conflict,{...conflict,id:11,type:'block',attendees:null,reason:'<svg>维护'}]));
  await ui.submit();restored(ui);
  assert.equal(ui.n['block-conflicts'].textContent,
    '预约 10 · 会议室 30 · 北京时间 2026-11-13 10:00:00 至 2026-11-14 16:00:00 · 待开始 · 5 人'+
    '停用 11 · 会议室 30 · 北京时间 2026-11-13 10:00:00 至 2026-11-14 16:00:00 · 待开始 · 原因：<svg>维护');
  assert.equal(ui.inputs[3].value,block.reason);
});
for(const code of ['STORE_BUSY','INTERNAL_ERROR','NOT_FOUND','CSRF_REJECTED'])test(`${code} restores inputs without retry`,async()=>{
  const ui=harness();ui.setFetch(async()=>fail(code));await ui.submit();restored(ui);assert.equal(ui.fetches.length,1);assert.match(ui.n['block-feedback'].textContent,/输入已保留/);
});
for(const code of ['AUTH_REQUIRED','FORBIDDEN'])test(`${code} blocks resubmission and clears protected lists while preserving draft`,async()=>{
  const ui=harness();await ui.load();ui.setFetch(async()=>fail(code));await ui.submit();assert.equal(ui.n['block-submit'].disabled,true);assert.equal(ui.n['block-relogin'].hidden,false);
  assert.equal(ui.n['admin-blocks-items'].children.length,0);assert.equal(ui.inputs[3].value,block.reason);await ui.submit();assert.equal(ui.fetches.length,2);
});
for(const result of ['success','failure','list-failure'])test(`${result} does not steal focus from another form`,async()=>{
  const ui=harness();let release;ui.setFetch(async(url,options)=>options.method?new Promise(r=>{release=r;}):result==='list-failure'?fail('STORE_BUSY'):ok({items:[block],total:1}));
  const pending=ui.submit();ui.n['room-name'].focus();release(result==='failure'?fail('OCCUPANCY_CONFLICT'):ok(block));await pending;restored(ui);assert.equal(ui.active,ui.n['room-name']);
  if(result==='list-failure'){assert.match(ui.n['block-feedback'].textContent,/已创建/);assert.match(ui.n['admin-blocks-feedback'].textContent,/已创建.*刷新失败/);}
});
for(const name of ['room_id','start','end','reason'])for(const event of ['input','change'])test(`${name} ${event} invalidates confirmation and updates preview`,async()=>{
  const ui=harness();ui.n['block-confirm'].checked=true;ui.n['block-'+name].handlers[event]();assert.equal(ui.n['block-confirm'].checked,false);
  await ui.n['block-form'].handlers.submit({preventDefault(){}});assert.equal(ui.fetches.length,0);assert.match(ui.n['block-summary'].textContent,/北京时间.*2026-11-13T10:00/);
});
test('filters sent only when selected, legal empty lists differ from not yet queried',async()=>{
  const ui=harness();assert.equal(ui.fetches.length,0);ui.n['admin-blocks-room_id'].value='30';ui.n['admin-blocks-date'].value='2026-11-14';ui.n['admin-blocks-status'].value='ended';
  ui.setFetch(async()=>ok({items:[],total:0}));await ui.load();restored(ui);assert.equal(ui.fetches[0].url,'/api/admin/blocks?room_id=30&date=2026-11-14&status=ended');
  assert.match(ui.n['admin-blocks-feedback'].textContent,/没有符合条件/);assert.equal(ui.active,ui.n['admin-blocks-feedback']);
});
test('malformed list never renders partial records and query can be retried',async()=>{
  const ui=harness();ui.setFetch(async()=>ok({items:[block,{...block,creator_id:'private'}],total:2}));await ui.load();restored(ui);assert.equal(ui.n['admin-blocks-items'].children.length,0);
  ui.setFetch(async()=>ok({items:[block],total:1}));await ui.load();restored(ui);assert.equal(ui.n['admin-blocks-items'].children.length,1);
});
for(const code of ['AUTH_REQUIRED','FORBIDDEN'])test(`created block remains explicitly successful when automatic list refresh gets ${code}`,async()=>{
  const ui=harness();ui.setFetch(async(_url,options)=>options.method?ok(block):fail(code));await ui.submit();
  assert.match(ui.n['block-feedback'].textContent,/停用 120 已创建.*重新登录/);assert.equal(ui.n['block-submit'].disabled,true);
  assert.equal(ui.n['admin-blocks-items'].children.length,0);assert.equal(ui.n['block-relogin'].hidden,false);assert.equal(ui.timers.size,0);
});
test('query waits prevent competing creation and restore the same input on completion',async()=>{
  const ui=harness();let release;ui.setFetch(()=>new Promise(r=>{release=r;}));const pending=ui.load();
  await ui.submit();assert.equal(ui.fetches.length,1);release(ok({items:[],total:0}));await pending;restored(ui);assert.equal(ui.inputs[3].value,block.reason);
});
for(const value of ['9007199254740993','9223372036854775807'])test(`unsafe selected room ${value} never sends a POST to its rounded neighbour`,async()=>{
  const ui=harness();ui.inputs[0].value=value;await ui.submit();restored(ui);assert.equal(ui.fetches.length,0);
  assert.equal(ui.inputs[0].value,value);assert.equal(ui.inputs[0].getAttribute('aria-invalid'),'true');assert.equal(ui.active,ui.inputs[0]);
});
test('unsafe refreshed room ID rejects the directory before changing any selector',async()=>{
  const ui=harness();ui.setFetch(async()=>ok({items:[{...block.room,id:Number('9007199254740993')}],total:1}));
  await ui.refresh();restored(ui);assert.equal(ui.inputs[0].value,'30');assert.equal(ui.n['admin-blocks-room_id'].children.length,0);
  assert.match(ui.n['block-rooms-feedback'].textContent,/刷新失败/);assert.equal(ui.fetches.filter(r=>r.options.method).length,0);
});
test('initial disabled fieldset becomes available only after initialization',()=>{
  const ui=harness();assert.equal(ui.n['block-fields'].disabled,false);assert.equal(ui.n['block-script-unavailable'].hidden,true);restored(ui);
});
test('unknown outcome clears confirmation and another submit cannot send until reconfirmed',async()=>{
  const ui=harness();ui.setFetch(async()=>{throw Error();});await ui.submit();restored(ui);assert.equal(ui.n['block-confirm'].checked,false);
  await ui.n['block-form'].handlers.submit({preventDefault(){}});assert.equal(ui.fetches.length,1);assert.match(ui.n['block-feedback'].textContent,/查询停用记录核对.*重新核对并勾选确认/);
});
for(const kind of ['bookings','blocks'])for(const name of ['room_id','date','status'])test(`${kind} changed ${name} clears stale rows/count until deliberate query`,async()=>{
  const ui=harness();ui.setFetch(async()=>ok({items:[],total:0}));await ui.load(kind);ui.n[`admin-${kind}-${name}`].value=name==='date'?'2026-11-14':name==='status'?'ended':'30';
  ui.n[`admin-${kind}-${name}`].handlers.change();assert.equal(ui.n[`admin-${kind}-items`].children.length,0);assert.match(ui.n[`admin-${kind}-feedback`].textContent,/条件已更改.*重新查询/);
  assert.equal(ui.fetches.length,1);await ui.load(kind);restored(ui);assert.equal(ui.fetches.length,2);assert.match(ui.n[`admin-${kind}-feedback`].textContent,/没有符合条件/);
});
for(const name of ['room_id','date','status'])test(`query ${name} errors attach to restored control, and correction preserves other-form focus`,async()=>{
  const ui=harness();const input=ui.n['admin-blocks-'+name];input.value='invalid';ui.setFetch(async()=>fail('INVALID_INPUT',{[name]:'字段错误'}));
  await ui.load();restored(ui);assert.equal(input.getAttribute('aria-invalid'),'true');assert.equal(ui.n['admin-blocks-'+name+'-error'].textContent,'字段错误');assert.equal(ui.active,input);assert.equal(input.value,'invalid');
  input.value='';input.handlers.change();let release;ui.setFetch(()=>new Promise(r=>{release=r;}));const pending=ui.load();ui.n['room-name'].focus();release(ok({items:[],total:0}));await pending;
  restored(ui);assert.equal(input.getAttribute('aria-invalid'),undefined);assert.equal(ui.active,ui.n['room-name']);
});
test('refresh fills all three selectors with new room while preserving complete draft and selections',async()=>{
  const ui=harness();ui.n['admin-bookings-room_id'].value='30';ui.n['admin-blocks-room_id'].value='30';const before=ui.inputs.map(i=>i.value);ui.n['block-confirm'].checked=true;
  const added={id:40,name:'新会议室',location:'新楼',capacity:7};ui.setFetch(async()=>ok({items:[block.room,added],total:2}));await ui.refresh();restored(ui);
  for(const select of [ui.inputs[0],ui.n['admin-bookings-room_id'],ui.n['admin-blocks-room_id']]){
    assert.equal(select.value,'30');assert.deepEqual(select.children.map(o=>[o.value,o.textContent]).slice(1),[['30','<img src=x> · 楼'],['40','新会议室 · 新楼']]);
  }
  assert.deepEqual(ui.inputs.map(i=>i.value),before);assert.equal(ui.n['block-confirm'].checked,false);
});
for(const phase of ['network','headers','body'])test(`room-option refresh ${phase} failure restores draft, selectors and controls`,async()=>{
  const ui=harness();const before=ui.inputs.map(i=>i.value);ui.setFetch(async(_url,{signal})=>{
    if(phase==='network')throw Error();const stall=()=>new Promise((_r,reject)=>signal.addEventListener('abort',()=>reject(Error())));return phase==='headers'?stall():{ok:true,json:stall};
  });const pending=ui.refresh();await tick();if(phase!=='network')[...ui.timers.values()][0].fn();await pending;restored(ui);
  assert.deepEqual(ui.inputs.map(i=>i.value),before);assert.match(ui.n['block-rooms-feedback'].textContent,/刷新失败/);assert.equal(ui.fetches.length,1);
});
for(const direction of ['rooms','blocks'])for(const code of ['AUTH_REQUIRED','FORBIDDEN'])test(`${direction} detects ${code} and blocks both panels while preserving drafts`,async()=>{
  const ui=harness({combined:true});await ui.load();const draft=ui.inputs.map(i=>i.value),roomDraft=ui.n['room-name'].value;ui.setFetch(async()=>fail(code));
  if(direction==='rooms')await ui.roomSubmit();else await ui.load();
  assert.equal(ui.n['block-submit'].disabled,true);assert.equal(ui.n['room-submit'].disabled,true);assert.equal(ui.n['admin-rooms'].children.length,0);assert.equal(ui.n['admin-blocks-items'].children.length,0);
  assert.deepEqual(ui.inputs.map(i=>i.value),draft);assert.equal(ui.n['room-name'].value,roomDraft);assert.equal(ui.n['room-relogin'].hidden,false);assert.equal(ui.n['block-relogin'].hidden,false);
});
for(const late of ['room-directory','block-list','room-write','block-write'])test(`late ${late} success cannot repopulate results after the other panel loses identity`,async()=>{
  const ui=harness({combined:true});let release;ui.setFetch(async(url,options)=>{
    if(late==='room-directory'&&url==='/api/rooms')return new Promise(r=>{release=r;});
    if(late==='block-list'&&url.startsWith('/api/admin/blocks?'))return new Promise(r=>{release=r;});
    if(late==='room-write'&&url==='/api/admin/rooms')return new Promise(r=>{release=r;});
    if(late==='block-write'&&url==='/api/admin/blocks')return new Promise(r=>{release=r;});
    return fail('AUTH_REQUIRED');
  });
  let pending;
  if(late==='room-directory')pending=ui.n['rooms-refresh'].handlers.click();else if(late==='room-write')pending=ui.roomSubmit();else if(late==='block-write')pending=ui.submit();else pending=ui.load();
  if(late.startsWith('room'))await ui.load();else await ui.roomSubmit();
  release(ok(late==='room-directory'?{items:[block.room],total:1}:late==='block-list'?{items:[block],total:1}:late==='room-write'?block.room:block));await pending;
  assert.equal(ui.n['admin-rooms'].children.length,0);assert.equal(ui.n['admin-blocks-items'].children.length,0);assert.equal(ui.n['block-submit'].disabled,true);assert.equal(ui.n['room-submit'].disabled,true);
});
for(const saved of ['room','block'])test(`confirmed ${saved} success survives identity loss in the other panel`,async()=>{
  const ui=harness({combined:true});ui.setFetch(async(url,options)=>ok(url==='/api/rooms'?{items:[block.room],total:1}:options.method?(url==='/api/admin/rooms'?block.room:block):{items:[block],total:1}));
  if(saved==='room')await ui.roomSubmit();else await ui.submit();
  ui.setFetch(async()=>fail('FORBIDDEN'));if(saved==='room')await ui.load();else await ui.roomSubmit();
  assert.match(ui.n[saved==='room'?'room-feedback':'block-feedback'].textContent,saved==='room'?/资料已保存.*重新登录/:/停用 120 已创建.*重新登录/);
});
const {assertRendered}=require('./maintenance_render_contract.cjs');
function visibleRows(ui,kind){return ui.n[`admin-${kind}-items`].children.map(item=>({title:item.children[0].textContent,pairs:item.children[1].children.reduce((pairs,node,i,all)=>{if(i%2===0)pairs.push([node.textContent,all[i+1].textContent]);return pairs;},[])}));}
function fixtures(kind){return ['pending','in_progress','ended',kind==='bookings'?'cancelled':'revoked'].map((status,i)=>{
  const common={id:200+i,room:{id:30+i,name:`房间${i}<img>`,location:`地点${i}`,capacity:10+i},start_at:block.start_at+i*3600,end_at:block.end_at+i*3600,
    start_local:`2026-11-${13+i}T10:00:00+08:00`,end_local:`2026-11-${14+i}T16:00:00+08:00`,status,created_at:block.created_at-i*86400,created_local:`2026-11-0${9-i}T08:30:00+08:00`};
  const terminal=kind==='bookings'?'cancelled':'revoked';Object.assign(common,{[terminal+'_at']:i===3?1794445000:null,[terminal+'_local']:i===3?'2026-11-11T09:30:00+08:00':null,[terminal+'_by_id']:i===3?9:null,[terminal+'_by_display_name']:i===3?'操作人<svg>':null,[kind==='bookings'?'cancel_reason':'revoke_reason']:i===3?'终态原因<script>':null});
  return {...common,...(kind==='bookings'?{title:`标题${i}`,purpose:`私密用途${i}`,attendees:2+i,owner_id:1+i,owner_display_name:`预约人${i}`}:{reason:`维护原因${i}`,creator_id:7+i,creator_display_name:`创建者${i}`})};
});}
for(const kind of ['bookings','blocks'])test(`all four ${kind} states render every row, label and distinct complete value`,async()=>{
  const rows=fixtures(kind),ui=harness();ui.setFetch(async()=>ok({items:rows,total:rows.length}));await ui.load(kind);assertRendered(visibleRows(ui,kind),rows,kind);restored(ui);
});
for(const mutant of ['empty-booking','missing-purpose'])test(`render oracle rejects ${mutant} regression`,async()=>{
  const rows=fixtures('bookings'),ui=harness({transform:source=>mutant==='empty-booking'?source.replace('for (const row of records) {','for (const row of (list.kind === "bookings" ? [] : records)) {'):source.replace('["用途",row.purpose],','')});
  ui.setFetch(async()=>ok({items:rows,total:rows.length}));await ui.load('bookings');assert.throws(()=>assertRendered(visibleRows(ui,'bookings'),rows,'bookings'),assert.AssertionError);
});

function adminBooking(status='pending') {
  const row=fixtures('bookings')[0];row.status=status;
  if(status==='cancelled')Object.assign(row,{cancelled_at:1794448800,cancelled_local:'2026-11-12T10:00:00+08:00',cancelled_by_id:3,cancelled_by_display_name:'管理员 <svg>',cancel_reason:'原原因 <script>'});
  return row;
}
async function cancellationUI(options){
  const ui=harness(options);ui.setFetch(async()=>ok({items:[adminBooking()],total:1}));await ui.load('bookings');ui.choose();ui.n['admin-cancel-reason'].value='维护 <script>';return ui;
}
function cancelRestored(ui){assert.equal(ui.n['admin-cancel-fields'].disabled,false);assert.equal(ui.n['admin-cancel-form'].getAttribute('aria-busy'),undefined);assert.equal(ui.timers.size,0);}
test('admin cancellation requires confirmation, reason edits reset it and eligible states expose controls',async()=>{
  const ui=harness();ui.setFetch(async()=>ok({items:['pending','in_progress','ended','cancelled'].map(adminBooking),total:4}));await ui.load('bookings');
  assert.deepEqual(ui.n['admin-bookings-items'].children.map(row=>row.querySelectorAll('button').length),[1,1,0,1]);ui.choose();
  await ui.n['admin-cancel-form'].handlers.submit({preventDefault(){}});assert.equal(ui.fetches.length,1);
  for(const name of ['input','change']){ui.n['admin-cancel-confirm'].checked=true;ui.n['admin-cancel-reason'].handlers[name]();assert.equal(ui.n['admin-cancel-confirm'].checked,false);}
});
test('admin cancellation sends only reason to selected ID, prevents repeat pending requests, refreshes and renders saved facts as text',async()=>{
  const ui=await cancellationUI();let release;ui.setFetch(async(_url,options)=>options.method?new Promise(resolve=>{release=resolve;}):ok({items:[adminBooking('cancelled')],total:1}));
  const pending=ui.cancel();assert.equal(ui.n['admin-cancel-fields'].disabled,true);assert.equal(ui.n['admin-bookings-submit'].disabled,true);
  await ui.cancel();assert.equal(ui.fetches.length,2);assert.equal(ui.fetches[1].url,'/api/admin/bookings/200/cancel');
  assert.deepEqual(JSON.parse(ui.fetches[1].options.body),{reason:'维护 <script>'});assert.equal(ui.fetches[1].options.headers['X-CSRF-Token'],'synthetic');
  ui.n['room-name'].focus();release(ok(adminBooking('cancelled')));await pending;cancelRestored(ui);
  assert.equal(ui.active,ui.n['room-name']);assert.match(ui.n['admin-cancel-summary'].textContent,/原取消原因：原原因 <script>/);
  assert.match(ui.n['admin-bookings-items'].textContent,/已取消/);assert.equal(ui.fetches.length,3);assert.equal(ui.n['admin-cancel-confirm'].checked,false);
});
for(const code of ['INVALID_INPUT','INTERNAL_ERROR','STORE_BUSY','CSRF_REJECTED'])test(`admin cancel ${code} preserves reason and allows deliberate retry`,async()=>{
  const ui=await cancellationUI();ui.setFetch(async()=>fail(code,code==='INVALID_INPUT'?{reason:'原因错误'}:{}));await ui.cancel();cancelRestored(ui);
  assert.equal(ui.n['admin-cancel-reason'].value,'维护 <script>');assert.equal(ui.fetches.length,2);assert.match(ui.n['admin-cancel-feedback'].textContent,/原因已保留/);
  if(code==='INVALID_INPUT'){assert.equal(ui.active,ui.n['admin-cancel-reason']);assert.equal(ui.n['admin-cancel-reason'].getAttribute('aria-invalid'),'true');}
});
for(const failure of ['network','malformed','mismatched-id','incomplete','timeout-headers','timeout-body'])test(`admin cancel ${failure} is unconfirmed without automatic retry`,async()=>{
  const ui=await cancellationUI();ui.setFetch(async(_url,{signal})=>{
    if(failure==='network')throw Error();
    if(failure.startsWith('timeout')){const stall=()=>new Promise((_r,reject)=>signal.addEventListener('abort',()=>reject(Error())));return failure==='timeout-headers'?stall():{ok:true,json:stall};}
    if(failure==='malformed')return {ok:true,json:async()=>{throw Error();}};
    const row=adminBooking('cancelled');if(failure==='mismatched-id')row.id=201;else delete row.cancel_reason;return ok(row);
  });const pending=ui.cancel();await tick();if(failure.startsWith('timeout'))[...ui.timers.values()][0].fn();await pending;cancelRestored(ui);
  assert.match(ui.n['admin-cancel-feedback'].textContent,/未能确认.*不会自动重试/);assert.equal(ui.n['admin-cancel-confirm'].checked,false);
  assert.equal(ui.n['admin-cancel-reason'].value,'维护 <script>');await ui.n['admin-cancel-form'].handlers.submit({preventDefault(){}});assert.equal(ui.fetches.length,2);
});
for(const code of ['AUTH_REQUIRED','FORBIDDEN'])test(`admin cancel ${code} clears protected data and blocks writes retaining reason`,async()=>{
  const ui=await cancellationUI();ui.setFetch(async()=>fail(code));await ui.cancel();assert.equal(ui.n['admin-cancel-fields'].disabled,true);
  assert.equal(ui.n['admin-bookings-items'].children.length,0);assert.equal(ui.n['admin-cancel-summary'].textContent,'');assert.equal(ui.n['admin-cancel-reason'].value,'维护 <script>');
  assert.equal(ui.n['admin-cancel-relogin'].hidden,false);await ui.cancel();assert.equal(ui.fetches.length,2);
});
for(const code of ['STORE_BUSY','AUTH_REQUIRED','FORBIDDEN'])test(`admin cancel successful result remains successful when refresh gets ${code}`,async()=>{
  const ui=await cancellationUI();ui.setFetch(async(_url,options)=>options.method?ok(adminBooking('cancelled')):fail(code));await ui.cancel();
  assert.match(ui.n['admin-cancel-feedback'].textContent,/预约 200 已取消/);assert.equal(ui.fetches.length,3);
  if(code==='STORE_BUSY'){cancelRestored(ui);assert.match(ui.n['admin-bookings-feedback'].textContent,/取消已成功.*刷新失败/);}
});
test('admin cancel repeated member cancellation accepts original null reason and unsafe ID never posts',async()=>{
  const ui=await cancellationUI();const row=adminBooking('cancelled');row.cancel_reason=null;row.cancelled_by_id=row.owner_id;
  ui.setFetch(async(_url,options)=>ok(options.method?row:{items:[row],total:1}));await ui.cancel();cancelRestored(ui);assert.match(ui.n['admin-cancel-summary'].textContent,/本人取消，无原因/);
  ui.setFetch(async()=>ok({items:[{...row,id:Number('9223372036854775807')}],total:1}));await ui.load('bookings');ui.choose();
  assert.match(ui.n['admin-bookings-feedback'].textContent,/无法安全提交/);
});

function assertDisarmed(ui){
  assert.equal(ui.n['admin-cancel-confirm'].checked,false);
  assert.equal(ui.n['admin-cancel-summary'].textContent,'');
  assert.equal(ui.n['admin-cancel-reason'].value,'维护 <script>');
  assert.equal(ui.n['admin-cancel-fields'].disabled,true);
}
for(const field of ['room_id','date','status'])for(const event of ['input','change'])test(`booking ${field} ${event} disarms old cancellation while preserving draft`,async()=>{
  const ui=await cancellationUI();ui.n['admin-cancel-confirm'].checked=true;
  ui.n[`admin-bookings-${field}`].handlers[event]();assertDisarmed(ui);
  await ui.cancel();assert.equal(ui.fetches.length,1);assert.match(ui.n['admin-cancel-feedback'].textContent,/重新查询/);
});
test('manual booking requery disarms selected target before response, even for empty results',async()=>{
  const ui=await cancellationUI();ui.n['admin-cancel-confirm'].checked=true;let release;ui.setFetch(()=>new Promise(r=>{release=r;}));
  const pending=ui.load('bookings');assertDisarmed(ui);release(ok({items:[],total:0}));await pending;
  assertDisarmed(ui);await ui.cancel();assert.equal(ui.fetches.length,2);
});
test('unsafe booking click clears previously armed safe booking and retains draft',async()=>{
  const ui=harness();ui.setFetch(async()=>ok({items:[adminBooking(),{...adminBooking(),id:Number('9223372036854775807')}],total:2}));
  await ui.load('bookings');ui.choose(0);ui.n['admin-cancel-reason'].value='维护 <script>';ui.n['admin-cancel-confirm'].checked=true;
  ui.choose(1);assertDisarmed(ui);await ui.cancel();assert.equal(ui.fetches.length,1);
});
for(const code of ['TRANSITION_CLOSED','NOT_FOUND'])test(`admin cancellation ${code} clears target and requires query instead of retry`,async()=>{
  const ui=await cancellationUI();ui.setFetch(async()=>fail(code));await ui.cancel();assertDisarmed(ui);
  assert.match(ui.n['admin-cancel-feedback'].textContent,/重新查询并选择预约/);assert.doesNotMatch(ui.n['admin-cancel-feedback'].textContent,/重试/);
  await ui.cancel();assert.equal(ui.fetches.length,2);
});
test('successful cancellation with empty pending refresh preserves complete target summary and known result',async()=>{
  const ui=await cancellationUI(),row=adminBooking('cancelled');ui.n['admin-bookings-status'].value='pending';
  ui.setFetch(async(_url,options)=>ok(options.method?row:{items:[],total:0}));await ui.cancel();cancelRestored(ui);
  assert.equal(ui.n['admin-bookings-items'].children.length,0);assert.equal(ui.fetches[2].url,'/api/admin/bookings?status=pending');
  assert.equal(ui.n['admin-cancel-summary'].textContent,'预约 200 · 标题0 · 已取消\n会议室：30 · 房间0<img> · 地点0\n预约时段（北京时间）：2026-11-13 10:00:00 至 2026-11-14 16:00:00\n取消时间（北京时间）：2026-11-12 10:00:00\n操作者：管理员 <svg>\n原取消原因：原原因 <script>');
  assert.match(ui.n['admin-cancel-feedback'].textContent,/预约 200 已取消/);
  await ui.cancel();assert.equal(ui.fetches.filter(call=>call.options.method==='POST').length,2);
});
async function lateCancellationOracle(code,transform){
  const ui=await cancellationUI({combined:true,transform});let release;
  ui.setFetch(async url=>url.endsWith('/cancel')?new Promise(r=>{release=r;}):fail(code));
  const pending=ui.cancel();await ui.roomSubmit();
  assert.equal(ui.n['admin-cancel-summary'].textContent,'');
  release(ok(adminBooking('cancelled')));await pending;
  assert.equal(ui.n['admin-cancel-summary'].textContent,'');
  assert.equal(ui.n['admin-cancel-fields'].disabled,true);assert.equal(ui.n['room-submit'].disabled,true);
  assert.equal(ui.n['admin-cancel-reason'].value,'维护 <script>');assert.equal(ui.n['admin-cancel-relogin'].hidden,false);
  assert.match(ui.n['admin-cancel-feedback'].textContent,/预约 200 已取消.*重新登录/);
  assert.equal(ui.n['admin-bookings-items'].children.length,0);assert.equal(ui.fetches.length,3);
}
for(const code of ['AUTH_REQUIRED','FORBIDDEN']){
  test(`rooms ${code} followed by late admin cancellation keeps protected summary empty and known success`,async()=>lateCancellationOracle(code));
  test(`late admin cancellation oracle detects removed blocked guard after rooms ${code}`,async()=>{
    const guard='if (blocked) { say(cancelFeedback,`${cancelledMessage} 请重新登录后查看详情。`,true); return; }';
    await assert.rejects(lateCancellationOracle(code,source=>{assert.ok(source.includes(guard));return source.replace(guard,'');}),assert.AssertionError);
  });
}

const revoked={...block,status:'revoked',revoked_at:1794448800,revoked_local:'2026-11-12T10:00:00+08:00',revoked_by_id:4,revoked_by_display_name:'首次管理员 <svg>',revoke_reason:'首次撤销 <script>纯文本</script>'};
async function selectRevoke(ui){await ui.load();ui.n['admin-blocks-items'].querySelectorAll('button')[0].handlers.click();ui.n['revoke-reason'].value=' 修复完成 <img> ';}
function submitRevoke(ui,confirm=true){ui.n['revoke-confirm'].checked=confirm;ui.n['revoke-submit'].focus();return ui.n['revoke-form'].handlers.submit({preventDefault(){}});}
function revokeRestored(ui){restored(ui);assert.equal(ui.n['revoke-form'].getAttribute('aria-busy'),undefined);assert.equal(ui.n['revoke-reason'].value,' 修复完成 <img> ');}
test('revocation is offered only for pending/ongoing safe block IDs, never bookings',async()=>{
  const ui=harness();ui.setFetch(async()=>ok({items:fixtures('blocks'),total:4}));await ui.load();
  assert.deepEqual(ui.n['admin-blocks-items'].querySelectorAll('button').map(n=>n.textContent),['选择撤销停用 200','选择撤销停用 201']);
  ui.setFetch(async()=>ok({items:fixtures('bookings'),total:4}));await ui.load('bookings');assert.equal(ui.n['admin-bookings-items'].querySelectorAll('button').filter(button=>button.textContent.includes('撤销停用')).length,0);
  ui.setFetch(async()=>ok({items:[{...block,id:Number('9007199254740993')}],total:1}));await ui.load();assert.equal(ui.n['admin-blocks-items'].querySelectorAll('button').length,0);assert.match(ui.n['admin-blocks-items'].textContent,/当前浏览器无法安全提交此编号/);
});
test('selected original facts and successful first revocation metadata render as text',async()=>{
  const ui=harness();await selectRevoke(ui);assert.match(ui.n['revoke-summary'].textContent,/<script>纯文本/);assert.equal(ui.active,ui.n['revoke-title']);
  await submitRevoke(ui,false);assert.equal(ui.fetches.length,1);
  ui.setFetch(async(_url,options)=>ok(options.method?revoked:{items:[revoked],total:1}));await submitRevoke(ui);revokeRestored(ui);
  const post=ui.fetches.find(r=>r.options.method);assert.equal(post.url,'/api/admin/blocks/120/revoke');assert.deepEqual(JSON.parse(post.options.body),{reason:' 修复完成 <img> '});
  assert.equal(post.options.headers['X-CSRF-Token'],'synthetic');assert.match(ui.n['revoke-feedback'].textContent,/已撤销.*全部占用已释放/);
  assert.match(ui.n['revoke-summary'].textContent,/首次管理员 <svg>.*\n撤销原因：首次撤销 <script>/);
  assert.equal(ui.n['revoke-form'].hidden,true);assert.equal(ui.n['admin-blocks-items'].querySelectorAll('button').length,0);
  await submitRevoke(ui);assert.equal(ui.fetches.length,3);
});
for(const event of ['input','change'])test(`revoke reason ${event} requires fresh confirmation`,async()=>{
  const ui=harness();await selectRevoke(ui);ui.n['revoke-confirm'].checked=true;ui.n['revoke-reason'].handlers[event]();
  assert.equal(ui.n['revoke-confirm'].checked,false);await ui.n['revoke-form'].handlers.submit({preventDefault(){}});assert.equal(ui.fetches.length,1);
});
test('waiting revocation disables competing controls and blocks double submission',async()=>{
  const ui=harness();await selectRevoke(ui);let release;ui.setFetch(()=>new Promise(r=>{release=r;}));const pending=submitRevoke(ui);
  assert.equal(ui.n['revoke-form'].getAttribute('aria-busy'),'true');assert.match(ui.n['revoke-feedback'].textContent,/正在撤销/);
  for(const id of ['revoke-reason','revoke-submit','block-submit','admin-blocks-submit'])assert.equal(ui.n[id].disabled,true);
  await submitRevoke(ui);await ui.submit();await ui.load();await ui.refresh();assert.equal(ui.fetches.length,2);
  ui.n['room-name'].focus();release(fail('STORE_BUSY'));await pending;revokeRestored(ui);assert.equal(ui.active,ui.n['room-name']);
});
for(const code of ['INVALID_INPUT','STORE_BUSY','INTERNAL_ERROR','CSRF_REJECTED'])test(`revoke ${code} preserves reason and requires reconfirmation`,async()=>{
  const ui=harness();await selectRevoke(ui);ui.setFetch(async()=>fail(code,code==='INVALID_INPUT'?{reason:'原因无效'}:{}));await submitRevoke(ui);revokeRestored(ui);
  assert.match(ui.n['revoke-feedback'].textContent,/撤销原因已保留/);assert.equal(ui.n['revoke-confirm'].checked,false);assert.equal(ui.n['revoke-submit'].disabled,false);
  if(code==='INVALID_INPUT'){assert.equal(ui.active,ui.n['revoke-reason']);assert.equal(ui.n['revoke-reason'].getAttribute('aria-invalid'),'true');}
  if(code==='CSRF_REJECTED')assert.equal(ui.n['revoke-relogin'].hidden,false);
});
for(const failure of ['network','bad-json','wrong-id','not-revoked','missing-field'])test(`uncertain revoke ${failure} preserves input without auto retry`,async()=>{
  const ui=harness();await selectRevoke(ui);ui.setFetch(async()=>{
    if(failure==='network')throw Error();if(failure==='bad-json')return {ok:true,json:async()=>{throw Error();}};
    if(failure==='wrong-id')return ok({...revoked,id:121});if(failure==='not-revoked')return ok(block);
    const row={...revoked};delete row.revoke_reason;return ok(row);
  });await submitRevoke(ui);revokeRestored(ui);assert.match(ui.n['revoke-feedback'].textContent,/未能确认.*重新确认后重试/);assert.equal(ui.fetches.length,2);
  await ui.n['revoke-form'].handlers.submit({preventDefault(){}});assert.equal(ui.fetches.length,2);
});
for(const phase of ['headers','body'])test(`revoke timeout during ${phase} preserves reason and restores controls`,async()=>{
  const ui=harness();await selectRevoke(ui);ui.setFetch(async(_url,{signal})=>{const stall=()=>new Promise((_r,reject)=>signal.addEventListener('abort',()=>reject(Error())));return phase==='headers'?stall():{ok:true,json:stall};});
  const pending=submitRevoke(ui);await tick();[...ui.timers.values()][0].fn();await pending;revokeRestored(ui);assert.match(ui.n['revoke-feedback'].textContent,/未能确认/);
});
for(const code of ['AUTH_REQUIRED','FORBIDDEN'])test(`revoke ${code} blocks all admin controls and preserves reason`,async()=>{
  const ui=harness({combined:true});await selectRevoke(ui);ui.setFetch(async()=>fail(code));await submitRevoke(ui);
  assert.equal(ui.n['revoke-reason'].value,' 修复完成 <img> ');assert.equal(ui.n['revoke-submit'].disabled,true);assert.equal(ui.n['room-submit'].disabled,true);
  assert.equal(ui.n['revoke-relogin'].hidden,false);assert.equal(ui.n['admin-blocks-items'].children.length,0);await submitRevoke(ui);assert.equal(ui.fetches.length,2);
});
for(const code of ['STORE_BUSY','AUTH_REQUIRED'])test(`successful revoke stays explicit when automatic refresh gets ${code}`,async()=>{
  const ui=harness();await selectRevoke(ui);ui.setFetch(async(_url,options)=>options.method?ok(revoked):fail(code));await submitRevoke(ui);
  assert.match(ui.n['revoke-feedback'].textContent,/停用 120 已撤销/);assert.equal(ui.n['revoke-reason'].value,' 修复完成 <img> ');
  if(code==='STORE_BUSY')assert.match(ui.n['admin-blocks-feedback'].textContent,/停用已撤销.*列表刷新失败/);
});
for(const code of ['AUTH_REQUIRED','FORBIDDEN'])test(`late revoke success remains known after room panel detects ${code}`,async()=>{
  const ui=harness({combined:true});await selectRevoke(ui);let release;ui.setFetch(async url=>url.endsWith('/revoke')?new Promise(r=>{release=r;}):fail(code));
  const pending=submitRevoke(ui);await ui.roomSubmit();release(ok(revoked));await pending;
  assert.equal(ui.n['revoke-submit'].disabled,true);assert.equal(ui.n['admin-blocks-items'].children.length,0);assert.equal(ui.n['revoke-summary'].textContent,'');assert.equal(ui.n['revoke-confirm'].checked,false);assert.equal(ui.n['room-submit'].disabled,true);assert.equal(ui.n['revoke-reason'].value,' 修复完成 <img> ');assert.match(ui.n['revoke-feedback'].textContent,/停用 120 已撤销.*重新登录查看/);
});

for(const code of ['TRANSITION_CLOSED','NOT_FOUND'])test(`revoke ${code} invalidates target and requests a new query`,async()=>{
  const ui=harness();await selectRevoke(ui);ui.setFetch(async()=>fail(code));await submitRevoke(ui);revokeRestored(ui);
  assert.equal(ui.n['revoke-summary'].textContent,'');assert.equal(ui.n['revoke-confirm'].checked,false);assert.equal(ui.n['revoke-submit'].disabled,true);assert.match(ui.n['revoke-feedback'].textContent,/重新查询/);
  await submitRevoke(ui);assert.equal(ui.fetches.length,2);
});
for(const field of ['room_id','date','status'])for(const event of ['input','change'])test(`block filter ${field} ${event} invalidates selected target before a new query`,async()=>{
  const ui=harness();await selectRevoke(ui);ui.n['revoke-confirm'].checked=true;
  ui.n[`admin-blocks-${field}`].handlers[event]();
  assert.equal(ui.n['revoke-confirm'].checked,false);assert.equal(ui.n['revoke-summary'].textContent,'');assert.equal(ui.n['revoke-reason'].value,' 修复完成 <img> ');assert.equal(ui.n['revoke-submit'].disabled,true);
  await submitRevoke(ui);assert.equal(ui.fetches.length,1);
});
for(const status of ['ended','revoked'])test(`manual refresh clears target before returning fresh ${status} record`,async()=>{
  const ui=harness();await selectRevoke(ui);ui.n['revoke-confirm'].checked=true;let release;ui.setFetch(()=>new Promise(resolve=>{release=resolve;}));
  const pending=ui.load();assert.equal(ui.n['revoke-confirm'].checked,false);assert.equal(ui.n['revoke-summary'].textContent,'');await submitRevoke(ui);assert.equal(ui.fetches.length,2);
  release(ok({items:[status==='revoked'?revoked:{...block,status}],total:1}));await pending;
  assert.equal(ui.n['revoke-submit'].disabled,true);assert.equal(ui.n['revoke-reason'].value,' 修复完成 <img> ');assert.equal(ui.n['admin-blocks-items'].querySelectorAll('button').length,0);
  await submitRevoke(ui);assert.equal(ui.fetches.length,2);
});
test('late list response after a filter edit cannot restore selection or protected summary',async()=>{
  const ui=harness();await selectRevoke(ui);let release;ui.setFetch(()=>new Promise(resolve=>{release=resolve;}));const pending=ui.load();
  ui.n['admin-blocks-status'].handlers.change();release(ok({items:[block],total:1}));await pending;
  assert.equal(ui.n['admin-blocks-items'].children.length,0);assert.equal(ui.n['revoke-summary'].textContent,'');await submitRevoke(ui);assert.equal(ui.fetches.length,2);
});
test('submit guard rejects a selected record that is now ended',async()=>{
  const current={...block},ui=harness();ui.setFetch(async()=>ok({items:[current],total:1}));await selectRevoke(ui);current.status='ended';await submitRevoke(ui);assert.equal(ui.fetches.length,1);
});
function assertSelectedInterval(ui,row){
  const text=ui.n['revoke-summary'].textContent;
  assert.equal(text.split('\n')[2],`北京时间：${row.start_local.replace('T',' ').slice(0,19)} 至 ${row.end_local.replace('T',' ').slice(0,19)}`);
  assert.equal(text.split('\n')[3],`原停用原因：${row.reason}`);
}
test('selection summary binds exact distinct start and end for two different records',async()=>{
  const rows=fixtures('blocks').slice(0,2),ui=harness();ui.setFetch(async()=>ok({items:rows,total:2}));await ui.load();
  for(const [i,row] of rows.entries()){ui.n['admin-blocks-items'].querySelectorAll('button')[i].handlers.click();assertSelectedInterval(ui,row);}
});
test('summary interval oracle rejects end accidentally bound to start',async()=>{
  const ui=harness({transform:source=>source.replace('formatted(row.end_local)}\\n原停用原因','formatted(row.start_local)}\\n原停用原因')});await selectRevoke(ui);
  assert.throws(()=>assertSelectedInterval(ui,block),assert.AssertionError);
});

async function bothAdminTargets(){
  const ui=harness({combined:true});
  ui.setFetch(async url=>ok({items:[url.includes('/bookings')?adminBooking():block],total:1}));
  await ui.load('bookings');ui.choose();ui.n['admin-cancel-reason'].value='取消草稿';
  await selectRevoke(ui);return ui;
}
for(const first of ['cancel','revoke'])test(`integrated ${first} pending excludes the other admin transition and restores both drafts`,async()=>{
  const ui=await bothAdminTargets();let release;ui.setFetch(()=>new Promise(resolve=>{release=resolve;}));
  const pending=first==='cancel'?ui.cancel():submitRevoke(ui);
  assert.equal(ui.n['admin-cancel-fields'].disabled,true);assert.equal(ui.n['revoke-submit'].disabled,true);
  if(first==='cancel')await submitRevoke(ui);else await ui.cancel();
  assert.equal(ui.fetches.filter(c=>c.options.method==='POST').length,1);
  release(fail('STORE_BUSY'));await pending;
  assert.equal(ui.n['admin-cancel-fields'].disabled,false);assert.equal(ui.n['revoke-submit'].disabled,false);
  assert.equal(ui.n['admin-cancel-reason'].value,'取消草稿');assert.equal(ui.n['revoke-reason'].value,' 修复完成 <img> ');
  assert.equal(ui.timers.size,0);
});
for(const first of ['cancel','revoke'])test(`integrated ${first} identity refusal clears both protected panels and prevents both writes`,async()=>{
  const ui=await bothAdminTargets();ui.setFetch(async()=>fail('AUTH_REQUIRED'));
  if(first==='cancel')await ui.cancel();else await submitRevoke(ui);
  assert.equal(ui.n['admin-cancel-summary'].textContent,'');assert.equal(ui.n['revoke-summary'].textContent,'');
  assert.equal(ui.n['admin-cancel-fields'].disabled,true);assert.equal(ui.n['revoke-submit'].disabled,true);
  assert.equal(ui.n['room-submit'].disabled,true);assert.equal(ui.n['block-submit'].disabled,true);
  await ui.cancel();await submitRevoke(ui);assert.equal(ui.fetches.filter(c=>c.options.method==='POST').length,1);
  assert.equal(ui.n['admin-cancel-reason'].value,'取消草稿');assert.equal(ui.n['revoke-reason'].value,' 修复完成 <img> ');
});
