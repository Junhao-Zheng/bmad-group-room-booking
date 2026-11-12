"use strict";

(() => {
  const find = id => document.getElementById(id), form = find("audit-form");
  if (!form) return;
  const list = find("audit-items"), results = find("audit-results"), feedback = find("audit-feedback");
  const relogin = find("audit-relogin"), submit = find("audit-submit");
  const inputs = [find("audit-target_type"), find("audit-date")];
  let busy = false, blocked = false, generation = 0, controller;
  const object = value => value !== null && typeof value === "object" && !Array.isArray(value);
  const keys = (value, names) => object(value) && Object.keys(value).sort().join(",") === names.split(",").sort().join(",");
  const actions = {"room.created":"新增会议室", "room.updated":"修改会议室", "booking.created":"创建预约",
    "booking.cancelled_by_member":"本人取消预约", "booking.cancelled_by_admin":"管理员取消预约",
    "block.created":"创建停用", "block.revoked":"撤销停用"};
  const snapshots = {room:"id,name,location,capacity", booking:"id,room_id,owner_id,title,purpose,attendees,start_at,end_at,created_at,cancelled_at,cancelled_by_id,cancel_reason",
    block:"id,room_id,creator_id,reason,start_at,end_at,created_at,revoked_at,revoked_by_id,revoke_reason"};
  const nullableFields = new Set(["cancelled_at","cancelled_by_id","cancel_reason","revoked_at","revoked_by_id","revoke_reason"]);
  const textFields = new Set(["name","location","title","purpose","reason","cancel_reason","revoke_reason"]);
  function snapshotShape(value, type) {
    return keys(value,snapshots[type]) && Object.entries(value).every(([field,item]) =>
      item === null ? nullableFields.has(field) : textFields.has(field) ? typeof item === "string" : Number.isInteger(item));
  }
  function eventShape(row) {
    return keys(row,"id,actor_id,actor_display_name,action,target_type,target_id,occurred_at,occurred_local,before,after,reason") &&
      [row.id,row.actor_id,row.target_id].every(value => Number.isInteger(value) && value > 0) &&
      Number.isInteger(row.occurred_at) && typeof row.actor_display_name === "string" &&
      Object.hasOwn(actions,row.action) && row.action.split(".")[0] === row.target_type &&
      typeof row.occurred_local === "string" && /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\+08:00$/.test(row.occurred_local) &&
      (row.before === null || snapshotShape(row.before,row.target_type)) && snapshotShape(row.after,row.target_type) &&
      (row.reason === null || typeof row.reason === "string");
  }
  function say(message, error = false) {
    feedback.textContent = message; feedback.classList.toggle("error",error);
    feedback.setAttribute("role",error ? "alert" : "status");
  }
  function controls(value) {
    busy = value; [...inputs,submit].forEach(node => { node.disabled = value || blocked; });
    if (value) form.setAttribute("aria-busy","true"); else form.removeAttribute("aria-busy");
  }
  function identityLost(code, broadcast = true) {
    if (blocked) return;
    blocked = true; generation++; controller?.abort(); list.replaceChildren(); results.hidden = true;
    relogin.hidden = false; controls(false);
    say(code === "FORBIDDEN" ? "当前无管理权限，请以管理员身份重新登录后打开管理页。" : "登录已失效，请重新登录后打开管理页。",true);
    if (broadcast) document.dispatchEvent(new CustomEvent("admin-auth-lost",{detail:{code}}));
  }
  document.addEventListener("admin-auth-lost",event => identityLost(event.detail.code,false));
  for (const input of inputs) for (const event of ["input","change"]) input.addEventListener(event,() => {
    if (blocked) return;
    generation++; controller?.abort(); list.replaceChildren(); results.hidden = true; controls(false);
    say("筛选条件已修改，请重新查询操作记录。");
  });
  function cell(row, text, expandable = false) {
    const td = document.createElement("td");
    if (expandable) {
      const details = document.createElement("details"), summary = document.createElement("summary"), content = document.createElement("pre");
      summary.textContent = "展开完整内容"; content.textContent = text; details.append(summary,content); td.append(details);
    } else td.textContent = text;
    row.append(td);
  }
  function render(items) {
    list.replaceChildren(); results.hidden = items.length === 0;
    for (const item of items) {
      const row = document.createElement("tr");
      cell(row,`#${item.id} · ${item.occurred_local.replace("T"," ").replace("+08:00","")}`);
      cell(row,`${item.actor_display_name}（${item.actor_id}）`);
      cell(row,`${actions[item.action]} · ${item.action}\n${item.target_type} #${item.target_id}`);
      cell(row,item.before === null ? "无（创建前）" : JSON.stringify(item.before,null,2),item.before !== null);
      cell(row,JSON.stringify(item.after,null,2),true);
      cell(row,item.reason === null ? "无" : item.reason,item.reason !== null && item.reason.length > 80);
      list.append(row);
    }
  }
  form.addEventListener("submit",async event => {
    event.preventDefault(); if (busy || blocked) return;
    const requestGeneration = ++generation, params = new URLSearchParams();
    inputs.forEach(input => { if (input.value) params.set(input.name,input.value); });
    list.replaceChildren(); results.hidden = true; relogin.hidden = true; controls(true); say("正在加载操作记录…");
    const requestController = new AbortController(); controller = requestController;
    const timer = window.setTimeout(() => requestController.abort(),20000);
    try {
      const response = await fetch(`/api/admin/audit?${params}`,{credentials:"same-origin",signal:requestController.signal});
      const body = await response.json();
      if (blocked || generation !== requestGeneration) return;
      if (!response.ok && body.ok === false && object(body.error) && typeof body.error.code === "string") {
        if (["AUTH_REQUIRED","FORBIDDEN"].includes(body.error.code)) { identityLost(body.error.code); return; }
        say(body.error.code === "INVALID_INPUT" ? "筛选条件无效，请检查对象和日期后重新查询。" : "查询失败，条件已保留，请稍后手动重试。",true); return;
      }
      if (!response.ok || !keys(body,"ok,data") || body.ok !== true || !keys(body.data,"items,total") ||
          !Array.isArray(body.data.items) || body.data.total !== body.data.items.length || !body.data.items.every(eventShape)) throw new Error("Invalid audit response");
      render(body.data.items); say(body.data.total ? `共 ${body.data.total} 条操作记录。` : "没有符合条件的操作记录。");
    } catch (_) {
      if (!blocked && generation === requestGeneration) say("未能读取操作记录，条件已保留，请手动重试。",true);
    } finally {
      window.clearTimeout(timer);
      if (generation === requestGeneration) controls(false);
    }
  });
})();
