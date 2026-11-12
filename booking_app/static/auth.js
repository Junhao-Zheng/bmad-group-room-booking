"use strict";

const loginForm = document.querySelector("#login-form");
const logoutForm = document.querySelector("#logout-form");
const feedback = document.querySelector("#auth-feedback");
const relogin = document.querySelector("#relogin-link");

function showFeedback(message, isError = false) {
  feedback.textContent = message;
  feedback.classList.toggle("error", isError);
  feedback.setAttribute("role", isError ? "alert" : "status");
  if (isError) feedback.focus();
}

async function submitAuth(form, endpoint, values, successUrl) {
  const button = form.querySelector("button[type=submit]");
  if (button.disabled) return;
  const inputs = form === loginForm ? [form.elements.username, form.elements.password] : [];
  const oldLabel = button.textContent;
  button.disabled = true;
  inputs.forEach(input => { input.disabled = true; });
  button.textContent = "正在提交…";
  form.setAttribute("aria-busy", "true");
  relogin.hidden = true;
  showFeedback("正在验证，请稍候…");
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), 20000);
  let invalidInput;
  try {
    const response = await fetch(endpoint, {
      method: "POST",
      credentials: "same-origin",
      signal: controller.signal,
      headers: {"Content-Type": "application/json", "X-CSRF-Token": form.elements.csrf_token.value},
      body: JSON.stringify(values),
    });
    const body = await response.json();
    if (!response.ok || !body.ok) {
      const error = body.error || {message: "操作未完成，请稍后重试。", fields: {}};
      showFeedback(error.message, true);
      for (const [name, message] of Object.entries(error.fields || {})) {
        const input = form.elements.namedItem(name);
        const hint = document.getElementById(`${name}-error`);
        if (input && hint) {
          input.setAttribute("aria-invalid", "true");
          hint.textContent = message;
        }
      }
      invalidInput = form.querySelector('[aria-invalid="true"]');
      if (["AUTH_REQUIRED", "CSRF_REJECTED"].includes(error.code)) relogin.hidden = false;
      return;
    }
    showFeedback(form === loginForm ? "登录成功，正在打开首页…" : "已退出登录。");
    window.location.assign(successUrl);
  } catch {
    showFeedback("未能确认操作结果，请检查网络后手动重试或重新打开页面。", true);
    relogin.hidden = false;
  } finally {
    window.clearTimeout(timeout);
    button.disabled = false;
    inputs.forEach(input => { input.disabled = false; });
    button.textContent = oldLabel;
    form.removeAttribute("aria-busy");
    if (invalidInput) invalidInput.focus();
  }
}

if (loginForm) loginForm.addEventListener("submit", (event) => {
  event.preventDefault();
  if (loginForm.querySelector("button[type=submit]").disabled) return;
  for (const name of ["username", "password"]) {
    loginForm.elements[name].removeAttribute("aria-invalid");
    document.getElementById(`${name}-error`).textContent = "";
  }
  submitAuth(loginForm, "/api/login", {
    username: loginForm.elements.username.value,
    password: loginForm.elements.password.value,
  }, "/");
});

if (logoutForm) logoutForm.addEventListener("submit", (event) => {
  event.preventDefault();
  submitAuth(logoutForm, "/api/logout", {}, "/login?logged_out=1");
});
