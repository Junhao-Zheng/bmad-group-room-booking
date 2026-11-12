# Story 2.2 验证记录

执行日期：2026-11-12。实现 FR-12/22、NFR-01/04、ADR-04 及 UX-DR5/10。所有账号、活动和历史夹具均为合成数据；这份记录是 AI 实施/自动化验证证据，不是成员试用、教师评审或实验 A 结果。

## 结果

- Python 全量：**90 个测试，90 个唯一测试标识，通过，无 skip**。新增 `ReplayIntentTests` 的 9 项测试直接继承 `unittest.TestCase`，仅复用夹具/辅助函数，没有继承已有测试类。原始输出：[Python](story-2.2-python-tests.txt)。
- JavaScript 全量：**27 个测试，通过，无 skip**；其中 13 项执行真实 `booking.js`/`availability.js` 处理器，覆盖原键重试、输入/选择变化、Python 空白兼容、严格响应合同及响应头/正文超时。原始输出：[JavaScript](story-2.2-javascript-tests.txt)。
- 同用户同 key 的真实 20 并发：**1×201 + 19×200**，20 个独立客户端和 CookieJar，全部返回同一 ID；数据库最终 **1 预约、4 个半小时槽、1 条创建审计**。实际停止并重启进程后仍能重放；故障 writer 不影响重放，新建触发的审计故障整体回滚，失败 key 在再次重启后可重用。
- 原创建回归：真实 20 个不同成员争用同槽仍为 **1×201 + 19×409 OCCUPANCY_CONFLICT**，无 503 替代冲突；审计故障与重启断言通过。
- Chrome **157.0.8103.51**、Playwright **1.58.2**，真实 **1280×800、390×844**：正常创建、占用拒绝、原成功预约再次确认、首次成功响应被截断后原键重试、实质编辑新意图、显式开始新预约、登录退出与查询/共享日程回归通过；无页面错误、无横向溢出。完整响应白名单、纯文本及最终真实文件库检查通过。

## 验收矩阵

| 验收 | 执行断言与证据 |
| --- | --- |
| AC-2.2-1 | Python 全 Unicode `isspace` 首尾空白重放，精确 `BookingFull` 与原 ID；比较预约/槽/审计完整快照零变化，故障 writer 确认零调用。JS 的 U+0085、U+001C—1F 保留 key，U+FEFF 换 key。 |
| AC-2.2-2 | 合规直接夹具设置取消、开始/结束与结束后降容量；返回当前状态、当前目录/显示名和保存的取消事实；替换所有六字段均先返回 409，跨用户同 key 只得到共享冲突或其自己的新记录；取锁后重新授权，过期/伪造 actor 不能重放。 |
| AC-2.2-3 | 无效文本/人数/房间/占用失败未占 key；HTTP 20 同意图全部原 ID，只有一次创建；审计故障与两个真实进程重启中保存原意图及失败 key 重用。见 [并发/重启结果](story-2.2-http/replay-http-result.json)。 |
| AC-2.2-4 | 两种视口均先 `route.fetch()` 得到真实 201，再 `route.abort()` 丢失响应；表单显示未知。首尾等价空白编辑后主动重试得到 200 与原 ID、相同 key 哈希；实质编辑及新时段得到 201、新 ID、新 key 哈希。提交期间禁用相关控件；正常成功不清空表单，重复确认仍原 ID；显式「开始新预约」才清空表单。 |

## 原始证据

- [HTTP 全部 20 个响应](story-2.2-http/replay-http-responses.jsonl)、[竞争后数据库](story-2.2-http/replay-http-storage.json)、[重启/故障各响应](story-2.2-http/replay-http-restart-fault-responses.json)、[最终数据库](story-2.2-http/replay-http-final-storage.json)、[环境/源码 SHA-256](story-2.2-http/replay-http-environment.json)、[运行输出](story-2.2-http-run.txt)。预约 key 仅存 SHA-256；不输出 cookie、CSRF、口令、session token/hash。
- [原创建并发回归结果](story-2.2-create-regression/create-http-result.json)、[原始响应](story-2.2-create-regression/create-http-responses.jsonl)、[运行输出](story-2.2-create-regression-run.txt)。其中意图键为公开合成夹具，不是会话凭证。
- [浏览器完整断言与最终存储校验](story-2.2-browser/browser-results.json)、[桌面原始网络](story-2.2-browser/replay-network-1280.jsonl)、[手机原始网络](story-2.2-browser/replay-network-390.jsonl)、[运行输出](story-2.2-browser-run.txt)。网络记录保留每次实际业务请求字段、状态、完整 JSON 响应、交付动作和安全的 key 哈希，不保存认证头。
- 桌面：[未知结果](story-2.2-browser/booking-committed-response-lost-1280.png)、[重放确认](story-2.2-browser/booking-replayed-1280.png)、[新意图](story-2.2-browser/booking-new-intent-1280.png)、[占用拒绝](story-2.2-browser/booking-conflict-1280.png)。
- 手机：[未知结果](story-2.2-browser/booking-committed-response-lost-390.png)、[重放确认](story-2.2-browser/booking-replayed-390.png)、[新意图](story-2.2-browser/booking-new-intent-390.png)、[占用拒绝](story-2.2-browser/booking-conflict-390.png)。已对自动化生成的桌面/手机重放截图进行 AI 视觉检查；布局正常，不代表人类验收。

## 复跑命令与边界

在应用目录运行，浏览器外部工具安装方式见 README。所有脚本使用独立临时文件库；HTTP 用随机空闲 loopback 端口，浏览器用 8002。临时密码只保存在内存或权限 600 文件，结束时自动清理。

```bash
.venv/bin/python -m unittest discover -s tests -v
node --test tests/test_*js.cjs
.venv/bin/python -m scripts.verify_replay_intent_http --output-dir work/replay-intent-http
.venv/bin/python -m scripts.verify_create_booking_http --output-dir work/create-booking-regression
.venv/bin/python -m scripts.verify_auth_browser --replay --output-dir work/replay-intent-browser
```

本机浏览器实际使用附加参数 `--browser-executable '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'`；默认也支持已安装的 Playwright Chromium。HTTP 环境记录 Python 3.12.14、SQLite 3.53.1、Flask 3.1.3、Jinja2 3.1.6、Werkzeug 3.1.9、Waitress 3.0.2，单进程/8 线程，Apple M1 Pro、8 逻辑 CPU、32 GiB 内存。

取消、管理员干预、容量管理及个人预约页面未在本故事交付；历史状态仅由测试夹具构造，未暴露测试 HTTP 后门。浏览器意图保留属于当前打开的表单；未新增跨页面刷新草稿恢复功能。所有规定验证均已完成，没有未完成验收项。
