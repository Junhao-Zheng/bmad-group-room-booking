# Story 2.3 验证记录

执行日期：2026-11-12。覆盖 FR-13/04/22、NFR-02、ADR-02/06、UX-DR3/6/9。所有账号、用途、取消事实均为合成测试夹具；本记录是 AI 实施与自动化验证证据，不是课题组试用、教师评审或实验 A 结果。未实现后续取消或管理员干预命令。

## 结果

- Python 全量 **100 项、100 个唯一测试标识，通过，无 skip**：[原始输出](story-2.3-python-tests.txt)。新增 `PersonalHistoryTests` 的 9 项测试直接继承 `unittest.TestCase`，独立建立历史夹具，没有继承其他测试类重复计数。
- JavaScript 全量 **44 项，通过，无 skip**：[原始输出](story-2.3-javascript-tests.txt)。新增 12 项执行真实 `history.js` 注册处理器，覆盖列表/详情超时、网络及 JSON 错误、字段错误恢复、显式重试、焦点、纯文本和会话失效。
- Chrome **157.0.8103.51** / Playwright **1.58.2**，**1280×800、390×844**：[个人历史结果](story-2.3-browser/browser-results.json)、[运行输出](story-2.3-browser-run.txt)。四态、完整详情、空记录/空筛选、长文本、成员隐私、管理员详情、加载/错误/失效及键盘导航退出均通过。页面宽度分别为 1280/390，均未横向溢出，页面异常数组为空。
- 查询前后完整业务存储一致：**9 条历史记录（8 预约、1 停用）、13 个槽、0 审计**。记录来自明确历史夹具，0 审计不是一次实际取消命令的结果。[读取前后原始存储快照](story-2.3-browser/runs/5113522db86f6440270b590115bfbe1b/storage.json)。
- 既有登录退出、共享日程、可用性、创建冲突、响应丢失重试、新意图与最终存储回归通过：[浏览器结果](story-2.3-regression-browser/browser-results.json)、[原始输出](story-2.3-regression-browser-run.txt)。
- 原创建 20 个独立成员争用同槽：**1×201 + 19×409**；同成员同意图 20 个独立 CookieJar：**1×201 + 19×200**。两组最终均为 1 预约、4 槽、1 创建审计；实际进程重启、审计故障完整回滚和失败 key 重用通过：[创建结果](story-2.3-create-regression/create-http-result.json)、[重放结果](story-2.3-replay-regression/replay-http-result.json)。没有用锁超时替代冲突。

## 验收矩阵

| 验收 | 实际执行断言 |
| --- | --- |
| AC-2.3-1 | 独立夹具本人四态，全列表 `[106,105,104,103,102,101]`；103/104 同起点按 ID 倒序。各过滤返回正确集合；精确开始前一秒、开始等号、结束前一秒、结束等号的列表与详情状态一致，取消优先。每条列表与详情精确相等，核对全部 BookingFull/Room 键、未取消 null、本人取消 null 原因、管理员取消操作者/原因和本地秒级时间。 |
| AC-2.3-2 | 两成员/管理员个人列表始终只本人；替换 user_id/owner_id/actor 不改变主体。成员他人记录、合法不存在和停用 ID 同 404 正文；管理员可读成员完整取消详情。服务重新核验会话，伪造 id/hash、已退出和精确到期拒绝；旧 Actor.role 不可越权，数据库角色提升/撤销即时生效。匿名先 401，HTML 跳登录；最大合法 ID 404、超界/5000 位数字/前导零/错误类型 400。 |
| AC-2.3-3 | 真实浏览器用四个独立账号验证全部空记录与筛选空记录；80 字符标题、500 字符用途、长位置与 HTML 字面文本安全展示，未生成 img/script/svg 或执行 historyXss；各业务/取消空字段明确显示。键盘访问导航、过滤、详情和退出；详情焦点落在标题。桌面/手机截图和 scrollWidth 断言通过。 |
| Code Map 读事务 | 每次服务捕获一次 Clock，并在只读事务内复核会话。列表转换期间另一连接提交房间/显示名修改并推进时钟，本次结果仍使用同一快照与 t。业务/槽/审计无修改，故障 writer 不会被读服务调用；应用重建后历史仍一致。 |
| 错误恢复及既有流程 | 真实 JS 处理器分别验证响应头/正文 20 秒超时、网络、JSON、字段及详情 404 错误，控件恢复、条件保留、无自动重试；真实浏览器断网后主动重试、退出后的旧页面查询 401，原创建/重放及键盘退出回归通过。 |

## 原始证据入口

个人历史最终运行 ID：`5113522db86f6440270b590115bfbe1b`；每次浏览器运行保存在独立目录，总结果指向该轮目录。第一次已通过的布局取证也保留在原 run 目录；最终轮补充全空账号和截图定位，旧轮不会覆盖最终证据。

- [桌面实际 API 响应](story-2.3-browser/runs/5113522db86f6440270b590115bfbe1b/history-network-1280.jsonl)、[手机实际 API 响应](story-2.3-browser/runs/5113522db86f6440270b590115bfbe1b/history-network-390.jsonl)：保留精确个人/管理员详情及 400/401/404 响应，不含登录凭证、CSRF、cookie 或会话摘要。
- [桌面长文本详情](story-2.3-browser/runs/5113522db86f6440270b590115bfbe1b/long-text-detail-1280.png)、[手机长文本详情](story-2.3-browser/runs/5113522db86f6440270b590115bfbe1b/long-text-detail-390.png)、[手机取消详情](story-2.3-browser/runs/5113522db86f6440270b590115bfbe1b/cancelled-detail-390.png)、[全空记录](story-2.3-browser/runs/5113522db86f6440270b590115bfbe1b/empty-all-390.png)、[失效](story-2.3-browser/runs/5113522db86f6440270b590115bfbe1b/session-expired-390.png)。桌面与手机长文本截图已经 AI 视觉检查，字段清晰、换行正常。
- [原浏览器回归各轮产物](story-2.3-regression-browser/browser-results.json) 的 `artifact_directory` 包含截图与原提交意图网络日志。
- [创建全部响应](story-2.3-create-regression/create-http-responses.jsonl)、[创建原始输出](story-2.3-create-regression-run.txt)、[重放全部响应](story-2.3-replay-regression/replay-http-responses.jsonl)、[重放原始输出](story-2.3-replay-regression-run.txt)。两个 HTTP 目录包含最终数据库、故障/重启响应、实际环境及源码 SHA-256。

## 复跑与边界

在项目目录运行：

```bash
.venv/bin/python -m unittest discover -s tests -v
node --test tests/test_*js.cjs
.venv/bin/python -m scripts.verify_history_browser --output-dir work/history-browser
.venv/bin/python -m scripts.verify_auth_browser --replay --port 8005 --output-dir work/history-regression-browser
.venv/bin/python -m scripts.verify_create_booking_http --output-dir work/history-create-regression
.venv/bin/python -m scripts.verify_replay_intent_http --output-dir work/history-replay-regression
```

本机两条浏览器命令实际加 `--browser-executable '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'`。Python 3.12.14、SQLite 3.53.1、Flask 3.1.3、Jinja2 3.1.6、Werkzeug 3.1.9、Waitress 3.0.2；启动参数为单进程、8 线程、loopback，调试关闭。历史浏览器端口默认 8004，旧流程回归本次 8005；HTTP 回归随机空闲端口。所有脚本使用独立临时库与随机凭证，结束停止进程并清理，不修改演示库。

规定验收均完成。当前列表依架构不分页，未增加 1000 条上限；未交付未来故事的取消按钮、管理写入口或实验 A 目标。自动化测试和 AI 截图检查不能替代真实人类试用。
