const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const event={id:1,actor_id:3,actor_display_name:'<img src=x onerror="evil()">',action:'room.created',target_type:'room',target_id:1,occurred_at:1,occurred_local:'2026-11-12T08:00:00+08:00',before:null,after:{id:1,name:'<script>text</script>',location:'L',capacity:20},reason:null};
const ok=(items=[event])=>({ok:true,json:async()=>({ok:true,data:{items,total:items.length}})});
const fail=code=>({ok:false,json:async()=>({ok:false,error:{code,message:'secret',fields:{},conflicts:[]}})});
const productionSource=fs.readFileSync(path.join(__dirname,'../booking_app/static/audit.js'),'utf8');
function harness(source=productionSource){
  let impl=async()=>ok(),timer=0;const timers=new Map(),fetches=[],events=new Map();
  function node(tag=''){let text='';return {tag,children:[],handlers:{},attrs:{},value:'',name:'',hidden:false,disabled:false,classList:{toggle(){}},
    get textContent(){return text+this.children.map(c=>c.textContent).join('');},set textContent(v){text=String(v);this.children=[];},
    set innerHTML(_){throw Error('Unsafe HTML');},append(...n){this.children.push(...n);},replaceChildren(){this.children=[];text='';},
    addEventListener(k,f){this.handlers[k]=f;},setAttribute(k,v){this.attrs[k]=v;},removeAttribute(k){delete this.attrs[k];}};}
  const n=Object.fromEntries(['audit-form','audit-items','audit-results','audit-feedback','audit-relogin','audit-submit','audit-target_type','audit-date'].map(id=>[id,node()]));
  n['audit-target_type'].name='target_type';n['audit-date'].name='date';
  function dispatch(event){for(const fn of events.get(event.type)||[])fn(event);}
  vm.runInNewContext(source,{AbortController,URLSearchParams,
    CustomEvent:class{constructor(type,{detail}){this.type=type;this.detail=detail;}},
    document:{getElementById:id=>n[id],createElement:node,addEventListener(k,f){if(!events.has(k))events.set(k,[]);events.get(k).push(f);},dispatchEvent:dispatch},
    window:{setTimeout(fn,ms){timers.set(++timer,{fn,ms});return timer;},clearTimeout(i){timers.delete(i);}},
    fetch:(url,options)=>{fetches.push({url,options});return impl(url,options);}});
  return {n,timers,fetches,setFetch:f=>{impl=f;},submit:()=>n['audit-form'].handlers.submit({preventDefault(){}}),lost:code=>dispatch({type:'admin-auth-lost',detail:{code}})};
}
function restored(ui){assert.equal(ui.n['audit-submit'].disabled,false);assert.equal(ui.n['audit-form'].attrs['aria-busy'],undefined);assert.equal(ui.timers.size,0);}
test('audit actual handler sends optional filters, renders exact facts as plain text and empty state',async()=>{
  const ui=harness();ui.n['audit-target_type'].value='room';ui.n['audit-date'].value='2026-11-12';await ui.submit();restored(ui);
  assert.equal(ui.fetches[0].url,'/api/admin/audit?target_type=room&date=2026-11-12');assert.equal(ui.n['audit-items'].children.length,1);
  assert.match(ui.n['audit-items'].textContent,/<img src=x/);assert.match(ui.n['audit-items'].textContent,/<script>text/);assert.match(ui.n['audit-items'].textContent,/无（创建前）/);
  ui.setFetch(async()=>ok([]));await ui.submit();restored(ui);assert.equal(ui.n['audit-results'].hidden,true);assert.match(ui.n['audit-feedback'].textContent,/没有符合/);
});
for(const phase of ['headers','body'])test(`audit ${phase} timeout unlocks retained filters without auto retry`,async()=>{
  const ui=harness();ui.n['audit-date'].value='2026-11-12';ui.setFetch(async(_,{signal})=>{const stall=()=>new Promise((_,reject)=>signal.addEventListener('abort',()=>reject(Error())));return phase==='headers'?stall():{ok:true,json:stall};});
  const pending=ui.submit();await new Promise(setImmediate);assert.equal(ui.n['audit-submit'].disabled,true);await ui.submit();assert.equal(ui.fetches.length,1);
  [...ui.timers.values()][0].fn();await pending;restored(ui);assert.equal(ui.n['audit-date'].value,'2026-11-12');assert.match(ui.n['audit-feedback'].textContent,/手动重试/);
  ui.setFetch(async()=>ok());await ui.submit();restored(ui);assert.equal(ui.n['audit-items'].children.length,1);
});
for(const code of ['INTERNAL_ERROR','INVALID_INPUT','STORE_BUSY'])test(`audit ${code} safely recovers`,async()=>{
  const ui=harness();ui.setFetch(async()=>fail(code));await ui.submit();restored(ui);assert.doesNotMatch(ui.n['audit-feedback'].textContent,/secret/);
  ui.setFetch(async()=>ok());await ui.submit();restored(ui);assert.match(ui.n['audit-feedback'].textContent,/1 条/);
});
for(const code of ['AUTH_REQUIRED','FORBIDDEN'])test(`audit ${code} clears loaded facts and disables stale requests`,async()=>{
  const ui=harness();await ui.submit();ui.setFetch(async()=>fail(code));await ui.submit();assert.equal(ui.n['audit-items'].children.length,0);
  assert.equal(ui.n['audit-relogin'].hidden,false);assert.equal(ui.n['audit-submit'].disabled,true);await ui.submit();assert.equal(ui.fetches.length,2);
});
for(const malformed of [{...event,extra:'secret'},{...event,before:'{}'},{...event,after:{password:'secret'}},{...event,reason:{}},{...event,action:'unknown'}])test('audit malformed DTO never renders partial facts',async()=>{
  const ui=harness();ui.setFetch(async()=>ok([event,malformed]));await ui.submit();restored(ui);assert.equal(ui.n['audit-items'].children.length,0);assert.match(ui.n['audit-feedback'].textContent,/未能读取/);
});
test('external auth-loss event invalidates late successful response',async()=>{
  const ui=harness();let release;ui.setFetch(()=>new Promise(resolve=>{release=resolve;}));const pending=ui.submit();ui.lost('FORBIDDEN');release(ok());await pending;
  assert.equal(ui.n['audit-items'].children.length,0);assert.equal(ui.n['audit-submit'].disabled,true);assert.match(ui.n['audit-feedback'].textContent,/无管理权限/);assert.equal(ui.timers.size,0);
});

const update={...event,id:2,action:'room.updated',before:{...event.after,name:'old room',capacity:10},after:{...event.after,name:'new room',capacity:20}};
const bookingBefore={id:12,room_id:1,owner_id:7,title:'distinct title',purpose:'distinct purpose',attendees:3,start_at:1800,end_at:3600,created_at:1,cancelled_at:null,cancelled_by_id:null,cancel_reason:null};
const cancellation={...event,id:3,action:'booking.cancelled_by_admin',target_type:'booking',target_id:12,before:bookingBefore,
  after:{...bookingBefore,cancelled_at:2,cancelled_by_id:3,cancel_reason:'管理员原因 <img src=x>'},reason:'管理员原因 <img src=x>'};
const blockBefore={id:13,room_id:1,creator_id:3,reason:'maintenance',start_at:1800,end_at:3600,created_at:1,revoked_at:null,revoked_by_id:null,revoke_reason:null};
const revocation={...event,id:4,action:'block.revoked',target_type:'block',target_id:13,before:blockBefore,
  after:{...blockBefore,revoked_at:2,revoked_by_id:3,revoke_reason:'撤销原因'+'长'.repeat(100)},reason:'撤销原因'+'长'.repeat(100)};
const displayedFixtures=[update,cancellation,revocation];
function cellContent(cell){const details=cell.children.find(child=>child.tag==='details');return details?details.children.find(child=>child.tag==='pre').textContent:cell.textContent;}
function assertDisplayed(ui,items){
  const rows=ui.n['audit-items'].children;assert.equal(rows.length,items.length);
  const labels={'room.updated':'修改会议室','booking.cancelled_by_admin':'管理员取消预约','block.revoked':'撤销停用'};
  for(let index=0;index<items.length;index++){
    const item=items[index],cells=rows[index].children;assert.equal(cells.length,6);
    assert.equal(cellContent(cells[0]),`#${item.id} · 2026-11-12 08:00:00`);
    assert.equal(cellContent(cells[1]),'<img src=x onerror="evil()">（3）');
    assert.equal(cellContent(cells[2]),`${labels[item.action]} · ${item.action}\n${item.target_type} #${item.target_id}`);
    assert.deepEqual(JSON.parse(cellContent(cells[3])),item.before);
    assert.deepEqual(JSON.parse(cellContent(cells[4])),item.after);
    assert.equal(cellContent(cells[5]),item.reason===null?'无':item.reason);
  }
}
test('audit distinct update cancellation revocation bind every full field to its own cell',async()=>{
  const ui=harness();ui.setFetch(async()=>ok(displayedFixtures));await ui.submit();restored(ui);assertDisplayed(ui,displayedFixtures);
  assert.equal(cellContent(ui.n['audit-items'].children[1].children[5]),'管理员原因 <img src=x>');
});
for(const [name,from,to] of [
  ['before cell incorrectly bound to after','JSON.stringify(item.before,null,2)','JSON.stringify(item.after,null,2)'],
  ['non-null reason discarded','cell(row,item.reason === null ? "无" : item.reason,item.reason !== null && item.reason.length > 80);','cell(row,"无");']
])test(`display oracle rejects mutation: ${name}`,async()=>{
  assert.ok(productionSource.includes(from));const ui=harness(productionSource.replace(from,to));ui.setFetch(async()=>ok(displayedFixtures));await ui.submit();
  assert.throws(()=>assertDisplayed(ui,displayedFixtures),assert.AssertionError);
});
for(const [name,malformed] of [
  ['nested name',{...event,after:{...event.after,name:{password:'secret'}}}],
  ['string capacity',{...event,after:{...event.after,capacity:'20'}}],
  ['boolean capacity',{...event,after:{...event.after,capacity:true}}],
  ['null required text',{...event,after:{...event.after,name:null}}],
  ['object previous name',{...update,before:{...update.before,name:{password:'secret'}}}],
  ['string cancelled time',{...cancellation,after:{...cancellation.after,cancelled_at:'2'}}],
  ['object nullable reason',{...cancellation,before:{...cancellation.before,cancel_reason:{password:'secret'}}}],
  ['boolean revoked actor',{...revocation,after:{...revocation.after,revoked_by_id:false}}],
  ['numeric revoke reason',{...revocation,after:{...revocation.after,revoke_reason:7}}]
])test(`audit malformed snapshot ${name} cannot render evidence`,async()=>{
  const ui=harness();ui.setFetch(async()=>ok([event,malformed]));await ui.submit();restored(ui);
  assert.equal(ui.n['audit-items'].children.length,0);assert.match(ui.n['audit-feedback'].textContent,/未能读取/);
});
for(const field of ['target_type','date'])for(const eventName of ['input','change'])test(`${field} ${eventName} invalidates results and requests deliberate query`,async()=>{
  const ui=harness();await ui.submit();ui.n['audit-'+field].value=field==='date'?'2026-11-13':'booking';
  ui.n['audit-'+field].handlers[eventName]();restored(ui);assert.equal(ui.n['audit-results'].hidden,true);assert.equal(ui.n['audit-items'].children.length,0);
  assert.match(ui.n['audit-feedback'].textContent,/筛选条件已修改.*重新查询/);assert.equal(ui.fetches.length,1);
  assert.equal(ui.n['audit-'+field].value,field==='date'?'2026-11-13':'booking');
  await ui.submit();assert.equal(ui.fetches.length,2);assert.match(ui.fetches[1].url,new RegExp(field+'='));
});
test('filter invalidation prevents a late old response restoring rows',async()=>{
  const ui=harness();let release;ui.setFetch(()=>new Promise(resolve=>{release=resolve;}));const pending=ui.submit();
  ui.n['audit-date'].value='2026-11-13';ui.n['audit-date'].handlers.input();release(ok());await pending;restored(ui);
  assert.equal(ui.n['audit-items'].children.length,0);assert.match(ui.n['audit-feedback'].textContent,/重新查询/);
});
for(const field of ['id','actor_id','target_id','occurred_at'])test(`unsafe audit event ${field} rejects all rows and preserves filters`,async()=>{
  const ui=harness();ui.n['audit-target_type'].value='room';ui.n['audit-date'].value='2026-11-12';
  ui.setFetch(async()=>ok([event,{...event,[field]:Number('9007199254740993')}]));await ui.submit();restored(ui);
  assert.equal(ui.n['audit-items'].children.length,0);assert.equal(ui.n['audit-results'].hidden,true);assert.match(ui.n['audit-feedback'].textContent,/未能读取.*条件已保留/);
  assert.equal(ui.n['audit-target_type'].value,'room');assert.equal(ui.n['audit-date'].value,'2026-11-12');
  ui.setFetch(async()=>ok());await ui.submit();assert.equal(ui.n['audit-items'].children.length,1);
});
for(const fixture of displayedFixtures)for(const side of ['before','after'])for(const field of Object.keys(fixture[side]).filter(k=>typeof fixture[side][k]==='number'||k.endsWith('_at')||k.endsWith('_id')))test(`unsafe ${fixture.target_type} ${side}.${field} snapshot cannot display rounded evidence`,async()=>{
  const ui=harness();ui.n['audit-date'].value='2026-11-12';
  const malformed={...fixture,[side]:{...fixture[side],[field]:Number('9223372036854775807')}};
  ui.setFetch(async()=>ok([event,malformed]));await ui.submit();restored(ui);
  assert.equal(ui.n['audit-items'].children.length,0);assert.match(ui.n['audit-feedback'].textContent,/未能读取.*条件已保留/);assert.equal(ui.n['audit-date'].value,'2026-11-12');
});


const applicationSnapshot={id:21,owner_id:7,owner_display_name:'学生 <img>',supervisor_id:3,supervisor_display_name:'导师',room_id:1,title:'审批讨论',purpose:'完整用途',attendees:4,start_at:1800,end_at:3600,weeks:1,status:'awaiting_approval',created_at:100,decided_at:null,decided_by:null,decision_reason:null};
const applicationEvents=['created','approved','rejected','withdrawn'].map((action,index)=>({...event,id:21+index,action:`application.${action}`,target_type:'application',target_id:21,
  before:action==='created'?null:applicationSnapshot,
  after:action==='created'?applicationSnapshot:{...applicationSnapshot,status:action,decided_at:200,decided_by:action==='withdrawn'?7:3,decision_reason:action==='rejected'?'拒绝原因 <script>':null},
  reason:action==='rejected'?'拒绝原因 <script>':null}));
test('application created approved rejected withdrawn audit events render exact full snapshots and reasons',async()=>{
  const ui=harness();ui.setFetch(async()=>ok(applicationEvents));await ui.submit();restored(ui);
  const rows=ui.n['audit-items'].children;assert.equal(rows.length,4);
  const labels=['提交申请','批准申请','拒绝申请','撤回申请'];
  applicationEvents.forEach((item,index)=>{
    const cells=rows[index].children;assert.equal(cells.length,6);
    assert.equal(cellContent(cells[2]),`${labels[index]} · ${item.action}\napplication #21`);
    if(item.before===null)assert.equal(cellContent(cells[3]),'无（创建前）');else assert.deepEqual(JSON.parse(cellContent(cells[3])),item.before);
    assert.deepEqual(JSON.parse(cellContent(cells[4])),item.after);assert.equal(cellContent(cells[5]),item.reason??'无');
  });
  assert.match(ui.n['audit-items'].textContent,/学生 <img>/);assert.match(ui.n['audit-items'].textContent,/拒绝原因 <script>/);
});
