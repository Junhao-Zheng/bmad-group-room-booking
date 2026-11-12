# Story 2.1 创建预约验证

2026-11-12，AI 实施与自动化验证记录；不是教师评审或实际成员试用。范围仅新建预约及原子审计，不包括可靠重放、取消或管理员实验目标。

## 实现与验收

- `services.create_booking` 为业务写入口。`BEGIN IMMEDIATE` 后取一次 Clock，重新读取真实会话、角色及显示名，再进行规范化、会议室存在性、时间、容量和占用校验。业务记录、完整连续半小时槽、一条 `booking.created` 事件同事务提交；web 仅包装一层 `ok/data`，提交成功后返回 201。
- `audit_events` 及索引通过幂等初始化补齐，保留旧用户、会话、预约、槽和 `user_version=1`。writer 使用命令同一连接，只执行一次 INSERT；事件保存固定事实白名单、操作者显示名快照、UTC 整数时刻及精确 null。
- JSON ID/人数严格拒绝 bool、float 和数字字符串；ID 在 SQLite 绑定前限正 64 位。人数过大先比较容量，不进行会溢出的 SQLite 绑定或超大整数 JSON 编码。文本 strip 后按 Unicode 码点计数，拒绝 NUL/孤立代理码点，普通 Unicode 与 HTML 字符按纯文本处理。
- 普通成员冲突条目仅含 `type/room_id/start_at/start_local/end_at/end_local/status`；管理员仅额外得到 `id/attendees/reason`。没有共享预约 ID、用途、人数或账号泄漏。
- 首页从可用结果选房，沿用当次查询时段/人数，随机生成 32 字节意图 key。提交中禁用创建与查询选择控件；成功显示编号/时间；冲突保留输入；网络未知结果保留输入且停止本页重提，不声称失败、不自动发新请求。

## 自动化原始证据

| 检查 | 结果 | 原始记录 |
| --- | --- | --- |
| Python 全量功能/安全/事务回归 | 78 通过，0 失败，无 skip | [python-tests.txt](story-2.1/python-tests.txt) |
| JavaScript 认证/日程/可用性/创建状态与超时 | 18 通过，0 失败，无 skip | [javascript-tests.txt](story-2.1/javascript-tests.txt) |
| 20 不同成员、不同 key、独立 HTTP cookie 会话，同室同时段 | 1×201 + 19×409 OCCUPANCY_CONFLICT，无 503 | [完整 20 响应](story-2.1/http/create-http-responses.jsonl)、[结果](story-2.1/http/create-http-result.json) |
| 并发最终 DB | 恰 1 条预约、4 个连续槽、1 条创建审计；payload/快照/外键/完整性匹配 | [竞争后存储](story-2.1/http/create-http-storage.json) |
| 真 HTTP 审计 writer 故障，随后重启 | 500 安全错误，业务/槽/审计完全不变；失败 key 无记录，正常重启同 key 首次创建成功 | [故障及重启响应](story-2.1/http/create-http-fault-responses.json)、[最终存储](story-2.1/http/create-http-final-storage.json) |
| 1280×800 / 390×844 真实 Chrome | 创建、冲突、Unicode/XSS、未知网络结果、全部原查询/登录/退出检查通过；无页面横向溢出、无 pageerror | [浏览器 JSON](story-2.1/browser/browser-results.json)、[运行输出](story-2.1/browser-run.txt) |

定向 Python 测试另实际注入了：writer 在 INSERT 前和后抛错、连接执行 COMMIT 抛错、预约 INSERT 非预期约束错误、写完首槽后制造槽主键冲突。每次均断言业务、槽、审计全部回滚，真实失败后的 key 可重新使用。测试还核对精确 DTO/null、规范化六字段 JSON、同 key 暂时 409、跨用户 key 隔离、同室 booking/block 重叠、相邻/异室成功、30 分钟/4 小时/30 天边界、跨日午夜拒绝、鉴权先于业务字段、CSRF/Origin 和同锁内新鲜身份。

环境和源码 SHA-256 见 [HTTP 环境](story-2.1/http/create-http-environment.json)，包含真实 Python/SQLite/Flask/Waitress 版本、OS/CPU、单进程 8 线程、固定测试时刻及启动调用。数据、账号和浏览器凭证都在隔离临时文件库；正式演示库未改动。测试用 Clock/writer 仅经 TESTING=True 注入，无 HTTP 后门。

截图已检查：

- [手机创建成功](story-2.1/browser/booking-success-390.png)
- [桌面创建成功](story-2.1/browser/booking-success-1280.png)
- [手机冲突保留输入](story-2.1/browser/booking-conflict-390.png)
- [桌面冲突保留输入](story-2.1/browser/booking-conflict-1280.png)
- [手机未知结果](story-2.1/browser/booking-unknown-390.png)

## 复跑与实际修正记录

从项目根运行：

```bash
.venv/bin/python -m unittest discover -s tests -v
node --test tests/test_*js.cjs
.venv/bin/python -m scripts.verify_create_booking_http --output-dir work/create-booking-http
.venv/bin/python -m scripts.verify_auth_browser --booking --output-dir work/create-booking-browser
```

浏览器依赖及安装步骤见 README。本机没有 Playwright 已下载的匹配 Chromium；首次 launch 在启动浏览器时失败，未执行应用断言，安全诊断保留于 [initial-browser-launch-failure.json](story-2.1/browser/initial-browser-launch-failure.json)。实际成功命令使用 `--browser-executable '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'`，报告记录 Chrome 157.0.8103.51 和 Playwright 1.58.2。其他机器应使用自己的安装路径或下载 Playwright Chromium。

实现中修正了测试账号切换时误复用已认证客户端、HTTP 夹具遗漏初始化要求的管理员、旧认证测试未包含新增审计表、JS 超时夹具的微任务启动顺序。这些均为验证夹具修正；最终全量回归通过。浏览器图像使用回到页面顶部后全页截图，避免把视口外固定跳转链接绘入中部。

## 本增量边界

成功意图已持久保存，但相同 key 暂统一返回受控 409，并未交付 Story 2.2 的可靠成功结果重放或意图编辑逻辑。共享日程只能帮助人工核对未知结果，不能替代后续精确意图确认。未创建任何取消、管理员取消、停用创建或撤销命令；实验目标没有提前实现。本故事未操作 Git 或远端。


后续独立评审与修复已完成：全量81项Python、24项JavaScript通过；见[逐条裁决](reviews/story-2.1-review.md)与[新浏览器/测试原始证据](story-2.1-reviewed/)。以上初版记录保留其发生时的事实。
