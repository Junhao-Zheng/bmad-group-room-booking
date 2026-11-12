// Execute the actual management handlers with controllable fetch and timers.
const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const room={id:1,name:'<img src=x onerror="evil()">',location:'合成楼',capacity:20};
const ok=data=>({ok:true,json:async()=>({ok:true,data})});
const fail=(code,fields={},conflicts=[])=>({ok:false,json:async()=>({ok:false,error:{code,message:'合成错误',fields,conflicts}})});
const tick=()=>new Promise(setImmediate);
function harness(initialRoom=room){
  let active,impl=async url=>ok(url==='/api/rooms'?{items:[room],total:1}:room),timer=0;
  const timers=new Map(),fetches=[],events=new Map();
  function node(id='',tag=''){
    const attrs=new Map(),handlers={};let text='',disabled=false,value='';
    return {id,tag,attrs,handlers,children:[],name:'',checked:false,hidden:false,dataset:{},classList:{toggle(){}},
      get value(){return value;},set value(v){value=String(v);if(['room-name','room-location'].includes(id))value=value.replace(/\r\n?/g,'\n');},
      get disabled(){return disabled;},set disabled(v){disabled=v;if(v&&active===this)active=undefined;},
      get textContent(){return text+this.children.map(c=>c.textContent).join('');},set textContent(v){text=String(v);this.children=[];},
      set innerHTML(v){throw new Error('Unsafe HTML');},append(...children){this.children.push(...children);},replaceChildren(){this.children=[];},
      setAttribute(k,v){attrs.set(k,v);},removeAttribute(k){attrs.delete(k);},getAttribute(k){return attrs.get(k);},
      addEventListener(k,f){handlers[k]=f;},querySelectorAll(tag){return this.children.flatMap(c=>[...(c.tag===tag?[c]:[]),...c.querySelectorAll(tag)]);},
      contains(target){return this===target||this.children.some(c=>c.contains(target));},focus(){if(!disabled)active=this;}};
  }
  const ids=['room-form','admin-rooms','room-form-title','room-submit','room-cancel','room-confirm','rooms-refresh','room-feedback','rooms-feedback',
    'room-conflicts','room-relogin','room-name','room-location','room-capacity','room-name-error','room-location-error','room-capacity-error','logout-form'];
  const n=Object.fromEntries(ids.map(id=>[id,node(id)]));
  const inputs=['name','location','capacity'].map(name=>{const input=n['room-'+name];input.name=name;input.value=String(initialRoom[name]);return input;});
  n['room-form'].elements={namedItem:name=>n['room-'+name]};n['room-form'].append(...inputs,n['room-submit'],n['room-cancel'],n['room-confirm']);
  n['logout-form'].elements={csrf_token:{value:'synthetic'}};
  const edit=node('edit','button');edit.dataset={room:JSON.stringify(initialRoom)};n['admin-rooms'].append(edit);
  const body=node('body');
  vm.runInNewContext(fs.readFileSync(path.join(__dirname,'../booking_app/static/rooms.js'),'utf8'),{
    AbortController,CustomEvent:class {constructor(type,options){this.type=type;this.detail=options.detail;}},document:{addEventListener(name,handler){if(!events.has(name))events.set(name,[]);events.get(name).push(handler);},dispatchEvent(event){for(const handler of events.get(event.type)||[])handler(event);},getElementById:id=>n[id],querySelector:s=>n[s.slice(1)],createElement:t=>node('',t),body,get activeElement(){return active;}},
    window:{setTimeout(fn,ms){timers.set(++timer,{fn,ms});return timer;},clearTimeout(id){timers.delete(id);}},
    fetch:(url,options)=>{fetches.push({url,options});return impl(url,options);}});
  return {n,inputs,timers,fetches,get active(){return active;},setFetch:f=>{impl=f;},edit:()=>edit.handlers.click(),
    submit(){n['room-confirm'].checked=true;n['room-submit'].focus();return n['room-form'].handlers.submit({preventDefault(){}});},
    refresh(){n['rooms-refresh'].focus();return n['rooms-refresh'].handlers.click();}};
}
function restored(ui){for(const input of ui.inputs)assert.equal(input.disabled,false);assert.equal(ui.n['room-submit'].disabled,false);
  assert.equal(ui.n['room-form'].getAttribute('aria-busy'),undefined);assert.equal(ui.timers.size,0);}
for(const phase of ['headers','body'])test(`room ${phase} timeout restores input and offers manual verification without retry`,async()=>{
  const ui=harness();ui.setFetch(async(_url,{signal})=>{
    const stalled=()=>new Promise((_r,reject)=>signal.addEventListener('abort',()=>reject(new Error('aborted'))));
    return phase==='headers'?stalled():{ok:true,json:stalled};});
  const pending=ui.submit();await tick();assert.equal(ui.n['room-submit'].disabled,true);await ui.submit();assert.equal(ui.fetches.length,1);
  const timer=[...ui.timers.values()][0];assert.equal(timer.ms,20000);timer.fn();await pending;restored(ui);
  assert.match(ui.n['room-feedback'].textContent,/未能确认.*输入已保留.*不会自动重试/);assert.equal(ui.inputs[0].value,room.name);
  assert.equal(ui.active,ui.n['room-feedback']);assert.equal(ui.fetches.length,1);
});
for(const failure of ['network','bad-json','bad-room'])test(`room ${failure} is unknown and keeps complete draft`,async()=>{
  const ui=harness();ui.setFetch(async()=>{if(failure==='network')throw new Error();if(failure==='bad-json')return {ok:true,json:async()=>{throw new Error();}};return ok({...room,extra:'leak'});});
  await ui.submit();restored(ui);assert.match(ui.n['room-feedback'].textContent,/未能确认/);assert.equal(ui.inputs[0].value,room.name);assert.equal(ui.fetches.length,1);
});
test('field errors focus enabled input; retry creates then uses stable update ID',async()=>{
  const ui=harness();ui.setFetch(async()=>fail('INVALID_INPUT',{name:'名称过长'}));await ui.submit();restored(ui);
  assert.equal(ui.active,ui.inputs[0]);assert.equal(ui.n['room-name-error'].textContent,'名称过长');
  ui.setFetch(async url=>ok(url==='/api/rooms'?{items:[room],total:1}:room));await ui.submit();restored(ui);
  assert.equal(ui.inputs[0].getAttribute('aria-invalid'),undefined);assert.equal(ui.n['room-confirm'].checked,false);
  assert.equal(ui.n['room-cancel'].hidden,false);assert.match(ui.n['room-feedback'].textContent,/已保存/);
  await ui.submit();assert.equal(ui.fetches[3].url,'/api/admin/rooms/1');
  assert.equal(ui.n['admin-rooms'].querySelectorAll('img').length,0);assert.ok(ui.n['admin-rooms'].textContent.includes(room.name));
});
test('capacity conflict renders exact management facts as text and preserves all fields',async()=>{
  const ui=harness();ui.edit();ui.inputs[2].value='4';ui.setFetch(async()=>fail('CAPACITY_CONFLICT',{},[
    {id:102,attendees:5,start_local:'2026-11-12T10:00:00+08:00',end_local:'2026-11-12T11:00:00+08:00',status:'in_progress'}]));
  await ui.submit();restored(ui);assert.equal(ui.inputs[2].value,'4');assert.equal(ui.fetches[0].url,'/api/admin/rooms/1');
  assert.equal(ui.n['room-conflicts'].textContent,'预约 102 · 5 人 · 北京时间 2026-11-12 10:00:00 至 2026-11-12 11:00:00 · 进行中');
});
for(const code of ['ROOM_DUPLICATE','CSRF_REJECTED','INTERNAL_ERROR','NOT_FOUND'])test(`${code} rejection retains draft and permits deliberate retry`,async()=>{
  const ui=harness();ui.setFetch(async()=>fail(code));await ui.submit();restored(ui);assert.equal(ui.inputs[0].value,room.name);
  assert.match(ui.n['room-feedback'].textContent,/输入已保留/);assert.equal(ui.n['room-relogin'].hidden,code!=='CSRF_REJECTED');
});
for(const code of ['AUTH_REQUIRED','FORBIDDEN'])test(`${code} preserves draft, clears directory and blocks stale resubmission`,async()=>{
  const ui=harness();ui.setFetch(async()=>fail(code));await ui.submit();assert.equal(ui.n['room-relogin'].hidden,false);
  assert.equal(ui.n['admin-rooms'].children.length,0);assert.equal(ui.inputs[0].value,room.name);assert.equal(ui.n['room-submit'].disabled,true);
  await ui.submit();assert.equal(ui.fetches.length,1);assert.equal(ui.timers.size,0);
});
for(const success of [true,false])test(`room ${success?'success':'failure'} does not steal focus from logout during request`,async()=>{
  const ui=harness();let resolve;ui.setFetch(url=>url==='/api/rooms'?Promise.resolve(ok({items:[room],total:1})):new Promise(r=>{resolve=r;}));
  const pending=ui.submit();ui.n['logout-form'].focus();resolve(success?ok(room):fail('ROOM_DUPLICATE'));await pending;
  assert.equal(ui.active,ui.n['logout-form']);restored(ui);
});
test('successful save with directory refresh failure stays a success and retains normalized saved form',async()=>{
  const ui=harness();ui.setFetch(async url=>{if(url==='/api/rooms')throw new Error();return ok(room);});await ui.submit();restored(ui);
  assert.match(ui.n['room-feedback'].textContent,/已保存/);assert.match(ui.n['rooms-feedback'].textContent,/已保存.*刷新失败/);
  assert.equal(ui.n['room-form-title'].textContent,'编辑会议室 1');
});
test('explicit directory refresh preserves draft and cancel edit resets to create with heading focus',async()=>{
  const ui=harness();ui.edit();ui.inputs[0].value='draft';await ui.refresh();restored(ui);assert.equal(ui.inputs[0].value,'draft');
  assert.equal(ui.active,ui.n['rooms-refresh']);ui.n['room-cancel'].handlers.click();assert.equal(ui.inputs[0].value,'');
  assert.equal(ui.n['room-cancel'].hidden,true);assert.equal(ui.active,ui.n['room-form-title']);assert.equal(ui.n['room-confirm'].checked,false);
});

for(const [label,newline] of [['LF','\n'],['CR','\r'],['CRLF','\r\n']])test(`${label} raw name/location survive unchanged and capacity-only edits through textarea normalization`,async()=>{
  const original={...room,name:`上${newline}下`,location:`东${newline}西`};const ui=harness(original);ui.edit();
  assert.equal(ui.inputs[0].value,'上\n下');assert.equal(ui.inputs[1].value,'东\n西');
  let current=original;ui.setFetch(async(url,options)=>{if(url==='/api/rooms')return ok({items:[current],total:1});
    const values=JSON.parse(options.body);assert.equal(values.name,original.name);assert.equal(values.location,original.location);
    current={id:1,...values};return ok(current);});
  await ui.submit();assert.deepEqual(JSON.parse(ui.fetches[0].options.body),{name:original.name,location:original.location,capacity:20});
  ui.inputs[2].value='21';ui.inputs[2].handlers.input();await ui.submit();
  assert.deepEqual(JSON.parse(ui.fetches[2].options.body),{name:original.name,location:original.location,capacity:21});restored(ui);
});
for(const [text,number] of [['1e2',100],['10.0',10],['01',1],['1000',1000]])test(`numeric control ${text} produces integer JSON ${number}`,async()=>{
  const ui=harness();ui.inputs[2].value=text;await ui.submit();restored(ui);
  assert.equal(JSON.parse(ui.fetches[0].options.body).capacity,number);
});
for(const value of ['1.5','0','-1','1001','',' ','Infinity','NaN'])test(`invalid numeric control ${JSON.stringify(value)} is rejected before POST`,async()=>{
  const ui=harness();ui.inputs[2].value=value;await ui.submit();restored(ui);assert.equal(ui.fetches.length,0);
  assert.equal(ui.inputs[2].getAttribute('aria-invalid'),'true');assert.equal(ui.active,ui.inputs[2]);assert.equal(ui.inputs[2].value,value);
});
for(const code of ['AUTH_REQUIRED','FORBIDDEN'])for(const phase of ['manual','after-save'])test(`${phase} directory ${code} preserves identity guidance instead of disabled retry`,async()=>{
  const ui=harness();ui.setFetch(async url=>url==='/api/rooms'?fail(code):ok(room));
  if(phase==='manual')await ui.refresh();else await ui.submit();
  assert.match(ui.n['rooms-feedback'].textContent,code==='AUTH_REQUIRED'?/登录已失效.*重新登录/:/无管理权限.*管理员.*重新登录/);
  assert.doesNotMatch(ui.n['rooms-feedback'].textContent,/手动重试|手动刷新/);
  assert.equal(ui.n['admin-rooms'].children.length,0);assert.equal(ui.n['rooms-refresh'].disabled,true);
  assert.equal(ui.n['room-relogin'].hidden,false);assert.equal(ui.inputs[0].value,room.name);
  if(phase==='after-save')assert.match(ui.n['room-feedback'].textContent,/会议室资料已保存。.*重新登录/);
});
const validConflict={id:102,attendees:5,start_local:'2026-11-12T10:00:00+08:00',end_local:'2026-11-12T11:00:00+08:00',status:'in_progress'};
for(const [label,fields,conflicts] of [
  ['non-array conflicts',{},{}],['string conflicts',{},'private'],['missing timestamp',{},[{...validConflict,end_local:undefined}]],
  ['numeric timestamp',{},[{...validConflict,start_local:7}]],['null conflict',{},[null]],['object id',{},[{...validConflict,id:{private:1}}]],
  ['bad status',{},[{...validConflict,status:{private:1}}]],['array fields',[],[]],['null fields',null,[]],['non-text field',{name:{private:1}},[]]
])test(`malformed ${label} uses unknown-result recovery and restores draft`,async()=>{
  const ui=harness();ui.setFetch(async()=>fail('CAPACITY_CONFLICT',fields,conflicts));await ui.submit();restored(ui);
  assert.match(ui.n['room-feedback'].textContent,/未能确认.*输入已保留/);assert.equal(ui.inputs[0].value,room.name);
  assert.equal(ui.n['room-conflicts'].children.length,0);assert.equal(ui.fetches.length,1);
});
for(const field of ['name','location','capacity'])for(const event of ['input','change'])test(`${field} ${event} clears confirmation and prevents POST until reconfirmed`,async()=>{
  const ui=harness();ui.n['room-confirm'].checked=true;ui.n['room-'+field].handlers[event]();
  assert.equal(ui.n['room-confirm'].checked,false);await ui.n['room-form'].handlers.submit({preventDefault(){}});assert.equal(ui.fetches.length,0);
  await ui.submit();assert.equal(ui.fetches.filter(row=>row.options.method==='POST').length,1);restored(ui);
});
test('STORE_BUSY keeps draft and restores controls; only deliberate retry saves',async()=>{
  const ui=harness();ui.edit();ui.setFetch(async()=>fail('STORE_BUSY'));await ui.submit();restored(ui);
  assert.equal(ui.inputs[0].value,room.name);assert.match(ui.n['room-feedback'].textContent,/输入已保留/);assert.equal(ui.fetches.length,1);
  ui.setFetch(async url=>ok(url==='/api/rooms'?{items:[room],total:1}:room));await ui.submit();restored(ui);
  assert.equal(ui.fetches.filter(row=>row.options.method==='POST').length,2);assert.match(ui.n['room-feedback'].textContent,/已保存/);
});
