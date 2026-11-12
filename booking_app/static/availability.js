// Independent query scope; no write, reservation promise, or automatic retry.
(() => {
  "use strict";
  const form = document.querySelector("#availability-form");
  if (!form) return;
  const names = ["start", "end", "attendees"];
  const inputs = names.map(name => form.elements[name]);
  const button = form.querySelector("button[type=submit]");
  const feedback = document.querySelector("#availability-feedback");
  const results = document.querySelector("#availability-results");
  const items = document.querySelector("#availability-items");
  const conditions = document.querySelector("#availability-conditions");
  const relogin = document.querySelector("#availability-relogin");
  button.disabled = false;

  function announce(message, isError = false) {
    feedback.textContent = message;
    feedback.classList.toggle("error", isError);
    feedback.setAttribute("role", isError ? "alert" : "status");
    if (isError) feedback.focus();
  }

  function addText(parent, tag, value) {
    const child = document.createElement(tag);
    child.textContent = value;
    parent.append(child);
  }

  form.addEventListener("submit", async event => {
    event.preventDefault();
    if (button.disabled) return;
    const query = Object.fromEntries(names.map(name => [name, form.elements[name].value]));
    for (const name of names) {
      form.elements[name].removeAttribute("aria-invalid");
      document.getElementById(`${name}-error`).textContent = "";
    }
    results.hidden = true;
    items.replaceChildren();
    relogin.hidden = true;
    button.disabled = true;
    inputs.forEach(input => { input.disabled = true; });
    button.textContent = "正在查询…";
    form.setAttribute("aria-busy", "true");
    announce("正在查询可用会议室，请稍候…");
    const controller = new AbortController();
    const timeout = window.setTimeout(() => controller.abort(), 20000);
    let invalidInput, succeeded = false;
    try {
      const response = await fetch(`/api/availability?${new URLSearchParams(query)}`, {
        credentials: "same-origin", signal: controller.signal, headers: {Accept: "application/json"},
      });
      const body = await response.json();
      if (!response.ok || !body.ok) {
        const error = body.error || {message: "未能查询可用会议室，请稍后重试。"};
        announce(error.message, true);
        for (const name of names) {
          if (error.fields && error.fields[name]) {
            form.elements[name].setAttribute("aria-invalid", "true");
            document.getElementById(`${name}-error`).textContent = error.fields[name];
          }
        }
        invalidInput = form.querySelector('[aria-invalid="true"]');
        relogin.hidden = error.code !== "AUTH_REQUIRED";
        return;
      }
      conditions.textContent = `${query.start.replace("T", " ")} — ${query.end.replace("T", " ")}（北京时间） · ${query.attendees} 人`;
      for (const room of body.data.items) {
        const row = document.createElement("li");
        addText(row, "h3", room.name);
        addText(row, "p", room.location);
        addText(row, "p", `可容纳 ${room.capacity} 人`);
        if (window.selectBookingRoom) {
          const select = document.createElement("button");
          select.type = "button";
          select.className = "button-secondary booking-select";
          select.textContent = "选择并填写活动";
          select.setAttribute("aria-label", `选择 ${room.name}（${room.location}）并填写活动`);
          select.addEventListener("click", () => window.selectBookingRoom(room, query));
          row.append(select);
        }
        items.append(row);
      }
      results.hidden = false;
      announce(body.data.total ? `找到 ${body.data.total} 间可用会议室。结果仅为查询快照，不保留时段。` : "没有符合条件的会议室，请调整时段或人数后查询。");
      succeeded = true;
    } catch {
      announce(controller.signal.aborted
        ? "查询超时，请稍后重试。查询条件已保留。"
        : "未能查询可用会议室，请检查网络后重试。查询条件已保留。", true);
    } finally {
      window.clearTimeout(timeout);
      button.disabled = false;
      inputs.forEach(input => { input.disabled = false; });
      button.textContent = "查询可用会议室";
      form.removeAttribute("aria-busy");
      if (invalidInput) invalidInput.focus();
      else if (succeeded) button.focus();
    }
  });
})();
