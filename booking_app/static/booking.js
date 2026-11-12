// Initial creation only. Never automatically resend a request with an unknown result.
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
  let selected, pending = false, unknown = false, completed = false;
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

  function announce(message, error = false) {
    feedback.textContent = message;
    feedback.classList.toggle("error", error);
    feedback.setAttribute("role", error ? "alert" : "status");
    feedback.focus();
  }

  window.selectBookingRoom = (room, query) => {
    if (pending || unknown) return;
    const random = new Uint8Array(32);
    window.crypto.getRandomValues(random);
    selected = {room_id: room.id, start: query.start, end: query.end, attendees: Number(query.attendees),
      intent_key: Array.from(random, value => value.toString(16).padStart(2, "0")).join("")};
    completed = false;
    button.disabled = false;
    button.textContent = "确认预约";
    panel.hidden = false;
    document.querySelector("#booking-conditions").textContent =
      `${room.name} · ${room.location} · ${query.start.replace("T", " ")} — ${query.end.replace("T", " ")}（北京时间） · ${query.attendees} 人`;
    announce("填写活动名称和用途后确认预约。");
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
    if (!selected || pending || unknown || completed) return;
    if (availabilityForm.getAttribute("aria-busy") === "true") {
      announce("可用会议室仍在查询，请稍候再提交预约。");
      return;
    }
    const payload = {...selected, title: form.elements.title.value, purpose: form.elements.purpose.value};
    pending = true;
    button.disabled = true;
    const controls = [...inputs, ...document.querySelectorAll("#availability-form input, #availability-form button, .booking-select")];
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
        announce([error.message, ...otherFields].join(" "), true);
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
      if (response.status !== 201 || !keys(body, ["ok", "data"]) || body.ok !== true
          || !keys(body.data, ["booking", "replayed"]) || body.data.replayed !== false
          || !object(body.data.booking)) throw new Error("Unconfirmed response");
      const booking = body.data.booking;
      if (!Number.isSafeInteger(booking.id) || booking.id < 1
          || typeof booking.title !== "string" || !booking.title.trim() || Array.from(booking.title).length > 80
          || !localTime(booking.start_local) || !localTime(booking.end_local)
          || booking.start_local >= booking.end_local) throw new Error("Unconfirmed response");
      announce(`预约成功 · 编号 ${booking.id} · ${booking.title} · ${booking.start_local.slice(0, 16).replace("T", " ")} — ${booking.end_local.slice(0, 16).replace("T", " ")}（北京时间）`);
      completed = true;
    } catch {
      unknown = true;
      announce("未能确认预约结果，输入已保留。请先通过共享日程或联系管理员核对，勿重复创建。当前版本尚不支持可靠重试。", true);
    } finally {
      window.clearTimeout(timeout);
      pending = false;
      controls.forEach((input, index) => { input.disabled = states[index]; });
      button.disabled = unknown || completed;
      inputs.forEach(input => { input.disabled = unknown || completed; });
      button.textContent = completed ? "已完成预约" : "确认预约";
      form.removeAttribute("aria-busy");
      if (invalidInput) invalidInput.focus();
    }
  });
})();
