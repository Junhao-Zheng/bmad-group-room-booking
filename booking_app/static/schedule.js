// Keep authentication and schedule names isolated; render all shared data as text.
(() => {
  "use strict";
  const form = document.querySelector("#schedule-form");
  if (!form) return;
  const inputs = [form.elements.room_id, form.elements.date];
  form.querySelector("button[type=submit]").disabled = form.elements.room_id.disabled;
  const feedback = document.querySelector("#schedule-feedback");
  const results = document.querySelector("#schedule-results");
  const items = document.querySelector("#schedule-items");
  const conditions = document.querySelector("#schedule-conditions");
  const relogin = document.querySelector("#schedule-relogin");
  const labels = {pending: "待开始", in_progress: "进行中", ended: "已结束"};

  function announce(message, isError = false) {
    feedback.textContent = message;
    feedback.classList.toggle("error", isError);
    feedback.setAttribute("role", isError ? "alert" : "status");
    if (isError) feedback.focus();
  }

  function addText(parent, tag, value, className) {
    const node = document.createElement(tag);
    node.textContent = value;
    if (className) node.className = className;
    parent.append(node);
  }

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const button = form.querySelector("button[type=submit]");
    if (button.disabled) return;
    const roomId = form.elements.room_id.value;
    const date = form.elements.date.value;
    const roomLabel = form.elements.room_id.selectedOptions[0].textContent;
    for (const name of ["room_id", "date"]) {
      form.elements[name].removeAttribute("aria-invalid");
      document.getElementById(`${name}-error`).textContent = "";
    }
    results.hidden = true;
    items.replaceChildren();
    relogin.hidden = true;
    button.disabled = true;
    for (const input of inputs) input.disabled = true;
    button.textContent = "正在查询…";
    form.setAttribute("aria-busy", "true");
    announce("正在查询日程，请稍候…");
    const controller = new AbortController();
    const timeout = window.setTimeout(() => controller.abort(), 20000);
    let invalidInput, succeeded = false;
    try {
      const params = new URLSearchParams({room_id: roomId, date});
      const response = await fetch(`/api/schedule?${params}`, {
        credentials: "same-origin", signal: controller.signal, headers: {Accept: "application/json"},
      });
      const body = await response.json();
      if (!response.ok || !body.ok) {
        const error = body.error || {message: "未能查询日程，请稍后重试。"};
        announce(error.message, true);
        for (const [name, message] of Object.entries(error.fields || {})) {
          const input = form.elements.namedItem(name);
          const hint = document.getElementById(`${name}-error`);
          if (input && hint) {
            input.setAttribute("aria-invalid", "true");
            hint.textContent = message;
          }
        }
        invalidInput = form.querySelector('[aria-invalid="true"]');
        relogin.hidden = error.code !== "AUTH_REQUIRED";
        return;
      }
      if (!body.data || !Array.isArray(body.data.items) || body.data.total !== body.data.items.length || !body.data.items.every(window.BookingContracts.schedule)) throw new Error("Invalid schedule contract");
      conditions.textContent = `${roomLabel} · ${date}（北京时间）`;
      for (const item of body.data.items) {
        const record = item.record;
        const row = document.createElement("li");
        addText(row, "span", `${item.kind === "booking" ? "预约" : "停用"} · ${labels[record.status]}`, "schedule-status");
        addText(row, "h4", item.kind === "booking" ? record.title : "会议室停用");
        addText(row, "p", `${record.start_local.slice(0, 16).replace("T", " ")} — ${record.end_local.slice(0, 16).replace("T", " ")}`);
        addText(row, "p", item.kind === "booking" ? `预约人：${record.owner_display_name}` : `原因：${record.reason}`, "muted");
        if (item.kind === "booking") addText(row, "p", `所属导师：${record.supervisor_display_name ?? (record.supervisor_source === "admin" ? "管理员安排" : "历史未绑定")}`, "muted");
        items.append(row);
      }
      results.hidden = false;
      announce(body.data.total ? `查询成功，共 ${body.data.total} 项安排。` : "当天暂无预约或停用安排。");
      succeeded = true;
    } catch {
      announce("未能查询日程，请检查网络后重试。查询条件已保留。", true);
    } finally {
      window.clearTimeout(timeout);
      button.disabled = false;
      for (const input of inputs) input.disabled = false;
      button.textContent = "查看日程";
      form.removeAttribute("aria-busy");
      if (invalidInput) invalidInput.focus();
      else if (succeeded && (document.activeElement === document.body || document.activeElement === feedback || form.contains(document.activeElement))) button.focus();
    }
  });
})();
