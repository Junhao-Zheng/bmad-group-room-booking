(() => {
  "use strict";
  const find = id => document.getElementById(id), list=find("applications-items");
  if (!list) return;
  const panel=find("applications-panel"), feedback=find("applications-feedback"), refresh=find("applications-refresh"),
    retry=find("applications-retry"), relogin=find("applications-relogin");
  const role=document.body.getAttribute("data-role"), userId=Number(document.body.getAttribute("data-user-id"));
  const csrf=find("logout-form").elements.csrf_token.value;
  const labels={awaiting_approval:"待本人导师审批（尚未占用）",approved:"已批准",rejected:"已拒绝",withdrawn:"已撤回"};
  let busy=false, blocked=false, pendingOperation=null, displayedItems=[], allItems=[];
  const appStatus=find("applications-status"), appRoom=find("applications-room"), appDate=find("applications-date");
  function fillRooms(select, items, idKey, nameKey) {
    if(!select)return;
    const selected=select.value;select.replaceChildren();
    const all=document.createElement("option");all.value="";all.textContent="全部会议室";select.append(all);
    const seen=new Set();
    for(const item of items){const id=String(idKey(item));if(seen.has(id))continue;seen.add(id);
      const option=document.createElement("option");option.value=id;option.textContent=nameKey(item);select.append(option);}
    select.value=selected;
  }
  function showApplications() {
    if(blocked){list.replaceChildren();return;}
    const visible=allItems.filter(item=>(!appStatus?.value||(appStatus.value==="processed"?item.status!=="awaiting_approval":item.status===appStatus.value))
      &&(!appRoom?.value||String(item.room.id)===appRoom.value)
      &&(!appDate?.value||item.start_local.slice(0,10)===appDate.value));
    render(visible);say(`显示 ${visible.length} / ${allItems.length} 条申请；待审批排在前面。`);
  }
  for(const filter of [appStatus,appRoom,appDate])filter?.addEventListener("change",showApplications);
  const text=(parent,tag,value) => {const node=document.createElement(tag); node.textContent=value; parent.append(node); return node;};
  const local=value => value.replace("T"," ").replace("+08:00","");
  function say(message,error=false) {feedback.textContent=message; feedback.setAttribute("role",error?"alert":"status");feedback.classList.toggle("error",error);feedback.focus();}
  function lock(value) {busy=value;panel.setAttribute("aria-busy",String(value)); for(const node of panel.querySelectorAll("button,textarea")) node.disabled=value||blocked;}
  async function request(url,operation) {
    const controller=new AbortController(), timer=window.setTimeout(()=>controller.abort(),20000);
    try {
      const response=await fetch(url,{credentials:"same-origin",signal:controller.signal,...(operation?{
        method:"POST",headers:{"Content-Type":"application/json","X-CSRF-Token":csrf},body:JSON.stringify(operation.payload)}:{headers:{Accept:"application/json"}})});
      const body=await response.json();
      if (!response.ok) {
        if (!body || body.ok!==false || !body.error || typeof body.error.code!=="string" || typeof body.error.message!=="string") throw Error("Unknown response");
        throw Object.assign(Error(body.error.message),{api:true,code:body.error.code,conflicts:body.error.conflicts});
      }
      if (!body || Object.keys(body).sort().join(",")!=="data,ok" || body.ok!==true) throw Error("Unknown response");
      return body.data;
    } finally {window.clearTimeout(timer);}
  }
  function identityLost(error,prefix="") {
    if(!["AUTH_REQUIRED","CSRF_REJECTED"].includes(error.code))return false;
    blocked=true;allItems=[];displayedItems=[];
    list.replaceChildren();cancellationItems?.replaceChildren(); relogin.hidden=false; retry.hidden=true; pendingOperation=null;
    say(prefix+(error.code==="CSRF_REJECTED"?"页面验证已失效，操作已停用。请重新登录后打开本页。":"登录已失效，申请详情已清空。请重新登录后查看。"),true);return true;
  }
  function render(items) {
    displayedItems=items;
    list.replaceChildren();
    for(const item of items) {
      const row=text(list,"li",""); row.setAttribute("data-application-id",String(item.id));
      text(row,"h2",`申请 #${item.id} · ${item.title}`);
      text(row,"p",labels[item.status]+(item.expired?" · 已过开始时间，不能批准":""));
      text(row,"p",`${item.room.name} · ${item.room.location} · ${item.attendees} 人`);
      text(row,"p",`${local(item.start_local)} — ${local(item.end_local)}`);
      if(item.occurrences)for(const occurrence of item.occurrences) {
        text(row,"p",`第 ${occurrence.occurrence} 周 · ${local(occurrence.start_local)} — ${local(occurrence.end_local)} · ${occurrence.reservation_id===null?"尚未占用":`预约 #${occurrence.reservation_id}（${occurrence.status}）`}`);
      }
      text(row,"p",`申请人：${item.owner_display_name} · 本人导师：${item.supervisor_display_name}`);
      text(row,"p",`用途：${item.purpose}`);
      if(item.decided_at!==null) text(row,"p",`处理时间：${new Date(item.decided_at*1000).toLocaleString("zh-CN",{timeZone:"Asia/Shanghai"})} · 处理人编号 ${item.decided_by}`);
      if(item.decision_reason!==null) text(row,"p",`拒绝原因：${item.decision_reason}`);
      if(item.reservation_id!==null && !item.occurrences) text(row,"p",`生效预约编号：${item.reservation_id}；学生可在“我的预约”查看，导师可查看下方预约详情。`);
      for(const bookingId of item.occurrences ? item.occurrences.map(value=>value.reservation_id).filter(Boolean) : item.reservation_id!==null?[item.reservation_id]:[]) {
        const detail=text(row,"button",item.occurrences?`查看第 ${item.occurrences.find(value=>value.reservation_id===bookingId).occurrence} 周预约详情`:"查看生效预约详情"); detail.type="button";
        const detailResult=text(row,"p",""); detailResult.hidden=true;
        detail.addEventListener("click",async()=>{
          if(busy||blocked)return;detailResult.textContent="";detailResult.hidden=true;lock(true);say("正在读取预约详情…");
          try{const booking=await request(`/api/bookings/${bookingId}`);if(!window.BookingContracts.booking(booking)||booking.id!==bookingId||booking.application_id!==item.id)throw Error("Invalid booking");
            detailResult.textContent=`预约 #${booking.id} · ${booking.title} · ${booking.purpose} · ${booking.status} · 审批申请 #${booking.application_id}`;detailResult.hidden=false;say("已读取生效预约详情。");
          }catch(error){if(!identityLost(error))say(error.api?error.message:"未能读取预约详情，请重试。",true);}finally{lock(false);}
        });
      }
      if(item.status!=="awaiting_approval")continue;
      const addAction=(action,label,payload) => {
        const button=text(row,"button",label);button.type="button";
        button.addEventListener("click",()=>{if(busy||blocked||pendingOperation)return; const data=payload();if(data===null)return; decide({id:item.id,action,payload:data});});
      };
      if(role==="member"&&item.owner_id===userId)addAction("withdraw","撤回本人申请",()=>({}));
      if(role==="teacher"&&item.supervisor_id===userId) {
        if(!item.expired)addAction("approve","批准申请",()=>({}));
        const label=text(row,"label","拒绝原因（1—500 字）"), reason=document.createElement("textarea");
        reason.id=`reason-${item.id}`; reason.rows=3;reason.maxLength=500;label.setAttribute("for",reason.id);row.append(reason);
        addAction("reject","拒绝申请",()=>{if(!reason.value.trim()||Array.from(reason.value.trim()).length>500){say("请填写 1—500 字拒绝原因。",true);reason.focus();return null;}return {reason:reason.value};});
      }
    }
  }
  async function load(prefix="") {
    if(busy||blocked)return;lock(true);relogin.hidden=true;say(prefix+"正在读取申请记录…");
    try{const result=await request("/api/applications");
      if(!result||Object.keys(result).sort().join(",")!=="items,total"||!Array.isArray(result.items)||result.total!==result.items.length||!result.items.every(window.BookingContracts.application))throw Error("Invalid applications");
      allItems=[...result.items].sort((a,b)=>Number(b.status==="awaiting_approval")-Number(a.status==="awaiting_approval")||b.id-a.id);
      fillRooms(appRoom,allItems,item=>item.room.id,item=>item.room.name);
      showApplications();if(prefix||pendingOperation)say(prefix+`共 ${result.total} 条申请。`+(pendingOperation?" 原操作结果尚未确认，请点击重试确认原操作。":""));
    }catch(error){if(!identityLost(error,prefix))say(prefix+(error.api?error.message:"列表刷新失败，请重试。"),true);}finally{lock(false);}
  }
  async function decide(operation) {
    if(busy||blocked)return;pendingOperation=operation;lock(true);retry.hidden=true;say("正在处理，请稍候…");
    let refreshMessage=null;
    try{const result=await request(`/api/applications/${operation.id}/${operation.action}`,operation);
      if(!window.BookingContracts.application(result)||result.id!==operation.id||result.status!=={approve:"approved",reject:"rejected",withdraw:"withdrawn"}[operation.action])throw Error("Unconfirmed transition");
      pendingOperation=null;refreshMessage=`申请 #${result.id}：${labels[result.status]}。`;
      render(displayedItems.map(item=>item.id===result.id?result:item));say(refreshMessage);
    }catch(error){
      if(!identityLost(error)){
        if(error.api){pendingOperation=null;list.replaceChildren();const dates=Array.isArray(error.conflicts)?error.conflicts.map(item=>item.start_local?.slice(0,10)).filter(Boolean):[];refreshMessage=error.message+(dates.length?` 冲突日期：${[...new Set(dates)].join("、")}。`:"")+" 原列表已清空，正在核对最新状态。";say(refreshMessage,true);}
        else{retry.hidden=false;say("结果未知，可能已成功。请点击重试确认原操作；将保留原申请与原原因。",true);}
      }
    }finally{lock(false);}
    if(refreshMessage!==null)await load(refreshMessage);
  }
  refresh.addEventListener("click",()=>load());
  retry.addEventListener("click",()=>{if(pendingOperation)decide(pendingOperation);});
  const cancellationItems=find("cancellations-items"), cancellationFeedback=find("cancellations-feedback"),
    cancellationRefresh=find("cancellations-refresh");
  const cancelStatus=find("cancellations-status"),cancelRoom=find("cancellations-room"),cancelDate=find("cancellations-date");
  function filterCancellations(){
    if(blocked){cancellationItems.replaceChildren();return;}
    let visible=0;
    for(const row of cancellationItems.children){const match=(!cancelStatus?.value||(cancelStatus.value==="processed"?row.dataset.status!=="awaiting_approval":row.dataset.status===cancelStatus.value))
      &&(!cancelRoom?.value||row.dataset.roomId===cancelRoom.value)&&(!cancelDate?.value||row.dataset.date===cancelDate.value);
      row.hidden=!match;if(match)visible++;}
    cancellationFeedback.textContent=`显示 ${visible} / ${cancellationItems.children.length} 条取消申请；待确认排在前面。`;
  }
  for(const filter of [cancelStatus,cancelRoom,cancelDate])filter?.addEventListener("change",filterCancellations);
  if (!cancellationItems || !cancellationFeedback || !cancellationRefresh) {
    load();
    return;
  }
  const cancellationLabels={awaiting_approval:"待本人导师确认，预约仍占用",approved:"已确认取消，时段已释放",
    rejected:"导师已拒绝，预约仍占用",superseded:"管理员已直接取消，申请已终结"};
  async function loadCancellations() {
    cancellationFeedback.textContent="正在读取取消申请…";
    try {
      const data=await request("/api/cancellation-requests");
      if(!data||!Array.isArray(data.items)||data.total!==data.items.length)throw Error("Invalid list");
      cancellationItems.replaceChildren();
      fillRooms(cancelRoom,data.items,item=>item.room_id,item=>item.room_name);
      for(const item of [...data.items].sort((a,b)=>Number(b.status==="awaiting_approval")-Number(a.status==="awaiting_approval")||b.id-a.id)) {
        if(!Object.hasOwn(cancellationLabels,item.status)||!Number.isSafeInteger(item.id)||!Number.isSafeInteger(item.booking_id))throw Error("Invalid request");
        const row=text(cancellationItems,"li","");
        row.dataset.cancellationId=String(item.id);row.dataset.status=item.status;row.dataset.roomId=String(item.room_id);row.dataset.date=item.start_local.slice(0,10);
        text(row,"h3",`取消申请 #${item.id} · 预约 #${item.booking_id} · ${item.title}`);
        text(row,"p",cancellationLabels[item.status]+(item.expired?" · 已到开始时间，不能再确认":""));
        text(row,"p",`${item.room_name} · ${local(item.start_local)} — ${local(item.end_local)}`);
        text(row,"p",`申请人：${item.owner_display_name} · 本人导师：${item.supervisor_display_name}`);
        if(item.decided_at!==null)text(row,"p",`处理时间：${new Date(item.decided_at*1000).toLocaleString("zh-CN",{timeZone:"Asia/Shanghai"})} · 处理人编号 ${item.decided_by}`);
        if(item.reason)text(row,"p",`拒绝原因：${item.reason}`);
        if(role==="teacher"&&item.supervisor_id===userId&&item.status==="awaiting_approval") {
          if(!item.expired) {
            const approve=text(row,"button","确认取消");approve.type="button";
            approve.addEventListener("click",()=>decideCancellation(item,"approve",{}));
          }
          const label=text(row,"label","拒绝原因（1—500 字）"),reason=document.createElement("textarea");
          reason.id=`cancellation-reason-${item.id}`;reason.rows=3;reason.maxLength=500;label.setAttribute("for",reason.id);row.append(reason);
          const reject=text(row,"button","拒绝取消");reject.type="button";
          reject.addEventListener("click",()=>{if(!reason.value.trim()){cancellationFeedback.textContent="请填写拒绝原因。";reason.focus();return;}decideCancellation(item,"reject",{reason:reason.value});});
        }
      }
      filterCancellations();
    } catch(error) {if(error.code==="AUTH_REQUIRED")identityLost(error);cancellationFeedback.textContent=error.api?error.message:"取消申请读取失败，请刷新重试。";}
  }
  async function decideCancellation(item,action,payload) {
    cancellationFeedback.textContent="正在处理取消申请…";
    try {
      const result=await request(`/api/cancellation-requests/${item.id}/${action}`,{payload});
      if(result.id!==item.id||result.status!==(action==="approve"?"approved":"rejected"))throw Error("Invalid decision");
      await loadCancellations();
    } catch(error) {cancellationFeedback.textContent=error.api?error.message:"处理结果未知，请刷新记录核对后重试。";}
  }
  cancellationRefresh.addEventListener("click",loadCancellations);
  loadCancellations();
  load();
})();
