# 4.2 学生申请与本人导师审批验证

2026-11-15，工作区代码，无 commit/push，无正式部署。以下为自动测试证据，不是正式演示或人工验收。

## 核心测试

实际执行（从 `outputs/group-room-booking`，本机 `uv` 不在 PATH，使用已有 Python 3.12.14 虚拟环境）：

```text
.venv/bin/python -m unittest tests.test_supervised_booking -q
Ran 14 tests in 1.782s
OK

node --test tests/test_applications_js.cjs
tests 6
pass 6
fail 0
```

Python 使用临时文件 SQLite 数据库与固定 Clock。覆盖提交零预约/零槽、同意图并发重放、完整角色隔离、管理员不能代批、伪造 Actor、20 个独立竞争批准恰好 1 个成功、19 个冲突仍待审、批准两个审计阶段失败全回滚、拒绝/撤回审计失败回滚、过期派生、容量与归属重查、7 天精确边界、停用 30 天不变、真实 schema1 历史升级与合法旧意图重放、schema2 绑定保留、导师/admin 直订、学生直接取消拦截及原取消结果重放。JS 覆盖严格合同、文本安全、身份对应入口、未知审批原操作重试、原因校验、401 清空和过期禁批。

## 真实 HTTP 和浏览器

```text
.venv/bin/python -m scripts.verify_supervised_booking_http
result: PASS; clock: production SystemClock; schema_version: 3; steps: 12
before_approval: applications=1, reservations=0, occupancy_slots=0
after_approval: applications=1, reservations=1, occupancy_slots=2
restart_replay_preserved: true

.venv/bin/python -m scripts.verify_supervised_booking_browser --browser-executable '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
result: PASS
viewports: 1280x900, 390x844
unknown_retry_preserved_intent: true (both)
cross_teacher_status: 404 (both)
keyboard_approval: true (both)
clock: production SystemClock; schema_version: 3
```

真实 Waitress 仅绑定随机 `127.0.0.1` 端口。账号、密码、数据库和浏览器资料均在临时目录，结束后清理；输出不含密码、cookie 或 CSRF。HTTP 使用生产 Clock，检查学生申请→本人导师批准→共享日程→越权拒绝，以及服务重启后同一申请和审批重放。浏览器使用真实 Chrome、生产 Clock，桌面/窄屏通过页面提交并模拟服务端已提交但响应丢失，核对同一个 intent 重试；导师用键盘批准，其他导师只能看到共享白名单文本，学生的已批准预约无直接取消入口。窄屏截图已实际查看，页面无横向溢出。

- `../story-4.2/http/result.json`：HTTP 结果与运行前后源码 SHA-256；`operations.json`：12 次操作的合成业务响应。
- `../story-4.2/browser/result.json`：浏览器断言、视口与源码 SHA-256。
- `../story-4.2/browser/student-awaiting-390.png`、`teacher-approved-390.png`、`shared-schedule-390.png`、`student-approved-detail-390.png`，及对应 1280px 截图：测试证据。
- `../story-4.2/browser/process-cleanup.json`：Waitress 与浏览器进程清理记录。
- `../story-4.2/browser/initial-missing-playwright-browser.json`：首次默认 Playwright Chromium 未安装的启动失败；后续指定已安装 Chrome 真实完成验证。

主流程完成旧夹具适配和独立复核修补后，完整回归：`.venv/bin/python -m unittest discover -s tests -p 'test_*.py'` 为 **243 项通过**；`node --test tests/test_*js.cjs` 为 **414 项通过**。新增 HTTP/浏览器、旧直订并发 HTTP 均在源码稳定后重新运行；原有直订浏览器 runner 的共享字段、完整预约字段和键盘导航断言也已更新，`--booking` 模式在 `story-4.2/legacy-browser-final-3` 实际通过。旧直订测试使用独立的合成导师夹具；旧真实学生和历史仍按 schema 1 迁移测试，未补造历史导师归属。复核意见及逐条裁定记录在 4.2 故事文件；初次旧浏览器失败证据保存在本机忽略目录 `work/approval-archived-runs/`，不冒充通过结果。
