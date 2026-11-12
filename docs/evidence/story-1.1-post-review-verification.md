# Story 1.1 评审修订验证

日期：2026-11-12；执行者：Codex AI。以下仅为修订后的定向技术验证，不是人工或教师验收。

## 变更与测试边界

- 初始化和登录共用账号 256 / 密码 1024 UTF-8 字节上限。初始化继续要求密码至少 12 字符；登录中的普通错误短密码仍为 401，不改变“账号或密码错误”文案。多字节字符恰好达到 256/1024 字节可初始化并登录；超限或孤立 Unicode surrogate 返回受控错误，数据不变。
- APP_ORIGIN 读取并验证数字端口，拒绝空端口、非数字、0、负值和超过 65535；HTTP 80 / HTTPS 443 省略。测试不仅检查保存的配置，还以规范化 Origin 发起 Flask HTTP 请求，实际完成登录和 `/api/me`；loopback / HTTPS Secure 检查保留。
- 实际子进程执行初始化 CLI：数组/null/字符串/数字/bool 顶层 JSON、644 权限私有文件均退出 1，无 traceback、无输入密码输出、数据库不变。脱离控制终端且 stdin 为管道时，GetPassWarning 转为受控失败并给出 `--credentials-file` 与权限 600 指引；不进行回显输入回退。
- 交互页面的 noscript 文案明确需要 JavaScript；表单 API 仍返回 JSON。请求采用 20 秒 AbortController，计时覆盖 fetch 响应头等待及 `response.json()` 正文读取。Node 用可控计时器分别冻结这两个阶段，断言定时值 20000 毫秒、取消信号、恢复按钮/aria-busy、显示结果未确认、总请求数仍为 1。未用真实网络等待 20 秒，也未把超时解释为服务端一定失败。
- 原“commit failure”用例准确更名为提交前失败。新增代理连接在实际 `execute("COMMIT")` 调用处抛 sqlite3.OperationalError，记录调用顺序为 COMMIT→ROLLBACK；三条认证写路径的数据与 cookie 均保持原状态。
- 浏览器检查从忽略的 work 脚本迁入 `scripts/verify_auth_browser.py` / `.cjs`。启动器生成权限 600 的临时随机凭证，创建独立临时 DB，自动启停 Waitress；外部 Playwright 固定 1.58.2，可用其 Chromium 或显式传入已有浏览器可执行文件。代码没有机器专用绝对路径，README 提供安装/运行方法。
- 新机器说明使用 `uv python install 3.12.14` 和 `uv sync --frozen --python 3.12.14`，不再假设工具 venv 的 Python 满足应用要求；实际 SQLite ≥3.51.3 启动检查保留。本次未重新安装解释器。

## 实际执行命令

```bash
PYTHONPATH=tests .venv/bin/python -m unittest -v \
  test_auth.AuthTests.test_shared_credential_byte_boundaries_can_initialize_and_login \
  test_auth.AuthTests.test_login_rejects_oversize_and_invalid_unicode_without_state_change \
  test_auth.AuthTests.test_initialization_rejects_oversize_and_invalid_unicode_before_database_changes \
  test_auth.AuthTests.test_cli_rejects_nonobject_json_without_traceback_or_secret_output \
  test_auth.AuthTests.test_cli_rejects_readable_credentials_file_without_database_changes \
  test_auth.AuthTests.test_cli_rejects_unavailable_hidden_input_with_private_file_guidance \
  test_auth.AuthTests.test_origin_validates_ports_and_matches_browser_default_port_requests \
  test_auth.AuthTests.test_runtime_configuration_guards \
  test_auth.AuthTests.test_execute_commit_failure_rolls_back_and_never_issues_or_clears_cookie \
  test_auth.AuthTests.test_pre_commit_failure_rolls_back_login_logout_and_preauth_without_cookie \
  test_auth.AuthTests.test_invalid_credentials_use_identical_error_and_do_not_change_data \
  test_auth.AuthTests.test_initialization_rejects_invalid_accounts_without_creating_database \
  test_auth.AuthTests.test_noscript_notice_requires_javascript_without_changing_json_api
node --test tests/test_auth_js.cjs
.venv/bin/python -m scripts.verify_auth_browser \
  --playwright-root /Users/mima0000/.npm/_npx/520e866687cefe78/node_modules \
  --browser-executable '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome' \
  --output-dir docs/evidence/story-1.1-post-review-browser
```

最后一条记录本次实际环境的显式参数；交付脚本自身没有这些机器路径，README 的默认命令使用项目内外部工具目录与 Playwright Chromium。本次复用已经安装的 Playwright 1.58.2 和 Chrome 157.0.8103.51，没有新增应用依赖。

## 结果

- [13 项 Python 定向测试](story-1.1-post-review-tests.txt)：全部通过，0 skip。
- [2 项 JS 超时测试](story-1.1-post-review-js-tests.txt)：全部通过。
- [浏览器机器可读结果](story-1.1-post-review-browser/browser-results.json)：1280×800 与 390×844 的键盘登录/退出、身份 API、退出后匿名与旧 cookie 拒绝、空字段反馈、label、宽度全部通过，0 pageerror。Waitress 使用 127.0.0.1:8002、单进程 8 线程，已停止，临时数据已清理。
- 新截图：[桌面登录](story-1.1-post-review-browser/login-1280.png)、[桌面身份](story-1.1-post-review-browser/home-1280.png)、[手机登录](story-1.1-post-review-browser/login-390.png)、[手机身份](story-1.1-post-review-browser/home-390.png)。

初次全量结果及 HTTP/浏览器证据保持原样。完整回归由主代理随后执行，当前记录不把这 13 项定向测试表述为全量验证。
