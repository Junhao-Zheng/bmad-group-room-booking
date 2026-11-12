// Personal data stays text; cancellation always requires explicit confirmation.
(() => {
  "use strict";
  const form = document.querySelector("#history-form");
  if (!form) return;
  const select = form.elements.status;
  const submit = form.querySelector("button[type=submit]");
  const items = document.querySelector("#history-items");
  const feedback = document.querySelector("#history-feedback");
  const statusError = document.querySelector("#history-status-error");
  const relogin = document.querySelector("#history-relogin");
  const panel = document.querySelector("#history-detail");
  const detailTitle = document.querySelector("#detail-title");
  const detailFeedback = document.querySelector("#detail-feedback");
  const detailFields = document.querySelector("#detail-fields");
  const detailRelogin = document.querySelector("#detail-relogin");
  const retry = document.querySelector("#detail-retry");
  const cancelForm = document.querySelector("#cancel-form");
  const confirm = document.querySelector("#cancel-confirm");
  const cancelSubmit = document.querySelector("#cancel-submit");
  const cancelFeedback = document.querySelector("#cancel-feedback");
  const csrf = document.querySelector("#logout-form").elements.csrf_token.value;
  const labels = {pending: "待开始", in_progress: "进行中", ended: "已结束", cancelled: "已取消"};
  let busy = false, selectedId;

  function announce(node, message, error = false, focus = error) {
    node.textContent = message;
    node.classList.toggle("error", error);
    node.setAttribute("role", error ? "alert" : "status");
    if (focus) node.focus();
  }
  function text(parent, tag, value, className) {
    const node = document.createElement(tag);
    node.textContent = value;
    if (className) node.className = className;
    parent.append(node);
    return node;
  }
  function local(value) { return value.replace("T", " ").replace("+08:00", ""); }
  function lock(value) {
    busy = value;
    select.disabled = value;
    submit.disabled = value;
    retry.disabled = value;
    confirm.disabled = value;
    cancelSubmit.disabled = value;
    for (const button of items.querySelectorAll("button")) button.disabled = value;
  }
  function resetDetail() {
    selectedId = undefined;
    cancelForm.hidden = true;
    confirm.checked = false;
    announce(cancelFeedback, "");
    detailFields.hidden = true;
    detailFields.replaceChildren();
    retry.hidden = true;
    detailRelogin.hidden = true;
    announce(detailFeedback, "选择一条预约查看完整信息。");
  }
  function responseData(response, body) {
    const object = value => value !== null && typeof value === "object" && !Array.isArray(value);
    if (object(body) && response.ok && body.ok === true && Object.hasOwn(body, "data")) return body.data;
    const error = object(body) && body.error;
    if (object(body) && body.ok === false && object(error) && typeof error.code === "string" && error.code &&
        typeof error.message === "string" && error.message && object(error.fields) &&
        Object.values(error.fields).every(value => typeof value === "string") && Array.isArray(error.conflicts)) {
      throw {api: true, code: error.code, message: error.message, fields: error.fields, conflicts: error.conflicts};
    }
    throw new Error("Unconfirmed response envelope");
  }
  async function request(url, signal) {
    const response = await fetch(url, {credentials: "same-origin", signal, headers: {Accept: "application/json"}});
    return responseData(response, await response.json());
  }
  function expired(error, origin, cancellationSucceeded = false, focus = true) {
    if (error.code !== "AUTH_REQUIRED") return false;
    items.replaceChildren();
    cancelForm.hidden = true;
    announce(cancelFeedback, "");
    detailFields.replaceChildren();
    detailFields.hidden = true;
    retry.hidden = true;
    relogin.hidden = false;
    detailRelogin.hidden = false;
    const message = cancellationSucceeded ? "取消已成功，但刷新时登录已失效；预约列表与详情已清空，请重新登录后查看。" :
      "登录已失效，预约列表与详情已清空。请重新登录后点击“查看预约”。";
    announce(feedback, message, true, false);
    announce(detailFeedback, message, true, false);
    if (cancellationSucceeded) announce(cancelFeedback, message);
    if (focus) origin.focus();
    return true;
  }
  function renderList(result) {
    items.replaceChildren();
      for (const booking of result.items) {
        const row = document.createElement("li");
        text(row, "span", labels[booking.status], "schedule-status");
        text(row, "h3", booking.title);
        text(row, "p", `${booking.room.name} · ${booking.room.location}`);
        text(row, "p", `${local(booking.start_local)} — ${local(booking.end_local)}`);
        const button = text(row, "button", `查看详情 · 编号 ${booking.id}`, "button-secondary");
        button.type = "button";
        button.setAttribute("aria-label", `查看预约详情：${booking.title}（编号 ${booking.id}）`);
        button.addEventListener("click", () => loadDetail(booking.id));
        items.append(row);
      }
  }
  function listMessage(result, status) {
    return (result.total ? `查询成功，共 ${result.total} 条${status ? labels[status] : ""}预约。` :
      (status ? `暂无${labels[status]}的预约。可选择其他状态查看。` : "你还没有预约记录，可从“预约”页面创建活动。")) +
      " 列表是本次查询的状态快照；点击“查看预约”可刷新。";
  }
  async function loadList(event) {
    if (event) event.preventDefault();
    if (busy) return;
    const status = select.value;
    items.replaceChildren();
    resetDetail();
    relogin.hidden = true;
    select.removeAttribute("aria-invalid");
    statusError.textContent = "";
    lock(true);
    form.setAttribute("aria-busy", "true");
    announce(feedback, "正在查询我的预约，请稍候…");
    const controller = new AbortController();
    const timeout = window.setTimeout(() => controller.abort(), 20000);
    let invalid = false, succeeded = false;
    try {
      const result = await request(`/api/bookings/mine${status ? `?${new URLSearchParams({status})}` : ""}`, controller.signal);
      renderList(result);
      succeeded = true;
      announce(feedback, listMessage(result, status));
    } catch (error) {
      announce(feedback, error.api ? error.message : "未能查询预约，请检查网络后重试。筛选条件已保留。", true);
      expired(error, feedback);
      if (error.fields && error.fields.status) {
        select.setAttribute("aria-invalid", "true");
        statusError.textContent = error.fields.status;
        invalid = true;
      }
    } finally {
      window.clearTimeout(timeout);
      form.removeAttribute("aria-busy");
      lock(false);
      if (invalid) select.focus();
      else if (succeeded && event && (!document.activeElement || document.activeElement === document.body ||
        document.activeElement === submit || document.activeElement === feedback)) submit.focus();
    }
  }
  function renderDetail(booking) {
    if (![booking.attendees, booking.room?.capacity].every(value => Number.isInteger(value) && value > 0))
      throw new Error("Incomplete booking quantities");
    const cancelled = booking.cancelled_at !== null;
    const fields = [
      ["预约编号", booking.id], ["活动名称", booking.title], ["用途", booking.purpose],
      ["预计人数", `${booking.attendees} 人`], ["会议室", booking.room.name],
      ["会议室编号", booking.room.id], ["位置", booking.room.location], ["当前容量", `${booking.room.capacity} 人`],
      ["预约人", booking.owner_display_name], ["预约人编号", booking.owner_id],
      ["开始时间（北京时间）", local(booking.start_local)], ["结束时间（北京时间）", local(booking.end_local)],
      ["状态", labels[booking.status]], ["创建时间（北京时间）", local(booking.created_local)],
      ["取消时间（北京时间）", cancelled ? local(booking.cancelled_local) : "未取消"],
      ["取消操作者", cancelled ? booking.cancelled_by_display_name : "无（未取消）"],
      ["取消操作者编号", cancelled ? booking.cancelled_by_id : "无（未取消）"],
      ["取消原因", cancelled ? (booking.cancel_reason === null ? "未填写（本人取消无需原因）" : booking.cancel_reason) : "无（未取消）"],
    ];
    if (fields.some(([, value]) => !["string", "number"].includes(typeof value)))
      throw new Error("Incomplete booking response");
    detailFields.replaceChildren();
    for (const [label, value] of fields) { text(detailFields, "dt", label); text(detailFields, "dd", value); }
    detailFields.hidden = false;
    cancelForm.hidden = !["pending", "cancelled"].includes(booking.status);
    confirm.checked = false;
    cancelSubmit.textContent = booking.status === "cancelled" ? "再次确认取消状态" : "确认取消本预约";
    announce(cancelFeedback, booking.status === "cancelled" ? "此预约已取消，再次确认不会改变原取消信息。" :
    (booking.status === "pending" ? "" : "预约已开始或结束，不能取消。"));
  }
  async function loadDetail(id) {
    if (busy) return;
    const initiatingFocus = document.activeElement;
    selectedId = id;
    cancelForm.hidden = true;
    announce(cancelFeedback, "");
    detailFields.replaceChildren();
    detailFields.hidden = true;
    retry.hidden = true;
    detailRelogin.hidden = true;
    lock(true);
    panel.setAttribute("aria-busy", "true");
    announce(detailFeedback, `正在读取预约 ${id} 的详情…`);
    const controller = new AbortController();
    const timeout = window.setTimeout(() => controller.abort(), 20000);
    try {
      const booking = await request(`/api/bookings/${id}`, controller.signal);
      if (!booking || booking.id !== id) throw new Error("Mismatched booking detail");
      renderDetail(booking);
      announce(detailFeedback, `已读取预约 ${booking.id} 的完整详情。状态以本次读取为准，可能与列表快照不同；点击“查看预约”刷新列表。`);
      if (!document.activeElement || document.activeElement === document.body ||
        document.activeElement === initiatingFocus) detailTitle.focus();
    } catch (error) {
      announce(detailFeedback, error.api ? error.message : "未能读取详情，请检查网络后重试。", true);
      if (!expired(error, detailFeedback)) retry.hidden = false;
    } finally {
      window.clearTimeout(timeout);
      panel.removeAttribute("aria-busy");
      lock(false);
    }
  }
  async function cancelBooking(event) {
    event.preventDefault();
    if (busy || cancelForm.hidden || selectedId === undefined || !confirm.checked) return;
    const id = selectedId;
    let focusTarget = cancelFeedback;
    lock(true);
    cancelForm.setAttribute("aria-busy", "true");
    announce(cancelFeedback, `正在确认取消预约 ${id}，请稍候…`);
    const controller = new AbortController();
    const timeout = window.setTimeout(() => controller.abort(), 20000);
    try {
      const response = await fetch(`/api/bookings/${id}/cancel`, {
        method: "POST", credentials: "same-origin", signal: controller.signal,
        headers: {"Content-Type": "application/json", Accept: "application/json", "X-CSRF-Token": csrf}, body: "{}",
      });
      const booking = responseData(response, await response.json());
      if (!booking || booking.id !== id || booking.status !== "cancelled" || !Number.isInteger(booking.cancelled_at) || !Number.isInteger(booking.cancelled_by_id))
        throw new Error("Unconfirmed cancellation response");
      renderDetail(booking);
      announce(detailFeedback, `预约 ${id} 已取消，详情已更新。`);
      announce(cancelFeedback, `预约 ${id} 已取消，时段已释放；取消信息和历史已保留。`);
      // A failed follow-up read must never misreport a committed cancellation as failed.
      try {
        const status = select.value;
        const result = await request(`/api/bookings/mine${status ? `?${new URLSearchParams({status})}` : ""}`, controller.signal);
        renderList(result);
        announce(feedback, `${listMessage(result, status)} 取消后列表已刷新，日程和可用性将在进入预约页查询时更新。`);
      } catch (error) {
        if (expired(error, detailFeedback, true, false)) focusTarget = detailFeedback;
        else announce(feedback, "取消已成功，但列表刷新失败。请点击“查看预约”刷新。", true, false);
      }
    } catch (error) {
      if (expired(error, detailFeedback, false, false)) focusTarget = detailFeedback;
      else {
        announce(cancelFeedback, error.api ? `${error.message} 当前详情已保留，可重新查看最新状态。` :
          `未能确认预约 ${id} 的取消结果。原记录已保留，请点击“重试确认原预约取消”；不会自动重试。`, true, false);
        cancelSubmit.textContent = error.api ? "重试取消本预约" : "重试确认原预约取消";
      }
    } finally {
      window.clearTimeout(timeout);
      cancelForm.removeAttribute("aria-busy");
      lock(false);
      // Restore focus lost by disabling this operation, but preserve a move to another form.
      if (!document.activeElement || document.activeElement === document.body ||
          [confirm, cancelSubmit, cancelFeedback, detailFeedback].includes(document.activeElement)) focusTarget.focus();
    }
  }
  cancelForm.addEventListener("submit", cancelBooking);
  form.addEventListener("submit", loadList);
  retry.addEventListener("click", () => loadDetail(selectedId));
  loadList();
})();
