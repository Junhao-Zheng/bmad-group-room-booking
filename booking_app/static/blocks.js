"use strict";

(() => {
  const find = id => document.getElementById(id), form = find("block-form");
  if (!form) return;
  const inputs = ["room_id", "start", "end", "reason"].map(name => form.elements.namedItem(name));
  const submit = find("block-submit"), confirm = find("block-confirm"), feedback = find("block-feedback");
  const conflicts = find("block-conflicts"), relogin = find("block-relogin"), refresh = find("block-rooms-refresh");
  const statuses = {pending:"待开始", in_progress:"进行中", ended:"已结束", cancelled:"已取消", revoked:"已撤销"};
  let creating = false, refreshing = false, blocked = false, createdMessage = "";
  const lists = ["bookings", "blocks"].map(kind => ({kind, form:find(`admin-${kind}-form`),
    items:find(`admin-${kind}-items`), feedback:find(`admin-${kind}-feedback`), busy:false, revision:0}));
  const fields = list => ["room_id", "date", "status"].map(name => list.form.elements.namedItem(name));
  const say = (node, text, error = false) => {
    node.textContent = text; node.classList.toggle("error", error); node.setAttribute("role", error ? "alert" : "status");
  };
  const object = value => value !== null && typeof value === "object" && !Array.isArray(value);
  const exact = (value, keys) => object(value) && Object.keys(value).sort().join(",") === keys.split(",").sort().join(",");
  const id = value => Number.isInteger(value) && value > 0;
  const local = value => typeof value === "string" && /^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}\+08:00$/.test(value);
  const roomShape = room => exact(room,"id,name,location,capacity") && id(room.id) && Number.isSafeInteger(room.id) && typeof room.name === "string" &&
    typeof room.location === "string" && Number.isInteger(room.capacity) && room.capacity >= 1 && room.capacity <= 1000;
  const commonKeys = "id,room,start_at,start_local,end_at,end_local,status,created_at,created_local";
  function recordShape(row, kind) {
    const booking = kind === "bookings", prefix = booking ? "cancelled" : "revoked", reason = booking ? "cancel_reason" : "revoke_reason";
    const own = booking ? "title,purpose,attendees,owner_id,owner_display_name" : "creator_id,creator_display_name,reason";
    if (!exact(row, `${commonKeys},${own},${prefix}_at,${prefix}_local,${prefix}_by_id,${prefix}_by_display_name,${reason}`) ||
        !id(row.id) || !roomShape(row.room) || ![row.start_at,row.end_at,row.created_at].every(Number.isInteger) ||
        ![row.start_local,row.end_local,row.created_local].every(local) || row.start_at >= row.end_at ||
        !["pending","in_progress","ended",prefix].includes(row.status)) return false;
    if (booking ? (!id(row.owner_id) || typeof row.owner_display_name !== "string" || typeof row.title !== "string" ||
        typeof row.purpose !== "string" || !id(row.attendees)) : (!id(row.creator_id) || typeof row.creator_display_name !== "string" || typeof row.reason !== "string")) return false;
    const terminal = [`${prefix}_at`, `${prefix}_local`, `${prefix}_by_id`, `${prefix}_by_display_name`, reason];
    if (row.status !== prefix) return terminal.every(key => row[key] === null);
    return Number.isInteger(row[terminal[0]]) && local(row[terminal[1]]) && id(row[terminal[2]]) &&
      typeof row[terminal[3]] === "string" && (typeof row[reason] === "string" || (booking && row[reason] === null));
  }
  function errorShape(error) {
    return exact(error,"code,message,fields,conflicts") && typeof error.code === "string" && typeof error.message === "string" &&
      object(error.fields) && Object.values(error.fields).every(value => typeof value === "string") && Array.isArray(error.conflicts) &&
      error.conflicts.every(row => exact(row,"id,type,room_id,start_at,start_local,end_at,end_local,status,attendees,reason") &&
        id(row.id) && id(row.room_id) && [row.start_at,row.end_at].every(Number.isInteger) && [row.start_local,row.end_local].every(local) &&
        ["pending","in_progress","ended"].includes(row.status) &&
        (row.type === "booking" ? id(row.attendees) && row.reason === null : row.type === "block" && row.attendees === null && typeof row.reason === "string"));
  }
  async function request(url, values) {
    const controller = new AbortController(), timer = window.setTimeout(() => controller.abort(), 20000);
    try {
      const response = await fetch(url, {credentials:"same-origin", signal:controller.signal,
        ...(values ? {method:"POST", headers:{"Content-Type":"application/json",
          "X-CSRF-Token":find("logout-form").elements.csrf_token.value}, body:JSON.stringify(values)} : {})});
      const body = await response.json();
      if (response.ok && exact(body,"ok,data") && body.ok === true) return body.data;
      if (!response.ok && exact(body,"ok,error") && body.ok === false && errorShape(body.error)) throw {serverError:body.error};
      throw new Error("Invalid response");
    } finally { window.clearTimeout(timer); }
  }
  function controls() {
    [...inputs,confirm,submit].forEach(node => { node.disabled = blocked || creating || refreshing || lists.some(list => list.busy); });
    refresh.disabled = blocked || creating || refreshing || lists.some(list => list.busy);
    if (creating) form.setAttribute("aria-busy","true"); else form.removeAttribute("aria-busy");
    for (const list of lists) {
      [...fields(list), find(`admin-${list.kind}-submit`)].forEach(node => { node.disabled = blocked || list.busy || refreshing || creating; });
      if (list.busy) list.form.setAttribute("aria-busy","true"); else list.form.removeAttribute("aria-busy");
    }
  }
  function identityError(error, broadcast = true) {
    if (["AUTH_REQUIRED","FORBIDDEN","CSRF_REJECTED"].includes(error.code)) relogin.hidden = false;
    if (!["AUTH_REQUIRED","FORBIDDEN"].includes(error.code)) return false;
    const firstLoss = !blocked;
    blocked = true; conflicts.replaceChildren();
    const message = error.code === "AUTH_REQUIRED" ? "登录已失效，请重新登录后打开管理页。" : "当前无管理权限，请以管理员身份重新登录。";
    say(feedback, `${createdMessage}${message} 表单输入已保留，不会自动提交。`, true);
    say(find("block-rooms-feedback"),message,true);
    for (const list of lists) { list.items.replaceChildren(); say(list.feedback,message,true); }
    controls();
    if (broadcast && firstLoss) document.dispatchEvent(new CustomEvent("admin-auth-lost", {detail:{code:error.code}}));
    return true;
  }
  document.addEventListener("admin-auth-lost", event => {
    if (["AUTH_REQUIRED","FORBIDDEN"].includes(event.detail?.code)) identityError({code:event.detail.code},false);
  });
  function summary() {
    confirm.checked = false;
    const room = inputs[0].options[inputs[0].selectedIndex]?.textContent || "未选择会议室";
    find("block-summary").textContent = `会议室：${room}\n北京时间：${inputs[1].value || "未填开始"} 至 ${inputs[2].value || "未填结束"}\n停用原因：${inputs[3].value || "未填写"}`;
  }
  for (const input of inputs) for (const event of ["input","change"]) input.addEventListener(event,summary);
  const formatted = value => value.replace("T"," ").slice(0,19);
  const focusAllowed = owner => !document.activeElement || document.activeElement === document.body || owner.contains(document.activeElement);
  function render(list, records) {
    list.items.replaceChildren();
    for (const row of records) {
      const booking = list.kind === "bookings", prefix = booking ? "cancelled" : "revoked";
      const item = document.createElement("li"), title = document.createElement("h3"), detail = document.createElement("dl");
      title.textContent = `${booking ? "预约" : "停用"} ${row.id} · ${statuses[row.status]}`; detail.className = "booking-fields";
      const pairs = [["会议室", `${row.room.id} · ${row.room.name} · ${row.room.location} · 容量 ${row.room.capacity} 人`],
        ["时段（北京时间）",`${formatted(row.start_local)} 至 ${formatted(row.end_local)}`],
        ...(booking ? [["活动名称",row.title],["用途",row.purpose],["预计人数",`${row.attendees} 人`],
          ["预约人",`${row.owner_id} · ${row.owner_display_name}`]] : [["停用原因",row.reason],["创建者",`${row.creator_id} · ${row.creator_display_name}`]]),
        ["创建时间（北京时间）",formatted(row.created_local)],
        [booking ? "取消信息" : "撤销信息",row[`${prefix}_at`] === null ? (booking ? "未取消" : "未撤销") :
          `${formatted(row[`${prefix}_local`])}（北京时间） · 操作者 ${row[`${prefix}_by_id`]} · ${row[`${prefix}_by_display_name`]}\n原因：${row[booking ? "cancel_reason" : "revoke_reason"] ?? "本人取消，无原因"}`]];
      for (const [label,value] of pairs) {
        const dt = document.createElement("dt"), dd = document.createElement("dd"); dt.textContent = label; dd.textContent = value; detail.append(dt,dd);
      }
      item.append(title,detail); list.items.append(item);
    }
  }
  async function load(list, automatic = false) {
    if (list.busy || blocked) return;
    const initiatedHere = list.form.contains(document.activeElement), params = new URLSearchParams(), revision = list.revision;
    let focusTarget = list.feedback;
    clearListErrors(list);
    for (const input of fields(list)) if (input.value) params.set(input.name,input.value);
    list.busy = true; controls(); list.items.replaceChildren(); say(list.feedback,"正在加载管理记录…");
    try {
      const data = await request(`/api/admin/${list.kind}?${params}`);
      if (!exact(data,"items,total") || !Array.isArray(data.items) || data.total !== data.items.length ||
          !data.items.every(row => recordShape(row,list.kind))) throw new Error("Invalid list");
      if (blocked || revision !== list.revision) return;
      render(list,data.items); say(list.feedback,data.total ? `共 ${data.total} 条${list.kind === "bookings" ? "预约" : "停用"}记录。` : "没有符合条件的记录。");
    } catch (failure) {
      const lostIdentity = failure.serverError && identityError(failure.serverError);
      if (!blocked && !lostIdentity && revision === list.revision) {
        const error = failure.serverError;
        say(list.feedback,`${automatic ? "停用已创建，但列表刷新失败。" : "管理记录查询失败。"} ${error ? error.message : "请稍后手动查询。"} 筛选条件已保留。`,true);
        for (const input of fields(list)) if (error?.fields[input.name]) {
          input.setAttribute("aria-invalid","true"); find(`admin-${list.kind}-${input.name}-error`).textContent = error.fields[input.name];
          if (focusTarget === list.feedback) focusTarget = input;
        }
      }
    } finally {
      list.busy = false; controls();
      if (!automatic && initiatedHere && revision === list.revision && focusAllowed(list.form)) focusTarget.focus();
    }
  }
  function clearListErrors(list) {
    for (const input of fields(list)) {
      input.removeAttribute("aria-invalid"); find(`admin-${list.kind}-${input.name}-error`).textContent = "";
    }
  }
  for (const list of lists) for (const input of fields(list)) for (const event of ["input","change"]) input.addEventListener(event, () => {
    if (blocked) return;
    list.revision++; list.items.replaceChildren(); clearListErrors(list);
    say(list.feedback,"筛选条件已更改，请重新查询记录。");
  });
  for (const list of lists) list.form.addEventListener("submit",event => {
    event.preventDefault(); if (!creating && !refreshing) return load(list);
  });
  form.addEventListener("submit", async event => {
    event.preventDefault(); if (creating || refreshing || blocked || lists.some(list => list.busy) || !confirm.checked) return;
    const values = {room_id:Number(inputs[0].value), start:inputs[1].value, end:inputs[2].value, reason:inputs[3].value};
    const initiatedHere = form.contains(document.activeElement); let focusTarget = feedback;
    for (const input of inputs) { input.removeAttribute("aria-invalid"); find(`block-${input.name}-error`).textContent = ""; }
    if (!/^[1-9][0-9]*$/.test(inputs[0].value) || !Number.isSafeInteger(values.room_id)) {
      inputs[0].setAttribute("aria-invalid","true");
      find("block-room_id-error").textContent = "当前浏览器无法安全提交此会议室编号，请重新选择有效会议室。";
      say(feedback,"会议室编号无法安全提交，输入已保留。",true); inputs[0].focus(); return;
    }
    createdMessage = "";
    conflicts.replaceChildren(); relogin.hidden = true; creating = true; controls(); say(feedback,"正在创建停用，请稍候…");
    try {
      const record = await request("/api/admin/blocks",values);
      if (!recordShape(record,"blocks")) throw new Error("Invalid block");
      if (blocked) return;
      confirm.checked = false;
      createdMessage = `停用 ${record.id} 已创建。`;
      say(feedback,`${createdMessage}北京时间 ${formatted(record.start_local)} 至 ${formatted(record.end_local)}。`);
      await load(lists[1],true);
    } catch (failure) {
      const error = failure.serverError;
      if (error) {
        if (!identityError(error) && !blocked) {
          say(feedback,`${error.message} 输入已保留。`,true);
          for (const input of inputs) if (error.fields[input.name]) {
            input.setAttribute("aria-invalid","true"); find(`block-${input.name}-error`).textContent = error.fields[input.name];
            if (focusTarget === feedback) focusTarget = input;
          }
          for (const row of error.conflicts) {
            const item = document.createElement("li"); item.textContent = `${row.type === "booking" ? "预约" : "停用"} ${row.id} · 会议室 ${row.room_id} · 北京时间 ${formatted(row.start_local)} 至 ${formatted(row.end_local)} · ${statuses[row.status]} · ${row.type === "booking" ? `${row.attendees} 人` : `原因：${row.reason}`}`; conflicts.append(item);
          }
        }
      } else if (!blocked) {
        confirm.checked = false;
        say(feedback,"未能确认创建结果，输入已保留。请先查询停用记录核对；再次提交前须重新核对并勾选确认，不会自动重试。",true);
      }
    } finally {
      creating = false; controls(); if (initiatedHere && focusAllowed(form)) focusTarget.focus();
    }
  });
  refresh.addEventListener("click", async () => {
    if (blocked || refreshing || creating || lists.some(list => list.busy)) return;
    const initiatedHere = document.activeElement === refresh; refreshing = true; controls();
    const output = find("block-rooms-feedback"); say(output,"正在刷新会议室选项…");
    try {
      const data = await request("/api/rooms");
      if (!exact(data,"items,total") || !Array.isArray(data.items) || data.total !== data.items.length || !data.items.every(roomShape)) throw new Error("Invalid rooms");
      if (blocked) return;
      for (const select of [inputs[0],...lists.map(list => fields(list)[0])]) {
        const previous = select.value, first = document.createElement("option"); first.value = "";
        first.textContent = select === inputs[0] ? "请选择会议室" : "全部会议室"; select.replaceChildren(first);
        for (const room of data.items) { const option = document.createElement("option"); option.value = String(room.id); option.textContent = `${room.name} · ${room.location}`; select.append(option); }
        select.value = previous;
      }
      summary(); say(output,"会议室选项已刷新，请重新核对创建信息。");
    } catch (failure) {
      if (!(failure.serverError && identityError(failure.serverError)) && !blocked) say(output,"会议室选项刷新失败，输入已保留，请手动重试。",true);
    } finally {
      refreshing = false; controls();
      if (initiatedHere && (!document.activeElement || document.activeElement === document.body)) (blocked ? feedback : refresh).focus();
    }
  });
  controls();
  find("block-script-unavailable").hidden = true;
  find("block-fields").disabled = false;
})();
