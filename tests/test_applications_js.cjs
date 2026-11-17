const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const app={id:1,owner_id:2,owner_display_name:'学生',supervisor_id:3,supervisor_display_name:'导师 <img>',room_id:1,title:'讨论 <img src=x>',purpose:'私有用途',attendees:3,start_at:1794531600,end_at:1794535200,weeks:1,status:'awaiting_approval',created_at:1794448800,decided_at:null,decided_by:null,decision_reason:null,room:{id:1,name:'讨论室',location:'科研楼',capacity:12},start_local:'2026-11-13T09:00:00+08:00',end_local:'2026-11-13T10:00:00+08:00',expired:false,reservation_id:null};
const body=value=>({ok:true,status:200,json:async()=>({ok:true,data:value})});
const flush=async()=>{for(let i=0;i<8;i++)await new Promise(resolve=>setImmediate(resolve));};
function harness(role='teacher',fetcher) {
  let active;const requests=[],nodes={};
  function node(tag,id='') {const attrs=new Map(),listeners={};const n={tag,id,children:[],hidden:false,disabled:false,value:'',_text:'',
    get textContent(){return this._text+this.children.map(c=>c.textContent).join('');},set textContent(v){this._text=String(v);this.children=[];},
    setAttribute(k,v){attrs.set(k,String(v));},getAttribute:k=>attrs.get(k),classList:{toggle(){}},
    append(c){this.children.push(c);},replaceChildren(){this.children=[];},focus(){active=this;},
    addEventListener(k,cb){listeners[k]=cb;},click(){return listeners.click?.({preventDefault(){}});},change(){return listeners.change?.();},
    querySelectorAll(selector){const tags=selector.split(',');return this.children.flatMap(c=>[...(tags.includes(c.tag)?[c]:[]),...c.querySelectorAll(selector)]);}};if(id)nodes[id]=n;return n;}
  const panel=node('section','applications-panel');for(const [id,tag] of [['applications-items','ul'],['applications-feedback','p'],['applications-refresh','button'],['applications-retry','button'],['applications-relogin','a']])panel.append(node(tag,id));
  for(const id of ['applications-status','applications-room','applications-date'])panel.append(node(id==='applications-date'?'input':'select',id));
  const docBody=node('body');docBody.setAttribute('data-role',role);docBody.setAttribute('data-user-id',role==='member'?'2':role==='teacher'?'3':'4');
  nodes['logout-form']={elements:{csrf_token:{value:'test-csrf'}}};let implementation=fetcher||(()=>body({items:[app],total:1}));
  const window={setTimeout:()=>1,clearTimeout(){}};
  const context=vm.createContext({window,document:{body:docBody,getElementById:id=>nodes[id],createElement:tag=>node(tag)},AbortController,
    fetch:async(url,options)=>{requests.push({url,options});return implementation(url,options);}});
  for(const script of ['contracts.js','applications.js'])vm.runInContext(fs.readFileSync(path.join(__dirname,'../booking_app/static',script),'utf8'),context);
  return {nodes,requests,window,get active(){return active;},setFetch(fn){implementation=fn;},buttons:()=>nodes['applications-items'].querySelectorAll('button')};
}
test('strict application contract rejects private identity injection and incorrect decisions',async()=>{
  const h=harness();await flush();assert.equal(h.window.BookingContracts.application(app),true);
  for(const value of [{...app,session_token:'leak'},{...app,weeks:2},{...app,status:'approved'},{...app,supervisor_id:null},{...app,start_local:'2026-11-13T10:00:00+08:00'}])assert.equal(h.window.BookingContracts.application(value),false);
  assert.match(h.nodes['applications-items'].textContent,/讨论 <img src=x>/);assert.equal(h.nodes['applications-items'].querySelectorAll('img').length,0);
});
test('student can withdraw and admin only sees records',async()=>{
  const student=harness('member');const admin=harness('admin');await flush();
  assert.deepEqual(student.buttons().map(n=>n.textContent),['撤回本人申请']);assert.deepEqual(admin.buttons(),[]);
});
test('unknown approval retries same operation and then updates record',async()=>{
  const h=harness();await flush();h.setFetch(()=>{throw Error('lost committed response');});h.buttons().find(n=>n.textContent==='批准申请').click();await flush();
  assert.equal(h.nodes['applications-retry'].hidden,false);assert.match(h.nodes['applications-feedback'].textContent,/结果未知/);
  const approved={...app,status:'approved',decided_at:1794448900,decided_by:3,reservation_id:7};
  h.setFetch((url,options)=>body(options.method?approved:{items:[approved],total:1}));h.nodes['applications-retry'].click();await flush();
  const writes=h.requests.filter(r=>r.options.method==='POST');assert.equal(writes.length,2);assert.equal(writes[0].url,writes[1].url);assert.equal(writes[0].options.body,writes[1].options.body);
  assert.match(h.nodes['applications-items'].textContent,/已批准/);assert.equal(h.nodes['applications-retry'].hidden,true);
});
test('rejection validates reason and sends safe plain text',async()=>{
  const h=harness();await flush();const button=h.buttons().find(n=>n.textContent==='拒绝申请');button.click();await flush();
  assert.match(h.nodes['applications-feedback'].textContent,/填写/);assert.equal(h.requests.length,1);
  const reason=h.nodes['applications-items'].querySelectorAll('textarea')[0];reason.value='  原因 <script>  ';
  const rejected={...app,status:'rejected',decided_at:1794448900,decided_by:3,decision_reason:'原因 <script>'};
  h.setFetch((url,options)=>body(options.method?rejected:{items:[rejected],total:1}));button.click();await flush();
  assert.equal(h.requests[1].url,'/api/applications/1/reject');
  assert.deepEqual(JSON.parse(h.requests[1].options.body),{reason:'  原因 <script>  '});
  assert.match(h.nodes['applications-items'].textContent,/已拒绝/);assert.match(h.nodes['applications-items'].textContent,/原因 <script>/);assert.deepEqual(h.buttons(),[]);
});
test('401 clears private details and reveals relogin',async()=>{
  const h=harness();await flush();h.setFetch(()=>({ok:false,status:401,json:async()=>({ok:false,error:{code:'AUTH_REQUIRED',message:'登录过期'}})}));
  h.nodes['applications-refresh'].click();await flush();assert.equal(h.nodes['applications-items'].children.length,0);assert.equal(h.nodes['applications-relogin'].hidden,false);assert.match(h.nodes['applications-feedback'].textContent,/已清空/);
});
test('expired awaiting application has no approval button',async()=>{
  const h=harness('teacher',()=>body({items:[{...app,expired:true}],total:1}));await flush();assert.deepEqual(h.buttons().map(n=>n.textContent),['拒绝申请']);
});

const approvedApp={...app,status:'approved',decided_at:1794448900,decided_by:3,reservation_id:7};
test('pending applications lead and status, room and date filters narrow the list',async()=>{
  const processed={...approvedApp,id:2,room_id:2,room:{...app.room,id:2,name:'第二间'}};
  const h=harness('teacher',()=>body({items:[processed,{...app,id:1},{...app,id:3}],total:3}));await flush();
  const headings=()=>h.nodes['applications-items'].children.map(row=>row.children.find(child=>child.tag==='h2')?.textContent);
  assert.deepEqual(headings(),['申请 #3 · 讨论 <img src=x>','申请 #1 · 讨论 <img src=x>','申请 #2 · 讨论 <img src=x>']);
  h.nodes['applications-status'].value='processed';h.nodes['applications-status'].change();assert.equal(h.nodes['applications-items'].children.length,1);
  h.nodes['applications-status'].value='';h.nodes['applications-room'].value='2';h.nodes['applications-room'].change();assert.equal(h.nodes['applications-items'].children.length,1);
  h.nodes['applications-date'].value='2026-11-14';h.nodes['applications-date'].change();assert.equal(h.nodes['applications-items'].children.length,0);
});
const approvedBooking={id:7,owner_id:2,owner_display_name:'学生',supervisor_id:3,supervisor_display_name:'导师 <img>',supervisor_source:'application',application_id:1,approved_at:1794448900,approved_by:3,
  room:app.room,title:app.title,purpose:app.purpose,attendees:3,start_at:app.start_at,end_at:app.end_at,start_local:app.start_local,end_local:app.end_local,status:'pending',created_at:1794448900,created_local:'2026-11-12T10:01:40+08:00',cancelled_at:null,cancelled_local:null,cancelled_by_id:null,cancelled_by_display_name:null,cancel_reason:null};
const failure=(code,status=409)=>({ok:false,status,json:async()=>({ok:false,error:{code,message:code,fields:{},conflicts:[]}})});
test('strict booking origins require all four source relationships',async()=>{
  const h=harness();await flush();const check=h.window.BookingContracts.booking;
  const noApproval={application_id:null,approved_at:null,approved_by:null};
  const teacher={...approvedBooking,...noApproval,owner_id:3,supervisor_source:'teacher'};
  const admin={...approvedBooking,...noApproval,supervisor_source:'admin',supervisor_id:null,supervisor_display_name:null};
  const legacy={...admin,supervisor_source:'legacy'};
  for(const valid of [approvedBooking,teacher,admin,legacy])assert.equal(check(valid),true,valid.supervisor_source);
  for(const [base,overrides] of [
    [approvedBooking,{supervisor_id:null}],[approvedBooking,{supervisor_display_name:null}],[approvedBooking,{application_id:null}],
    [approvedBooking,{approved_at:null}],[approvedBooking,{approved_by:null}],[approvedBooking,{approved_by:9}],[approvedBooking,{owner_id:3}],
    [teacher,{supervisor_id:2}],[teacher,{supervisor_id:null}],[teacher,{application_id:1}],[teacher,{approved_at:1794448900}],
    [admin,{supervisor_id:3}],[admin,{supervisor_display_name:'伪导师'}],[admin,{approved_by:3}],
    [legacy,{supervisor_id:3}],[legacy,{supervisor_display_name:'猜测导师'}],[legacy,{application_id:1}],
  ])assert.equal(check({...base,...overrides}),false,JSON.stringify(overrides));
});
test('withdrawal sends exact URL and payload and renders terminal status',async()=>{
  const h=harness('member');await flush();const withdrawn={...app,status:'withdrawn',decided_at:1794448900,decided_by:2};
  h.setFetch((_url,options)=>body(options.method?withdrawn:{items:[withdrawn],total:1}));
  h.buttons()[0].click();await flush();const write=h.requests.find(r=>r.options.method==='POST');
  assert.equal(write.url,'/api/applications/1/withdraw');assert.equal(write.options.body,'{}');
  assert.match(h.nodes['applications-items'].textContent,/已撤回/);assert.deepEqual(h.buttons(),[]);
});
test('recognized transition failure refreshes a competing decision without stale buttons',async()=>{
  const h=harness();await flush();const withdrawn={...app,status:'withdrawn',decided_at:1794448900,decided_by:2};
  h.setFetch((_url,options)=>options.method?failure('TRANSITION_CLOSED'):body({items:[withdrawn],total:1}));
  h.buttons().find(n=>n.textContent==='批准申请').click();await flush();
  assert.match(h.nodes['applications-items'].textContent,/已撤回/);assert.deepEqual(h.buttons(),[]);
  assert.doesNotMatch(h.nodes['applications-feedback'].textContent,/保持原样/);
});
test('recognized conflict with failed read clears stale actions and does not claim unchanged facts',async()=>{
  const h=harness();await flush();h.setFetch((_url,options)=>{if(options.method)return failure('OCCUPANCY_CONFLICT');throw Error('read failed');});
  h.buttons().find(n=>n.textContent==='批准申请').click();await flush();
  assert.deepEqual(h.buttons(),[]);assert.equal(h.nodes['applications-items'].children.length,0);
  assert.match(h.nodes['applications-feedback'].textContent,/OCCUPANCY_CONFLICT.*列表刷新失败/);assert.doesNotMatch(h.nodes['applications-feedback'].textContent,/保持原样/);
});
test('confirmed transition remains visible when subsequent list refresh fails',async()=>{
  const h=harness();await flush();h.setFetch((_url,options)=>{if(options.method)return body(approvedApp);throw Error('read failed');});
  h.buttons().find(n=>n.textContent==='批准申请').click();await flush();
  assert.match(h.nodes['applications-feedback'].textContent,/申请 #1：已批准.*列表刷新失败/);
  assert.match(h.nodes['applications-items'].textContent,/已批准/);assert.equal(h.buttons().some(n=>n.textContent==='批准申请'),false);
});
test('detail reads replace old paragraphs and failed reads clear stale details',async()=>{
  const h=harness('teacher',()=>body({items:[approvedApp],total:1}));await flush();
  const button=h.buttons().find(n=>n.textContent==='查看生效预约详情');
  h.setFetch(()=>body(approvedBooking));button.click();await flush();
  assert.equal((h.nodes['applications-items'].textContent.match(/预约 #7/g)||[]).length,1);
  h.setFetch(()=>body({...approvedBooking,status:'ended'}));button.click();await flush();
  assert.equal((h.nodes['applications-items'].textContent.match(/预约 #7/g)||[]).length,1);
  assert.doesNotMatch(h.nodes['applications-items'].textContent,/pending/);assert.match(h.nodes['applications-items'].textContent,/ended/);
  h.setFetch(()=>{throw Error('failed detail');});button.click();await flush();
  assert.doesNotMatch(h.nodes['applications-items'].textContent,/预约 #7/);
});
test('CSRF rejection clears facts and disables stale-token actions until page reload',async()=>{
  const h=harness();await flush();const old=h.buttons().find(n=>n.textContent==='批准申请');h.setFetch(()=>failure('CSRF_REJECTED',403));
  old.click();await flush();assert.equal(h.nodes['applications-items'].children.length,0);assert.equal(h.nodes['applications-relogin'].hidden,false);
  assert.equal(h.nodes['applications-refresh'].disabled,true);assert.equal(h.nodes['applications-retry'].disabled,true);
  assert.match(h.nodes['applications-feedback'].textContent,/页面验证已失效/);
  const count=h.requests.length;old.click();h.nodes['applications-refresh'].click();h.nodes['applications-retry'].click();await flush();assert.equal(h.requests.length,count);
});
