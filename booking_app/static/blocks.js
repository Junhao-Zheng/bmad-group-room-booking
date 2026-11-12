"use strict";

(() => {
  const find = id => document.getElementById(id), form = find("block-form");
  if (!form) return;
  const inputs = ["room_id", "start", "end", "reason"].map(name => form.elements.namedItem(name));
  const submit = find("block-submit"), confirm = find("block-confirm"), feedback = find("block-feedback");
  const conflicts = find("block-conflicts"), relogin = find("block-relogin"), refresh = find("block-rooms-refresh");
  const statuses = {pending:"待开始", in_progress:"进行中", ended:"已结束", cancelled:"已取消", revoked:"已撤销"};
  let creating = false, refreshing = false, blocked = false, createdMessage = "";
  const cancelForm = find("admin-cancel-form"), cancelReason = find("admin-cancel-reason"), cancelConfirm = find("admin-cancel-confirm");
  const cancelFeedback = find("admin-cancel-feedback");
  let cancelling = false, selectedBooking = null, cancelledMessage = "";
  const revokeForm = find("revoke-form"), revokeReason = find("revoke-reason"), revokeConfirm = find("revoke-confirm");
  const revokeSubmit = find("revoke-submit"), revokeFeedback = find("revoke-feedback");
  let selectButtons = [];
  let revokedMessage = "", revoking = false, selected = null;
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
    const busy = creating || refreshing || revoking || cancelling || lists.some(list => list.busy);
    [...inputs,confirm,submit].forEach(node => { node.disabled = blocked || busy; });
    refresh.disabled = blocked || busy;
    [...selectButtons,revokeReason,revokeConfirm,revokeSubmit].forEach(node => {
      node.disabled = blocked || busy || ([revokeReason,revokeConfirm,revokeSubmit].includes(node) && (!selected || !["pending","in_progress"].includes(selected.status)));
    });
    if (revoking) revokeForm.setAttribute("aria-busy","true"); else revokeForm.removeAttribute("aria-busy");
    if (cancelForm) {
      find("admin-cancel-fields").disabled = blocked || !selectedBooking || busy;
      if (cancelling) cancelForm.setAttribute("aria-busy","true"); else cancelForm.removeAttribute("aria-busy");
    }
    if (creating) form.setAttribute("aria-busy","true"); else form.removeAttribute("aria-busy");
    for (const list of lists) {
      [...fields(list), find(`admin-${list.kind}-submit`), ...list.items.querySelectorAll("button")].forEach(node => { node.disabled = blocked || list.busy || refreshing || creating || cancelling || revoking; });
      if (list.busy) list.form.setAttribute("aria-busy","true"); else list.form.removeAttribute("aria-busy");
    }
  }
  function identityError(error, broadcast = true) {
    if (["AUTH_REQUIRED","FORBIDDEN","CSRF_REJECTED"].includes(error.code)) {
      relogin.hidden = false; find("revoke-relogin").hidden = false;
    }
    if (!["AUTH_REQUIRED","FORBIDDEN"].includes(error.code)) return false;
    const firstLoss = !blocked;
    blocked = true; conflicts.replaceChildren();
    const message = error.code === "AUTH_REQUIRED" ? "登录已失效，请重新登录后打开管理页。" : "当前无管理权限，请以管理员身份重新登录。";
    say(feedback, `${createdMessage}${message} 表单输入已保留，不会自动提交。`, true);
    say(find("block-rooms-feedback"),message,true);
    if (cancelForm) {
      find("admin-cancel-summary").textContent = "";
      find("admin-cancel-relogin").hidden = false;
      say(cancelFeedback,`${cancelledMessage}${message} 原因已保留，不会自动提交。`,true);
    }
    for (const list of lists) { list.items.replaceChildren(); say(list.feedback,message,true); }
    selected = null; selectButtons = []; revokeConfirm.checked = false;
    find("revoke-summary").textContent = "";
    say(revokeFeedback,`${revokedMessage}${message} 撤销原因已保留，不会自动提交。`,true);
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
  function clearCancelTarget(message = "请重新查询并选择预约。") {
    if (!cancelForm) return;
    selectedBooking = null; cancelConfirm.checked = false;
    find("admin-cancel-summary").textContent = "";
    say(cancelFeedback,`${cancelledMessage}${message} 原因草稿已保留。`);
    controls();
  }
  function render(list, records) {
    list.items.replaceChildren();
    if (list.kind === "blocks") selectButtons = [];
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
      item.append(title,detail);
      if (booking && cancelForm && row.status !== "ended") {
        const button = document.createElement("button"); button.type = "button"; button.className = "button-secondary";
        button.textContent = `${row.status === "cancelled" ? "确认取消状态" : "管理员取消"} · 预约 ${row.id}`;
        button.addEventListener("click", () => {
          if (blocked || cancelling || revoking || creating || refreshing || list.busy) return;
          if (!Number.isSafeInteger(row.id)) { clearCancelTarget(); say(list.feedback,"当前浏览器无法安全提交此预约编号。",true); return; }
          selectedBooking = row;
          cancelReason.value = ""; cancelConfirm.checked = false; cancelledMessage = "";
          cancelReason.removeAttribute("aria-invalid"); find("admin-cancel-reason-error").textContent = "";
          find("admin-cancel-panel").hidden = false; find("admin-cancel-relogin").hidden = true;
          find("admin-cancel-summary").textContent = `预约 ${row.id} · ${row.title}\n${row.room.name} · 北京时间 ${formatted(row.start_local)} 至 ${formatted(row.end_local)} · ${statuses[row.status]}`;
          say(cancelFeedback,row.status === "cancelled" ? "此预约已取消。仍须填写合规原因；确认只返回原取消信息，不会覆盖。" : "请填写原因并核对后确认。");
          controls(); cancelReason.focus();
        });
        item.append(button);
      }
      if (!booking && ["pending","in_progress"].includes(row.status) && Number.isSafeInteger(row.id)) {
        const button = document.createElement("button"); button.type = "button"; button.className = "button-secondary";
        button.textContent = `选择撤销停用 ${row.id}`;
        button.addEventListener("click", () => {
          if (blocked || creating || refreshing || revoking || cancelling || lists.some(list => list.busy)) return;
          if (selected?.id !== row.id) revokeReason.value = "";
          selected = row; revokedMessage = ""; revokeConfirm.checked = false; revokeForm.hidden = false;
          revokeReason.removeAttribute("aria-invalid"); find("revoke-reason-error").textContent = "";
          find("revoke-panel").hidden = false; showSelected(); say(revokeFeedback,"");
          controls(); find("revoke-title").focus();
        });
        item.append(button); selectButtons.push(button);
      } else if (!booking && !Number.isSafeInteger(row.id)) {
        const note = document.createElement("p"); note.textContent = "当前浏览器无法安全提交此编号，不能在此撤销该停用。"; item.append(note);
      }
      list.items.append(item);
    }
  }
  async function load(list, automatic = false) {
    if (list.busy || blocked) return;
    if (list.kind === "bookings" && !automatic) clearCancelTarget();
    if (list.kind === "blocks" && !automatic) clearSelected("正在重新查询，请从新结果选择停用；撤销原因草稿已保留。");
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
        say(list.feedback,`${automatic ? `${typeof automatic === "string" ? automatic : (list.kind === "bookings" ? "取消已成功" : "停用已创建")}，但列表刷新失败。` : "管理记录查询失败。"} ${error ? error.message : "请稍后手动查询。"} 筛选条件已保留。`,true);
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
  function clearSelected(message) {
    selected = null; revokedMessage = ""; revokeConfirm.checked = false;
    find("revoke-summary").textContent = "";
    say(revokeFeedback,message); controls();
  }
  for (const list of lists) for (const input of fields(list)) for (const event of ["input","change"]) input.addEventListener(event, () => {
    if (blocked) return;
    list.revision++; list.items.replaceChildren(); clearListErrors(list);
    if (list.kind === "bookings") clearCancelTarget();
    if (list.kind === "blocks") clearSelected("筛选条件已更改，请重新查询并选择停用；撤销原因草稿已保留。");
    say(list.feedback,"筛选条件已更改，请重新查询记录。");
  });
  for (const list of lists) list.form.addEventListener("submit",event => {
    event.preventDefault(); if (!creating && !cancelling && !revoking && !refreshing) return load(list);
  });
  form.addEventListener("submit", async event => {
    event.preventDefault(); if (creating || cancelling || revoking || refreshing || blocked || lists.some(list => list.busy) || !confirm.checked) return;
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
    if (blocked || refreshing || creating || cancelling || revoking || lists.some(list => list.busy)) return;
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
  if (cancelForm) {
    for (const event of ["input","change"]) cancelReason.addEventListener(event, () => { cancelConfirm.checked = false; });
    cancelForm.addEventListener("submit", async event => {
      event.preventDefault();
      if (blocked || cancelling || revoking || creating || refreshing || lists.some(list => list.busy) || !selectedBooking || !cancelConfirm.checked) return;
      const bookingId = selectedBooking.id, initiatedHere = cancelForm.contains(document.activeElement);
      let focusTarget = cancelFeedback;
      cancelledMessage = ""; cancelling = true; controls();
      find("admin-cancel-relogin").hidden = true;
      cancelReason.removeAttribute("aria-invalid"); find("admin-cancel-reason-error").textContent = "";
      say(cancelFeedback,`正在确认取消预约 ${bookingId}，请稍候…`);
      try {
        const record = await request(`/api/admin/bookings/${bookingId}/cancel`,{reason:cancelReason.value});
        if (!recordShape(record,"bookings") || record.id !== bookingId || record.status !== "cancelled") throw new Error("Unconfirmed cancellation");
        cancelledMessage = `预约 ${bookingId} 已取消，时段已释放。`;
        if (blocked) { say(cancelFeedback,`${cancelledMessage} 请重新登录后查看详情。`,true); return; }
        selectedBooking = record; cancelConfirm.checked = false;
        find("admin-cancel-summary").textContent = `预约 ${record.id} · ${record.title} · 已取消\n会议室：${record.room.id} · ${record.room.name} · ${record.room.location}\n预约时段（北京时间）：${formatted(record.start_local)} 至 ${formatted(record.end_local)}\n取消时间（北京时间）：${formatted(record.cancelled_local)}\n操作者：${record.cancelled_by_display_name}\n原取消原因：${record.cancel_reason ?? "本人取消，无原因"}`;
        say(cancelFeedback,`${cancelledMessage} 原取消信息和历史已保留。日程与可用性将在预约页查询时更新。`);
        await load(lists[0],true);
      } catch (failure) {
        const error = failure.serverError;
        if (error) {
          if (!(["AUTH_REQUIRED","FORBIDDEN"].includes(error.code) && identityError(error)) && !blocked) {
            if (["TRANSITION_CLOSED","NOT_FOUND"].includes(error.code)) {
              clearCancelTarget();
              say(cancelFeedback,`${error.message} 请重新查询并选择预约。原因草稿已保留。`,true);
            } else say(cancelFeedback,`${error.message} 原因已保留，可核对后重试。`,true);
            if (error.code === "CSRF_REJECTED") find("admin-cancel-relogin").hidden = false;
            if (error.fields.reason) {
              cancelReason.setAttribute("aria-invalid","true"); find("admin-cancel-reason-error").textContent = error.fields.reason; focusTarget = cancelReason;
            }
          }
        } else if (!blocked) {
          cancelConfirm.checked = false;
          say(cancelFeedback,"未能确认取消结果。原因已保留，请重新勾选确认后重试原预约；不会自动重试。",true);
        }
      } finally {
        cancelling = false; controls();
        if (initiatedHere && focusAllowed(cancelForm)) focusTarget.focus();
      }
    });
  }
  function showSelected() {
    const row = selected;
    find("revoke-summary").textContent = `停用 ${row.id} · ${statuses[row.status]}\n会议室：${row.room.name} · ${row.room.location}\n北京时间：${formatted(row.start_local)} 至 ${formatted(row.end_local)}\n原停用原因：${row.reason}` +
      (row.status === "revoked" ? `\n首次撤销：${formatted(row.revoked_local)}（北京时间） · ${row.revoked_by_id} · ${row.revoked_by_display_name}\n撤销原因：${row.revoke_reason}` : "");
  }
  for (const event of ["input","change"]) revokeReason.addEventListener(event, () => {
    revokeConfirm.checked = false; revokeReason.removeAttribute("aria-invalid"); find("revoke-reason-error").textContent = "";
  });
  revokeForm.addEventListener("submit", async event => {
    event.preventDefault();
    if (!selected || !["pending","in_progress"].includes(selected.status) || !revokeConfirm.checked || blocked || creating || refreshing || revoking || cancelling || lists.some(list => list.busy)) return;
    const blockId = selected.id, initiatedHere = revokeForm.contains(document.activeElement);
    let focusTarget = revokeFeedback;
    revokeReason.removeAttribute("aria-invalid"); find("revoke-reason-error").textContent = "";
    find("revoke-relogin").hidden = true; revoking = true; controls(); say(revokeFeedback,"正在撤销停用，请稍候…");
    try {
      const result = await request(`/api/admin/blocks/${blockId}/revoke`, {reason:revokeReason.value});
      if (!recordShape(result,"blocks") || result.id !== blockId || result.status !== "revoked") throw new Error("Invalid revoked block");
      revokedMessage = `停用 ${result.id} 已撤销，全部占用已释放。`;
      if (blocked) {
        say(revokeFeedback,`${revokedMessage}请重新登录查看首次撤销信息。撤销原因草稿已保留。`);
        return;
      }
      selected = result; revokeConfirm.checked = false; revokeForm.hidden = true; showSelected();
      say(revokeFeedback,`${revokedMessage}首次撤销信息已显示。`);
      await load(lists[1],"停用已撤销");
    } catch (failure) {
      const error = failure.serverError;
      if (error && identityError(error)) return;
      if (!blocked) {
        revokeConfirm.checked = false;
        if (["TRANSITION_CLOSED","NOT_FOUND"].includes(error?.code)) {
          clearSelected(`${error.message} 请重新查询并选择有效停用；撤销原因已保留。`);
          say(revokeFeedback,revokeFeedback.textContent,true);
          return;
        }
        say(revokeFeedback,error ? `${error.message} 撤销原因已保留，请核对后重新确认。` :
          "未能确认撤销结果，撤销原因已保留。请查询记录核对；也可重新确认后重试，已撤销记录会返回首次结果。",true);
        if (error?.fields.reason) {
          revokeReason.setAttribute("aria-invalid","true"); find("revoke-reason-error").textContent = error.fields.reason; focusTarget = revokeReason;
        }
      }
    } finally {
      revoking = false; controls();
      if (initiatedHere && focusAllowed(revokeForm)) focusTarget.focus();
    }
  });
  controls();
  find("block-script-unavailable").hidden = true;
  find("block-fields").disabled = false;
})();
