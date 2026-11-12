# Story 1.2 会议室与共享日程：实施验证

验证日期：2026-11-12。执行者：Codex AI。所有账号、房间、预约和停用均为明确的合成夹具；测试文件库、浏览器临时库与默认演示库隔离。以下是技术验证，不代表实际课题组试用、教师 M1/M2 或完整系统 NFR 验收。

追踪：FR-05、FR-07、FR-22；NFR-02；ADR-02/03/06；UX-DR3/4/9/10；AC-1.2-1—4。

## 交付

- 非破坏性补齐 `rooms`、`reservations`、`occupancy_slots`，保留 `user_version=1`。落实 kind/空值/取消字段、外键、唯一占用槽和索引约束，启动检查全部查询实体列；没有引入业务审计或写接口。
- 页面与 `/api/rooms` 共用目录服务；页面通过 `/api/schedule` 调用同一个日程服务。服务在短只读事务内捕获一个 Clock 时刻，重新检查 actor 会话，再验证参数并读取一致快照。
- 目录按 name/location/id 排序；日程按半开区间与北京日期相交，按 start_at/id 排序，排除取消预约和撤销停用，保留已结束及跨日历史。DTO 显式列出合同字段，不序列化完整数据库行。
- 首页有中文目录、会议室和日期 label、条件保留、等待/成功/空/错误反馈、失效重新登录提示；保留顶栏身份与正常退出。Jinja 自动转义；日程脚本使用独立作用域及 `textContent`。
- `scripts.seed_demo_rooms` 幂等补充三间合成房间，不覆盖已有容量、账号或业务。README 给出新库及旧 Story 1.1 库的初始化/启动路径；默认演示库为空日程，有日程由独立测试夹具验证。

## 可复跑命令与结果

```bash
.venv/bin/python -m unittest discover -s tests -v
node --test tests/test_auth_js.cjs
.venv/bin/python -m scripts.verify_auth_browser --schedule --output-dir work/schedule-verification
```

浏览器依赖安装及 `--browser-executable` 选项见 README。本机真实执行的浏览器命令为：

```bash
.venv/bin/python -m scripts.verify_auth_browser --schedule --browser-executable '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome' --output-dir docs/evidence/story-1.2-browser
```

初版全量 **49 项 Python 测试通过，0 skip**，其中原认证 33 项、新日程 16 项；新测试类不继承认证测试。原始结果见 [Python 输出](story-1.2-tests.txt)。[认证 JavaScript 超时回归](story-1.2-js-tests.txt) 2 项通过，覆盖响应头及正文读取停滞。夹具规范化 payload 修订时的定向结果也保留在 [夹具复查](story-1.2-fixture-recheck.txt)，初版全量记录包含新增的旧 schema 升级用例。评审修订的定向结果另见本文末尾；此处不代表修订后重跑了全量。

实际连续执行两次房间初始化 CLI，新增数为 3、0，最终房间数 3；临时库清理，见 [CLI 结果](story-1.2-seed-cli.json)。单元测试另验证原房间容量、预约和槽不被复跑覆盖，并从仅有 users/sessions 的版本 1 数据库补齐新表后保留原身份及会话。

环境为 macOS 26.6 arm64，Python 3.12.14、SQLite 3.53.1、Flask 3.1.3、Jinja2 3.1.6、Werkzeug 3.1.9、Waitress 3.0.2，见 [实际版本](story-1.2-environment.json)。浏览器为 Chrome 157.0.8103.51、外部 Playwright 1.58.2。启动器使用 `python -m waitress --listen=127.0.0.1:8002 --threads=8 --call booking_app:create_app`，单进程 8 线程，结束后停止服务并删除临时账号和数据。

## 矩阵证据

| 范围 | 实际断言 |
| --- | --- |
| 目录/空状态 | 不同名称、同名不同地点按名称/地点/id 排序；精确 Room 键；空目录及空日程 200；HTML 与 API 共用服务。 |
| 半开日期/历史 | 跨日前后各日覆盖；23:00—次日00:00 不进入下一日；下一日00:00记录只进入下一日；历史未撤销停用保留；已取消预约/撤销停用不返回。 |
| 统一状态/排序 | 固定 t 下 pending/in_progress/ended；start=t 与 end=t 等号；服务仅调用 Clock 一次。相同起点的取消记录与其他房间记录不混入目标日程；SQL 明确包含 `ORDER BY r.start_at,r.id`。同室两个有效记录若同起点将违反唯一槽，未制造违反槽完整性的夹具冒充排序证据。 |
| 隐私/XSS | 成员甲查看乙、乙本人、管理员均得到相同共享白名单；预约不含 id/user_id/owner_id/purpose/attendees/username/cancel_reason/意图载荷；私密哨兵值不在 JSON/DOM 中。HTML 字符活动名/显示名原样显示为文本，没有新增 img/script 节点或执行事件。 |
| 输入/身份 | 日期严格固定宽度、无效闰日/溢出拒绝；ID 拒绝 bool/float/Unicode 数字/前导零/超范围/超长数字。`2**63-1` 不存在为404，`2**63` 和一万位数字400，无500。匿名、临时、到期及退出凭证先401；服务拒绝伪造/陈旧 actor。 |
| 存储 | 分支/取消/外键/槽唯一约束拒绝非法写；所有测试结束检查每条有效记录槽连续完整、取消记录零槽；只读事务禁止写入，独立 writer 提交后读事务仍保持原快照。 |

## 浏览器与视觉检查

[浏览器原始结果](story-1.2-browser/browser-results.json) 为 PASS；1280×800、390×844 均保留键盘登录/退出、身份 API、退出旧 cookie 拒绝和认证字段错误检查，并增加日程查询的等待状态、字段聚焦、成功、空结果、404 条件保留、共享 JSON/DOM 隐私、半开午夜和另一标签页退出后的重新登录提示。两种尺寸均无页面 JavaScript 异常，页面 scrollWidth 分别为 1280 与 390，无横向溢出。

- [桌面有日程](story-1.2-browser/schedule-1280.png)、[手机有日程](story-1.2-browser/schedule-390.png)
- [桌面空日程](story-1.2-browser/empty-1280.png)、[手机空日程](story-1.2-browser/empty-390.png)
- 同目录保留登录和查询前首页截图。

桌面/手机有日程截图已实际打开检查；手机内容正常纵向滚动，长 HTML 文本换行而不执行。截图前回到页面顶端，避免离屏固定跳转链接在全页截图中产生位置伪影。

验证启动器快速复跑时曾因端口处于 TIME_WAIT 报 Address already in use；在端口可用性探测设置 SO_REUSEADDR 后，最终浏览器验证通过。没有为此放松应用认证、端口绑定或业务规则。

## 范围边界

本故事执行项完成，无已知未通过的本故事验收项。未实现可用性、创建预约、管理写入或实验 A 目标；没有操作 Git 或远端。默认库不提供公开固定密码，也不注入测试预约。完整系统的性能、业务写并发、审计及真实使用适用性仍由后续故事和验收负责。

## 评审修订：定向验证

2026-11-12，根据评审修复查询期间仍可编辑条件的问题：请求进行时同时禁用会议室和日期输入，`finally` 恢复按钮、两个输入及 `aria-busy`，随后再聚焦字段错误，确保错误属于原查询条件。首页增加明确的无 JavaScript 提示；查询按钮默认禁用，由脚本在可查询时启用，无脚本下目录保持可读且不会提交到 JSON 页面。

新增 `tests/test_schedule_js.cjs`，执行 `schedule.js` 实际注册的 submit 处理器。可控计时器分别覆盖响应头/正文停滞 20 秒取消，另覆盖网络失败、坏 JSON、等待期间条件不可编辑、字段错误聚焦、条件保留、控件/忙状态恢复及手动再次查询。认证超时测试只覆盖 `auth.js`，不再将其作为日程脚本超时的替代证据。

初版浏览器使用真实时钟，未断言日程三种状态，也未精确断言结束时间；原始文件保持不变。复查使用验证脚本专属工厂 `scripts.verify_auth_browser:create_schedule_verification_app`，以 `TESTING=True` 注入夹具固定 Clock；生产工厂没有新增环境变量开关或 HTTP 测试入口。固定时间是 **1794448800 / 2026-11-12T10:00:00+08:00**，在报告中明确记录。普通预约与跨日停用均精确核对 start/end epoch、本地字符串和完整页面区间；浏览器逐条核对「已结束 / 进行中 / 待开始」文字，并以键盘 Enter 提交日程、分别验证会议室和日期字段错误聚焦。

本次只执行以下涉及修改的定向检查，没有重跑全量测试：

```bash
.venv/bin/python -m unittest tests.test_room_schedule.RoomScheduleTests.test_room_exact_contract_order_and_page_share_service tests.test_room_schedule.RoomScheduleTests.test_schedule_exact_contract_current_status_and_private_fields_absent tests.test_room_schedule.RoomScheduleTests.test_half_open_midnight_cross_day_and_historical_blocks -v
node --test tests/test_schedule_js.cjs
.venv/bin/python -m scripts.verify_auth_browser --schedule --browser-executable '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome' --output-dir docs/evidence/story-1.2-browser-reviewed
```

结果：**3 项 Python、5 项日程 JavaScript 测试通过，0 skip**；浏览器在 **1280×800、390×844** 均 PASS，无 JavaScript 异常和横向溢出。原始记录为 [Python 定向输出](story-1.2-reviewed-tests.txt)、[日程 JS 输出](story-1.2-reviewed-js-tests.txt)、[固定时钟浏览器报告](story-1.2-browser-reviewed/browser-results.json)。该报告保存实际 Waitress 命令、固定时刻以及逐项检查结果；启动单进程 8 线程，临时服务与数据在结束后清理。

[复查桌面截图](story-1.2-browser-reviewed/schedule-1280.png)和[复查手机截图](story-1.2-browser-reviewed/schedule-390.png)已打开检查，三种状态文字与完整起止区间显示正确。`story-1.2-browser/`、初版 Python/认证 JS 原始证据均未覆盖。


主代理最终核对：49项Python、7项JS全量通过（0 skip）；修订后桌面/手机浏览器通过，固定Clock三态、准确区间、无脚本说明与键盘提交均有证据；已查看修订截图。14条发现逐条裁决，所有保留修补项关闭，无high/medium延期。
