# Story 2.2 评审修复定向验证

2026-11-12。仅验证本轮修改覆盖的文件；没有运行全量测试，也没有操作 Git/远端。初版 `story-2.2-*` 原始证据保持不变。

## 修复

- `booking.js` 保留当前意图未知状态，后续认证/CSRF/存储错误不会清除原提交的不确定性；相同 key 确认成功后才清除。被实质编辑替换的未知意图保留页面内持续提醒，后续输入、选房和新意图成功都不会覆盖该提醒。
- 当前意图保留最后已确认编号；再次确认遭遇网络错误时显示“原预约 #编号 已确认，本次当前状态未刷新”，不把已确认的存在性重新说成“可能成功”。成功 Full DTO 刷新确认区当前房间名称、地点及时间，不修改业务字段或提交键。
- 六个实质字段分别从独立基线修改，断言只有该字段改变且 key 变化；四态分别断言待开始/进行中/已结束/已取消文字。
- 浏览器新增首 POST 在发送到服务端前中止的场景；同一 key 主动重试返回 201。保留已经提交后丢失响应、重试 200 的场景。真实文件库分别核对一条预约、连续完整槽、一次创建审计。
- 浏览器 runner 开始即用新 `run_id` 和真实 UTC 时刻写 INCOMPLETE；每次网络/截图存入独立 `runs/<run_id>`。服务停止、临时文件清理及存储断言完成后才写 PASS；失败只保存安全错误类型和运行元数据。
- HTTP 元数据新增实际直接依赖的 SHA-256：`verify_create_booking_http.py`（server/clock/fault/storage）、`verify_availability_performance.py`（client/environment）、`init_demo.py` 与 `tests/schedule_fixtures.py`。取消夹具的固定 Clock 已推进到取消时刻再创建替代预约。

## 实际结果

- [18 项实际预约 JS 处理器回归通过](booking-javascript-tests.txt)，无 skip。
- [10 项定向 Python 测试通过](targeted-python-tests.txt)：9 项重放验收和 1 项真实启动失败回归，无 skip。
- [真实 HTTP 结果](http/replay-http-result.json)：20 同 key 请求为 1×201、19×200，同一个预约 ID；一次创建审计、4 个完整半小时槽。重启/故障验证通过。最终应用及辅助源码哈希与磁盘内容一致。
- [真实浏览器结果](browser/browser-results.json)：1280×800 和 390×844 均通过。`artifact_directory` 指向本轮截图和原始网络目录；两种视口均保留 `replay-network-*.jsonl`（201→200→新意图201）及 `not-delivered-network-*.jsonl`（未发送→原 key 201）。存储 oracle 确认首次未送达重试最终只有一条预约、两个槽、一次审计。
- [已有 PASS 目录实际失败验证](browser-prior-pass-failure-check.json)：复制本轮实际成功目录作为已有 PASS 输入，使用真实被占用端口运行，退出码 1，最新结果变为 [INCOMPLETE](browser-prior-pass-failure/browser-results.json)，新 run_id 与旧值不同，仅报告 OSError；旧网络文件 SHA-256 不变，新目录无旧文件混入。运行标准错误为空，未输出凭证。

```bash
node --test tests/test_booking_js.cjs
.venv/bin/python -m unittest tests.test_replay_intent tests.test_browser_verification -v
.venv/bin/python -m scripts.verify_replay_intent_http --output-dir docs/evidence/story-2.2-reviewed/http
.venv/bin/python -m scripts.verify_auth_browser --replay --browser-executable '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome' --output-dir docs/evidence/story-2.2-reviewed/browser
```

这些均为 AI 执行的合成数据自动化验证，不是人类验收或教师评审。没有新增跨刷新草稿、取消/管理接口或其他故事能力。本轮列出的修复项均已完成；全量复验由主代理继续执行。


主代理最终验收：91项Python、32项JavaScript全量通过，无skip；两视口真实浏览器覆盖提交后丢响应→200重放与未送达→201创建，两者最终均恰一次业务/审计。20同意图并发1×201+19×200，重启/回滚通过；应用及验证辅助源码hash已独立比对一致。全部11条保留发现关闭，无high/medium延期。修补期间发生1次传输中断，原代理恢复同一修补任务；逻辑修补1轮、实际实现/修补调用3次（含恢复调用），不把连接错误当产品缺陷。
