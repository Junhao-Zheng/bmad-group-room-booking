(() => {
  "use strict";
  const find = id => document.getElementById(id), form = find("batch-form");
  if (!form) return;
  const inputs = ["room_id", "start", "end", "reason"].map(name => form.elements.namedItem(name));
  const previewButton = find("batch-preview"), submit = find("batch-submit"), confirm = find("batch-confirm");
  const review = find("batch-review"), summary = find("batch-summary"), affected = find("batch-affected");
  const feedback = find("batch-feedback"), relogin = find("batch-relogin");
  let token = null, reviewed = null, busy = false, blocked = false, successful = "";
  const local = value => value.replace("T", " ").replace("+08:00", "");
  const safeId = value => Number.isSafeInteger(value) && value > 0;
  const object = value => value !== null && typeof value === "object" && !Array.isArray(value);
  const exact = (value, keys) => object(value) && Object.keys(value).sort().join(",") === keys.split(",").sort().join(",");
  function say(message, error = false) {
    feedback.textContent = successful + message;
    feedback.classList.toggle("error", error);
    feedback.setAttribute("role", error ? "alert" : "status");
    feedback.focus();
  }
  function controls() {
    previewButton.disabled = busy || blocked;
    submit.disabled = busy || blocked || token === null || !confirm.checked;
    confirm.disabled = busy || blocked || token === null;
    for (const input of inputs) input.disabled = busy || blocked;
    form.setAttribute("aria-busy", String(busy));
  }
  function clearPreview(message = "输入已更改，请重新预览。") {
    token = null; reviewed = null; confirm.checked = false; review.hidden = true;
    affected.replaceChildren(); summary.textContent = ""; controls();
    if (message) say(message);
  }
  for (const input of inputs) for (const event of ["input", "change"]) input.addEventListener(event, () => {
    if (token !== null) clearPreview();
  });
  confirm.addEventListener("change", controls);
  function identityLost(error) {
    if (!["AUTH_REQUIRED", "FORBIDDEN", "CSRF_REJECTED"].includes(error.code)) return false;
    relogin.hidden = false;
    blocked = true;
    clearPreview("");
    say("身份或页面验证已失效，请重新登录后预览。", true);
    return true;
  }
  document.addEventListener("admin-auth-lost", event => {
    if (!["AUTH_REQUIRED", "FORBIDDEN"].includes(event.detail?.code)) return;
    blocked = true; relogin.hidden = false; clearPreview("");
    say("管理权限已失效，请重新登录后预览。", true);
  });
  async function request(url, data) {
    const controller = new AbortController(), timer = window.setTimeout(() => controller.abort(), 20000);
    try {
      const response = await fetch(url, {method:"POST", credentials:"same-origin", signal:controller.signal,
        headers:{"Content-Type":"application/json", "X-CSRF-Token":find("logout-form").elements.csrf_token.value},
        body:JSON.stringify(data)});
      const body = await response.json();
      if (response.ok && exact(body,"ok,data") && body.ok === true) return body.data;
      if (!response.ok && exact(body,"ok,error") && body.ok === false && object(body.error) && typeof body.error.code === "string")
        throw Object.assign(Error(body.error.message), {api:true, code:body.error.code});
      throw Error("Invalid response");
    } finally { window.clearTimeout(timer); }
  }
  function affectedShape(item) {
    return exact(item,"id,title,owner_display_name,start_at,start_local,end_at,end_local") && safeId(item.id) &&
      [item.title,item.owner_display_name,item.start_local,item.end_local].every(value => typeof value === "string") &&
      Number.isSafeInteger(item.start_at) && Number.isSafeInteger(item.end_at) && item.start_at < item.end_at;
  }
  function previewShape(data, values) {
    return exact(data,"preview_token,room,start_at,start_local,end_at,end_local,reason,affected,expires_at") &&
      /^[A-Za-z0-9_-]{32,80}$/.test(data.preview_token) && window.BookingContracts.room(data.room) &&
      data.room.id === values.room_id && Number.isSafeInteger(data.start_at) && Number.isSafeInteger(data.end_at) &&
      data.start_local.slice(0,16) === `${values.start}:00+08:00`.slice(0,16) &&
      data.end_local.slice(0,16) === `${values.end}:00+08:00`.slice(0,16) &&
      typeof data.reason === "string" && data.reason === values.reason.trim() &&
      Array.isArray(data.affected) && data.affected.every(affectedShape) && Number.isSafeInteger(data.expires_at);
  }
  form.addEventListener("submit", async event => {
    event.preventDefault();
    if (busy || blocked) return;
    clearPreview("");
    const values = {room_id:Number(inputs[0].value), start:inputs[1].value, end:inputs[2].value, reason:inputs[3].value};
    if (!safeId(values.room_id) || !/^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:(00|30)$/.test(values.start) ||
        !/^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:(00|30)$/.test(values.end) || !values.reason.trim()) {
      say("请填写有效会议室、半小时时段和停用原因。", true); return;
    }
    busy = true; controls(); say("正在预览受影响预约…");
    try {
      const data = await request("/api/admin/blocks/preview", values);
      if (!previewShape(data, values)) throw Error("Invalid preview");
      token = data.preview_token;
      reviewed = data;
      summary.textContent = `${data.room.name} · ${data.room.location} · ${local(data.start_local)} — ${local(data.end_local)} · 原因：${data.reason}`;
      affected.replaceChildren();
      if (!data.affected.length) {
        const row = document.createElement("li"); row.textContent = "无预约需要取消。"; affected.append(row);
      }
      for (const item of data.affected) {
        const row = document.createElement("li");
        row.textContent = `预约 #${item.id} · ${item.title} · ${item.owner_display_name} · ${local(item.start_local)} — ${local(item.end_local)}`;
        affected.append(row);
      }
      review.hidden = false;
      say(`已预览 ${data.affected.length} 条受影响预约。请核对后一次确认。`);
    } catch (error) {
      if (!identityLost(error)) say(error.api ? error.message : "预览结果未知，请重新预览。", true);
    } finally { busy = false; controls(); }
  });
  submit.addEventListener("click", async () => {
    if (busy || blocked || token === null || !confirm.checked) return;
    busy = true; controls(); say("正在取消受影响预约并设置停用…");
    try {
      const data = await request("/api/admin/blocks/confirm", {preview_token:token, confirmed:true});
      if (!exact(data,"block,affected,replayed") || !object(data.block) || !safeId(data.block.id) ||
          !["pending","in_progress","ended","revoked"].includes(data.block.status) ||
          !window.BookingContracts.room(data.block.room) || data.block.room.id !== reviewed.room.id ||
          data.block.start_at !== reviewed.start_at || data.block.end_at !== reviewed.end_at ||
          data.block.reason !== reviewed.reason ||
          !Array.isArray(data.affected) || !data.affected.every(affectedShape) ||
          JSON.stringify(data.affected) !== JSON.stringify(reviewed.affected) || typeof data.replayed !== "boolean")
        throw Error("Invalid confirmation");
      successful = `停用 #${data.block.id} 已确认；${data.affected.length} 条预约已取消。`;
      token = null; reviewed = null; confirm.checked = false; review.hidden = true;
      affected.replaceChildren(); summary.textContent = "";
      say("可在完整预约和停用记录中查看结果。");
    } catch (error) {
      if (!identityLost(error)) {
        if (error.api && ["TRANSITION_CLOSED","OCCUPANCY_CONFLICT","NOT_FOUND","INVALID_INPUT"].includes(error.code)) {
          clearPreview(""); say(`${error.message} 请重新预览。`, true);
        } else say("结果尚未确认。请保留当前预览凭据，点击确认重试；不会新建另一批。", true);
      }
    } finally { busy = false; controls(); }
  });
  controls();
})();
