// Successful intents can be confirmed repeatedly; only explicit actions submit requests.
(() => {
  "use strict";
  const form = document.querySelector("#booking-form");
  if (!form) return;
  const panel = document.querySelector("#booking-panel");
  const button = form.querySelector("button[type=submit]");
  const feedback = document.querySelector("#booking-feedback");
  const relogin = document.querySelector("#booking-relogin");
  const availabilityForm = document.querySelector("#availability-form");
  const inputs = [form.elements.title, form.elements.purpose];
  const newButton = document.querySelector("#booking-new");
  let selected, signature, intentKey, pending = false, unknown = false, completed = false;
  let confirmedId, earlierUnknown = false;
  // Python str.strip whitespace: includes C0 separators and NEL, excludes BOM (U+FEFF).
  const strip = value => value.replace(/^[\u0009-\u000d\u001c-\u0020\u0085\u00a0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000]+|[\u0009-\u000d\u001c-\u0020\u0085\u00a0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000]+$/g, "");
  function randomKey() {
    const random = new Uint8Array(32);
    window.crypto.getRandomValues(random);
    return Array.from(random, value => value.toString(16).padStart(2, "0")).join("");
  }
  function currentSignature() {
    return JSON.stringify({...selected, title: strip(form.elements.title.value), purpose: strip(form.elements.purpose.value)});
  }
  function syncIntent() {
    const next = currentSignature();
    if (next === signature) return;
    if (unknown && confirmedId === undefined) earlierUnknown = true;
    signature = next;
    intentKey = randomKey();
    unknown = completed = false;
    confirmedId = undefined;
    button.textContent = "确认预约";
    announce("内容已更改，将提交新预约意图。", false, false);
  }
  inputs.forEach(input => input.addEventListener("input", () => {
    if (selected && !pending) syncIntent();
  }));
  newButton.addEventListener("click", () => {
    if (pending) return;
    if (unknown && confirmedId === undefined) earlierUnknown = true;
    selected = signature = intentKey = undefined;
    unknown = completed = false;
    confirmedId = undefined;
    inputs.forEach(input => { input.value = ""; });
    panel.hidden = true;
    availabilityForm.elements.start.focus();
  });
  const errorStatuses = {INVALID_INPUT: 400, AUTH_REQUIRED: 401, FORBIDDEN: 403, CSRF_REJECTED: 403,
    NOT_FOUND: 404, OCCUPANCY_CONFLICT: 409, CAPACITY_CONFLICT: 409, IDEMPOTENCY_MISMATCH: 409,
    STORE_BUSY: 503, INTERNAL_ERROR: 500};
  const object = value => value !== null && typeof value === "object" && !Array.isArray(value);
  const keys = (value, expected) => object(value) && Object.keys(value).length === expected.length
    && expected.every(name => Object.hasOwn(value, name));
  function localTime(value) {
    if (typeof value !== "string" || !/^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}\+08:00$/.test(value)) return false;
    const epoch = Date.parse(value);
    return Number.isFinite(epoch) && new Date(epoch + 8 * 3600000).toISOString().slice(0, 19) === value.slice(0, 19);
  }

  function validBooking(value) {
    const fullKeys = ["id", "room", "title", "purpose", "attendees", "owner_id", "owner_display_name", "start_at", "start_local",
      "end_at", "end_local", "status", "created_at", "created_local", "cancelled_at", "cancelled_local",
      "cancelled_by_id", "cancelled_by_display_name", "cancel_reason"];
    const positive = number => Number.isSafeInteger(number) && number > 0;
    const pair = (epoch, local) => Number.isSafeInteger(epoch) && localTime(local) && Date.parse(local) / 1000 === epoch;
    if (!keys(value, fullKeys) || !keys(value.room, ["id", "name", "location", "capacity"])
        || ![value.id, value.owner_id, value.attendees, value.room.id, value.room.capacity].every(positive)
        || ![value.room.name, value.room.location, value.purpose, value.owner_display_name].every(text => typeof text === "string")
        || !["pending", "in_progress", "ended", "cancelled"].includes(value.status)
        || !pair(value.start_at, value.start_local) || !pair(value.end_at, value.end_local)
        || !pair(value.created_at, value.created_local)) return false;
    if (value.status === "cancelled") return pair(value.cancelled_at, value.cancelled_local)
      && positive(value.cancelled_by_id) && typeof value.cancelled_by_display_name === "string"
      && (value.cancel_reason === null || typeof value.cancel_reason === "string");
    return [value.cancelled_at, value.cancelled_local, value.cancelled_by_id, value.cancelled_by_display_name,
      value.cancel_reason].every(field => field === null);
  }

  function announce(message, error = false, focus = true) {
    feedback.textContent = message + (earlierUnknown ? " 先前提交的预约结果仍未确认，请核对原安排。" : "");
    feedback.classList.toggle("error", error);
    feedback.setAttribute("role", error ? "alert" : "status");
    if (focus) feedback.focus();
  }

  function unconfirmedMessage() {
    return confirmedId !== undefined
      ? `原预约 #${confirmedId} 已确认，本次当前状态未刷新。请点击「重试确认原预约」。`
      : "原预约结果仍未确认，可能已成功。请点击「重试确认原预约」，相同内容会沿用原提交标识。";
  }

  window.selectBookingRoom = (room, query) => {
    if (pending) return;
    if (!Number.isSafeInteger(room.id) || room.id < 1 || !/^[1-9][0-9]*$/.test(query.attendees)
        || !Number.isSafeInteger(Number(query.attendees))
        || ![query.start, query.end].every(value => typeof value === "string"
          && /^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:(00|30)$/.test(value))) {
      announce("查询结果格式无效，请重新查询会议室。", true);
      return;
    }
    const wasUnknown = unknown;
    selected = {room_id: room.id, start: query.start, end: query.end, attendees: Number(query.attendees)};
    syncIntent();
    button.disabled = false;
    button.textContent = unknown ? "重试确认原预约" : completed ? "再次确认原预约" : "确认预约";
    panel.hidden = false;
    document.querySelector("#booking-conditions").textContent =
      `${room.name} · ${room.location} · ${query.start.replace("T", " ")} — ${query.end.replace("T", " ")}（北京时间） · ${query.attendees} 人`;
    if (!completed && !unknown && !wasUnknown) announce("填写活动名称和用途后确认预约。");
    relogin.hidden = true;
    inputs.forEach(input => { input.disabled = false; });
    for (const name of ["title", "purpose"]) {
      form.elements[name].removeAttribute("aria-invalid");
      document.getElementById(`booking-${name}-error`).textContent = "";
    }
    form.elements.title.focus();
  };

  form.addEventListener("submit", async event => {
    event.preventDefault();
    if (!selected || pending) return;
    if (availabilityForm.getAttribute("aria-busy") === "true") {
      announce("可用会议室仍在查询，请稍候再提交预约。");
      return;
    }
    syncIntent();
    const payload = {...selected, intent_key: intentKey, title: form.elements.title.value, purpose: form.elements.purpose.value};
    pending = true;
    button.disabled = true;
    const controls = [...inputs, newButton, ...document.querySelectorAll("#availability-form input, #availability-form button, .booking-select")];
    const states = controls.map(input => input.disabled);
    controls.forEach(input => { input.disabled = true; });
    form.setAttribute("aria-busy", "true");
    button.textContent = "正在提交…";
    relogin.hidden = true;
    for (const name of ["title", "purpose"]) {
      form.elements[name].removeAttribute("aria-invalid");
      document.getElementById(`booking-${name}-error`).textContent = "";
    }
    announce("正在提交预约，请稍候…");
    const controller = new AbortController();
    const timeout = window.setTimeout(() => controller.abort(), 20000);
    let invalidInput;
    try {
      const response = await fetch("/api/bookings", {
        method: "POST", credentials: "same-origin", signal: controller.signal,
        headers: {"Content-Type": "application/json", "X-CSRF-Token": form.elements.csrf_token.value},
        body: JSON.stringify(payload),
      });
      const body = await response.json();
      if (!response.ok) {
        if (!keys(body, ["ok", "error"]) || body.ok !== false
            || !keys(body.error, ["code", "message", "fields", "conflicts"])
            || !Object.hasOwn(errorStatuses, body.error.code) || errorStatuses[body.error.code] !== response.status
            || typeof body.error.message !== "string" || !body.error.message
            || !object(body.error.fields) || !Object.values(body.error.fields).every(value => typeof value === "string")
            || !Array.isArray(body.error.conflicts)) throw new Error("Unconfirmed response");
        const error = body.error;
        const otherFields = Object.entries(error.fields || {})
          .filter(([name]) => !["title", "purpose"].includes(name)).map(([, message]) => message);
        announce([error.message, ...otherFields, ...(unknown || completed ? [unconfirmedMessage()] : [])].join(" "), true);
        for (const name of ["title", "purpose"]) {
          if (error.fields && error.fields[name]) {
            form.elements[name].setAttribute("aria-invalid", "true");
            document.getElementById(`booking-${name}-error`).textContent = error.fields[name];
            invalidInput ||= form.elements[name];
          }
        }
        relogin.hidden = !["AUTH_REQUIRED", "CSRF_REJECTED"].includes(error.code);
        return;
      }
      if (![200, 201].includes(response.status) || !keys(body, ["ok", "data"]) || body.ok !== true
          || !keys(body.data, ["booking", "replayed"]) || body.data.replayed !== (response.status === 200)
          || !object(body.data.booking)) throw new Error("Unconfirmed response");
      const booking = body.data.booking;
      if (!Number.isSafeInteger(booking.id) || booking.id < 1
          || typeof booking.title !== "string" || !strip(booking.title) || Array.from(booking.title).length > 80
          || !localTime(booking.start_local) || !localTime(booking.end_local)
          || booking.start_local >= booking.end_local) throw new Error("Unconfirmed response");
      if (!validBooking(booking)) throw new Error("Unconfirmed booking contract");
      document.querySelector("#booking-conditions").textContent =
        `${booking.room.name} · ${booking.room.location} · ${booking.start_local.slice(0, 16).replace("T", " ")} — ${booking.end_local.slice(0, 16).replace("T", " ")}（北京时间） · ${booking.attendees} 人`;
      const status = {pending: "待开始", in_progress: "进行中", ended: "已结束", cancelled: "已取消"}[booking.status];
      announce(`${body.data.replayed ? "已确认原预约" : "预约成功"} · ${status} · 编号 ${booking.id} · ${booking.title} · ${booking.start_local.slice(0, 16).replace("T", " ")} — ${booking.end_local.slice(0, 16).replace("T", " ")}（北京时间）`);
      unknown = false;
      completed = true;
      confirmedId = booking.id;
    } catch {
      unknown = true;
      announce(`未能确认预约结果，输入已保留；${unconfirmedMessage()}`, true);
    } finally {
      window.clearTimeout(timeout);
      pending = false;
      controls.forEach((input, index) => { input.disabled = states[index]; });
      button.disabled = false;
      button.textContent = unknown ? "重试确认原预约" : completed ? "再次确认原预约" : "确认预约";
      form.removeAttribute("aria-busy");
      if (invalidInput) invalidInput.focus();
    }
  });
})();
