"use strict";

(() => {
  const find = id => document.getElementById(id);
  const form = find("room-form"), list = find("admin-rooms"), heading = find("room-form-title");
  if (!form) return;
  const submit = find("room-submit"), cancel = find("room-cancel"), confirm = find("room-confirm");
  const refresh = find("rooms-refresh"), feedback = find("room-feedback"), directoryFeedback = find("rooms-feedback");
  const conflicts = find("room-conflicts"), relogin = find("room-relogin");
  const inputs = ["name", "location", "capacity"].map(name => form.elements.namedItem(name));
  let editing = null, busy = false, blocked = false;
  const displayed = new Map();
  function fillInputs(room) {
    for (const input of inputs) {
      input.value = room ? String(room[input.name]) : "";
      // Textarea values normalize CR/CRLF to LF. Keep that display baseline
      // separate from the raw server facts for a capacity-only edit.
      displayed.set(input.name, input.value);
    }
  }
  const draftText = input => editing && input.value === displayed.get(input.name) ? editing[input.name] : input.value;
  for (const input of inputs) {
    for (const event of ["input", "change"]) input.addEventListener(event, () => { confirm.checked = false; });
  }
  const say = (node, message, error = false) => {
    node.textContent = message; node.classList.toggle("error", error);
    node.setAttribute("role", error ? "alert" : "status");
  };
  function controls(value) {
    busy = value;
    [...inputs, confirm, submit, cancel, refresh, ...list.querySelectorAll("button")].forEach(node => { node.disabled = value || blocked; });
    if (value) form.setAttribute("aria-busy", "true"); else form.removeAttribute("aria-busy");
  }
  function clearErrors() {
    for (const input of inputs) {
      input.removeAttribute("aria-invalid"); find(`room-${input.name}-error`).textContent = "";
    }
    conflicts.replaceChildren(); relogin.hidden = true;
  }
  function setEditing(room) {
    if (busy || blocked) return;
    editing = room;
    fillInputs(room);
    confirm.checked = false; cancel.hidden = !room; clearErrors();
    heading.textContent = room ? `编辑会议室 ${room.id}` : "新增会议室";
    submit.textContent = room ? "确认保存会议室" : "确认新增会议室";
    say(feedback, ""); heading.focus();
  }
  function bindEdit(button, room) { button.addEventListener("click", () => setEditing(room)); }
  for (const button of list.querySelectorAll("button")) {
    bindEdit(button, JSON.parse(button.dataset.room));
  }
  function roomShape(room) {
    return room && Object.keys(room).sort().join(",") === "capacity,id,location,name" &&
      Number.isInteger(room.id) && room.id > 0 && typeof room.name === "string" &&
      typeof room.location === "string" && Number.isInteger(room.capacity) && room.capacity >= 1 && room.capacity <= 1000;
  }
  const object = value => value !== null && typeof value === "object" && !Array.isArray(value);
  const localTimestamp = value => typeof value === "string" && /^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}\+08:00$/.test(value);
  function errorShape(error) {
    return object(error) && typeof error.code === "string" && typeof error.message === "string" &&
      object(error.fields) && Object.values(error.fields).every(value => typeof value === "string") &&
      Array.isArray(error.conflicts) && error.conflicts.every(row => object(row) &&
        Number.isInteger(row.id) && row.id > 0 && Number.isInteger(row.attendees) && row.attendees > 0 &&
        localTimestamp(row.start_local) && localTimestamp(row.end_local) && ["pending", "in_progress"].includes(row.status));
  }
  async function request(url, values) {
    const controller = new AbortController(), timer = window.setTimeout(() => controller.abort(), 20000);
    try {
      const response = await fetch(url, {credentials:"same-origin",signal:controller.signal,
        ...(values ? {method:"POST",headers:{"Content-Type":"application/json",
          "X-CSRF-Token":document.querySelector("#logout-form").elements.csrf_token.value},body:JSON.stringify(values)} : {})});
      const body = await response.json();
      if (response.ok && body.ok === true && body.data) return body.data;
      if (!response.ok && body.ok === false && errorShape(body.error)) throw {serverError:body.error};
      throw new Error("Invalid response");
    } finally { window.clearTimeout(timer); }
  }
  function sessionError(error) {
    const identityLost = ["AUTH_REQUIRED", "FORBIDDEN"].includes(error.code);
    if (identityLost) {
      blocked = true; list.replaceChildren(); conflicts.replaceChildren();
      say(directoryFeedback, error.code === "AUTH_REQUIRED" ? "登录已失效，请重新登录后打开管理页。表单输入已保留。" :
        "当前无管理权限，请以管理员身份重新登录后打开管理页。表单输入已保留。", true);
    }
    if (["AUTH_REQUIRED", "FORBIDDEN", "CSRF_REJECTED"].includes(error.code)) relogin.hidden = false;
    return identityLost;
  }
  async function loadRooms() {
    const data = await request("/api/rooms");
    if (!Array.isArray(data.items) || data.total !== data.items.length || !data.items.every(roomShape)) throw new Error("Invalid directory");
    list.replaceChildren();
    for (const room of data.items) {
      const item = document.createElement("li"), title = document.createElement("h3"), detail = document.createElement("p"), button = document.createElement("button");
      title.textContent = room.name; detail.textContent = `${room.location} · 容量 ${room.capacity} 人`;
      button.textContent = `编辑会议室 ${room.id}`; button.type = "button"; button.className = "button-secondary";
      button.disabled = busy || blocked; bindEdit(button, room); item.append(title, detail, button); list.append(item);
    }
    say(directoryFeedback, data.total ? `共 ${data.total} 间会议室，目录已刷新。` : "暂无会议室，请新增。");
  }
  const canFocus = () => !document.activeElement || document.activeElement === document.body || form.contains(document.activeElement);
  form.addEventListener("submit", async event => {
    event.preventDefault(); if (busy || blocked || !confirm.checked) return;
    const capacity = Number(inputs[2].value);
    if (!inputs[2].value.trim() || !Number.isInteger(capacity) || capacity < 1 || capacity > 1000) {
      clearErrors(); inputs[2].setAttribute("aria-invalid", "true");
      find("room-capacity-error").textContent = "容量须为 1—1000 的整数。";
      say(feedback, "请检查容量，输入已保留。", true); inputs[2].focus(); return;
    }
    const values = {name:draftText(inputs[0]), location:draftText(inputs[1]), capacity};
    const roomId = editing?.id; const initiatedHere = form.contains(document.activeElement);
    clearErrors(); controls(true); submit.textContent = "正在提交…";
    say(feedback, "正在保存，请稍候…"); let focusTarget = feedback;
    try {
      const room = await request(roomId ? `/api/admin/rooms/${roomId}` : "/api/admin/rooms", values);
      if (!roomShape(room) || (roomId && room.id !== roomId)) throw new Error("Invalid room");
      editing = room; cancel.hidden = false; heading.textContent = `编辑会议室 ${room.id}`;
      fillInputs(room);
      confirm.checked = false;
      say(feedback, `会议室 ${room.id} 已保存。相同资料重复保存不会新增操作记录。`);
      try { await loadRooms(); }
      catch (error) {
        if (error.serverError && sessionError(error.serverError)) say(feedback, "会议室资料已保存。");
        else say(directoryFeedback, "会议室已保存，但目录刷新失败，请手动刷新目录。", true);
      }
    } catch (failure) {
      const error = failure.serverError;
      if (error) {
        say(feedback, `${error.message} 输入已保留。`, true); sessionError(error);
        for (const input of inputs) {
          if (error.fields && typeof error.fields[input.name] === "string") {
            input.setAttribute("aria-invalid", "true"); find(`room-${input.name}-error`).textContent = error.fields[input.name];
            if (focusTarget === feedback) focusTarget = input;
          }
        }
        for (const row of error.conflicts || []) {
          const item = document.createElement("li");
          item.textContent = `预约 ${row.id} · ${row.attendees} 人 · 北京时间 ${row.start_local.replace("T", " ").slice(0,19)} 至 ${row.end_local.replace("T", " ").slice(0,19)} · ${row.status === "in_progress" ? "进行中" : "待开始"}`;
          conflicts.append(item);
        }
      } else {
        say(feedback, "未能确认保存结果，输入已保留。请先刷新目录核对，再手动提交；不会自动重试。", true);
      }
    } finally {
      controls(false); submit.textContent = editing ? "确认保存会议室" : "确认新增会议室";
      if (initiatedHere && canFocus()) focusTarget.focus();
    }
  });
  cancel.addEventListener("click", () => setEditing(null));
  refresh.addEventListener("click", async () => {
    if (busy || blocked) return;
    const initiatedHere = document.activeElement === refresh;
    controls(true); say(directoryFeedback, "正在刷新目录…");
    try { await loadRooms(); }
    catch (error) {
      if (!(error.serverError && sessionError(error.serverError))) {
        say(directoryFeedback, "目录刷新失败，表单输入已保留，请手动重试。", true);
      }
    } finally {
      controls(false);
      if (initiatedHere && (!document.activeElement || document.activeElement === document.body)) {
        (blocked ? directoryFeedback : refresh).focus();
      }
    }
  });
})();
