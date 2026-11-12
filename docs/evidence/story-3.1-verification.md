# Story 3.1 验证记录

执行日期：2026-11-12。覆盖 FR-16/17/21/22、NFR-01/02/04、ADR-03/06/07、UX-DR7/9/10。数据、账号和密码均为隔离临时环境的合成测试数据。本记录是实际 AI 实施与自动化验收证据，不代表课题组试用、教师评审或实验 A 结果。

## 执行结果

- Python 全量 **133 项通过，无 skip**：[原始输出](story-3.1-python-tests.txt)。新增 `RoomManagementTests` 的 12 个独立测试直接继承 `unittest.TestCase`，未重复继承既有测试方法。
- JavaScript 全量 **103 项通过，无 skip**：[原始输出](story-3.1-javascript-tests.txt)。新增 17 项执行真实 `rooms.js` 处理器，覆盖头/正文超时、未知响应、非法 DTO、字段/重复/容量冲突、401/403/404/500、保存后目录刷新失败、纯文本、手动刷新、取消编辑和跨表单焦点。
- 真实 HTTP **20 轮×2 并发请求**，屏障同时释放两个独立认证会话，经单进程 8 线程 Waitress：**12 轮预约先成功、降容 409；8 轮降容先成功、预约 409**。全部最终存储无未结束超员；审计与实际成功逐项对应。[结果](story-3.1-http/http-result.json)、[原始输出](story-3.1-http-run.txt)。
- 真实浏览器 **1280×800、390×844**：新增/同值/修改、输入确认、容量/组合/字段/CSRF 拒绝、提交等待、服务器已提交但响应丢失、手动刷新核对、会话失效保留输入、成员越权、精确 DTO、纯文本、无横向溢出、跨表单焦点均通过。[结果](story-3.1-browser/browser-results.json)、[原始输出](story-3.1-browser-run.txt)。已实际查看桌面初始页和手机成功/容量冲突截图。
- 既有登录退出、日程、可用性、创建预约、响应丢失后原意图确认与新意图流程：[预约回归 PASS](story-3.1-booking-regression/browser-results.json)。既有本人取消、拒绝/失效、释放时段和重复确认：[取消回归 PASS](story-3.1-cancel-regression/browser-results.json)。两组均覆盖桌面与手机。

## 末次测试夹具修正

在初次全量 133 项通过后，增加“writer 收到的连接与事务连接为同一对象”断言。首次复跑中测试内 `original` 变量又被复用于 Room DTO，导致第二次调用测试事务包装器报 TypeError；此为测试夹具变量遮蔽，应用事务代码未修改。[当次 133 项中 1 项失败原始输出](story-3.1-python-connection-probe-failure.txt)保留。改为独立 `real_transaction` 名称后，[12 项定向测试](story-3.1-targeted-tests.txt)与最终全量测试均复跑通过。新增未来停用夹具亦证明其不按预约人数阻止降容。

## 验收映射

| 验收项 | 实际断言 |
| --- | --- |
| AC-3.1-1 | 创建 201、完整修改 200、稳定 ID、Room 精确四键；strip、80/120 Unicode 码点及容量 1/1000 边界成功。组合唯一，名称相同不同地点可用，大小写/Unicode 不合并。writer 与业务连接对象身份相同，真实创建/修改各一次，创建 before=null，修改 before/after 四键快照，reason=null。相同规范化资料零 writer/零 timestamp 变更。 |
| AC-3.1-2 | 空值、缺字段、非法 UTF-8/NUL、超长、bool/float/数字字符串/越界容量 400；重复 409 ROOM_DUPLICATE，全部表不变。匿名/退出/精确过期 401，成员 HTML/API 403，授权先于坏参数。超大/超长/非规范路径 ID 400，最大合法不存在 ID 404。Origin/CSRF、内容类型与对象形状直接请求拒绝。无 DELETE 路由。 |
| AC-3.1-3 | 未结束 pending/in_progress 预约均保护；降至 4 时针对人数 5 返回精确管理员 conflict 十键，包含编号/北京时间/人数/reason=null，名称地点全不保存。降至 5 成功。结束等号、已取消和未来停用不阻止降低；预约历史与全部槽原样保留。非管理员先 403，不能取得冲突详情。 |
| AC-3.1-4 | 20 轮真实竞争只出现 [201,409] 或 [409,200]，逐轮保存全部响应及 rooms/reservations/slots/audit 快照，校验无未结束超员、每次业务成功对应唯一审计、完整槽。浏览器失败保留全字段，未知结果不自动重发，刷新目录后可确认已提交的创建。 |
| 原子性、重启与旧意图 | 单元测试注入 writer INSERT 前/后故障及 COMMIT 故障，rooms/预约/槽/审计完全回滚。真实进程停止后重启至失败 writer，新增与修改 500、存储逐字段不变；同值更新 200 不调用 writer。已取消成功预约降容至 1 后，重启仍以原 key 返回原 ID 当前 cancelled 状态/当前容量且零新增审计。 |
| 页面、权限与恢复 | 页面首次有新增/编辑入口，字段 label、核对确认、取消编辑、状态反馈齐全。未确认零 POST，提交中禁用相关控件，20 秒头/正文超时恢复，无自动重提；字段错误聚焦恢复后的字段，完成不抢已移动到退出表单的焦点。失效保留输入、清目录并要求重新登录；模板转义和 textContent 验证 HTML 文本不执行。 |

## 原始文件与运行环境

- 管理浏览器运行 `54e2f87c41c1a5e383cb6f283e248dac`：[桌面网络](story-3.1-browser/runs/54e2f87c41c1a5e383cb6f283e248dac/network-1280.json)、[手机网络](story-3.1-browser/runs/54e2f87c41c1a5e383cb6f283e248dac/network-390.json)、[存储快照](story-3.1-browser/runs/54e2f87c41c1a5e383cb6f283e248dac/storage.json)。最终 7 房间、6 条 room 审计（4 新增、2 修改）；原 9 条预约/停用及槽逐字段保持。
- [桌面初始页面](story-3.1-browser/runs/54e2f87c41c1a5e383cb6f283e248dac/admin-initial-1280.png)、[手机容量拒绝](story-3.1-browser/runs/54e2f87c41c1a5e383cb6f283e248dac/capacity-conflict-390.png)、[手机纯文本成功](story-3.1-browser/runs/54e2f87c41c1a5e383cb6f283e248dac/created-plain-text-390.png)。每个视口另存确认成功、等待、字段/CSRF/重复拒绝、响应未知与失效截图。
- HTTP 运行 `baddceb00604a6836025fc322e7ea4d5`：[40 条原始并发响应](story-3.1-http/runs/baddceb00604a6836025fc322e7ea4d5/concurrent-responses.jsonl)、[步骤响应](story-3.1-http/runs/baddceb00604a6836025fc322e7ea4d5/http-steps.json)、[故障前](story-3.1-http/runs/baddceb00604a6836025fc322e7ea4d5/before-restart-fault.json)、[故障/重启后](story-3.1-http/runs/baddceb00604a6836025fc322e7ea4d5/after-restart-fault.json)、[真实环境](story-3.1-http/runs/baddceb00604a6836025fc322e7ea4d5/environment.json)。目录另有逐轮 `round-00` 至 `round-19` 全表快照。
- macOS 26.6 arm64；Python 3.12.14、SQLite 3.53.1、Flask 3.1.3、Jinja2 3.1.6、Werkzeug 3.1.9、Waitress 3.0.2、Playwright 1.58.2、Google Chrome 157.0.8103.51。版本取自实际环境输出；不宣称全部组件最新。
- 新 runner 每次先置 `INCOMPLETE`，独立 `runs/<run_id>` 保留原始数据。应用/runner/helper SHA-256 在运行前后比对；只有实际断言、停服与临时文件清理完成才发布 PASS。浏览器复用已验证的 POSIX 进程组与 Chromium 注册清理，HTTP 复用已验证的独立 Waitress 进程生命周期。临时库与私有随机凭证自动删除，不写默认演示库。

## 复跑

```bash
.venv/bin/python -m unittest discover -s tests -v
node --test tests/test_*js.cjs
.venv/bin/python -m scripts.verify_room_management_http --output-dir work/room-management-http
.venv/bin/python -m scripts.verify_room_management_browser --output-dir work/room-management-browser
.venv/bin/python -m scripts.verify_auth_browser --replay --port 8005 --output-dir work/room-booking-regression
.venv/bin/python -m scripts.verify_member_cancel_browser --output-dir work/room-cancel-regression
```

浏览器工具安装和已有 Chrome 的 `--browser-executable /absolute/path/to/chrome` 参数见 README。本次实际浏览器命令使用 `/Applications/Google Chrome.app/Contents/MacOS/Google Chrome`。HTTP 随机空闲端口；管理浏览器默认 8007，回归分别 8005/8006。禁止把测试固定 Clock 或失败 writer 当作线上 HTTP 后门。

房间管理范围全部完成；没有提前实现 `admin_cancel_booking` 或 `revoke_block`，没有操作 Git 或远端。并发结果只代表本次规定负载；未声称真实用户试用或生产 SLA。

## 独立评审后最终核验

三层评审15条逐条分类，11条归并为8项直接修补，4条低影响且增加复杂度的边界不修，0defer。所有修补及定向证据见[修补记录](story-3.1-review-fixes/verification.md)。跨登录导航不恢复草稿、极大ID的浏览器精度、多人完整资料编辑最后提交覆盖属于已披露边界，不宣称具备相关保护。

主流程实际重跑全量 **139个唯一Python测试、141项JS**，无skip。20轮真实HTTP预约/降容竞争，预约胜10轮、降容胜10轮；全部最终状态、审计、故障回滚和真实重启通过。新管理浏览器已验证1280/390，主流程另跑既有创建重放和本人取消两套浏览器回归，均通过。四份报告的应用及验证源码SHA-256重新计算全部匹配，详见[父流程最终核验](story-3.1-review-fixes/parent-final-qa.json)。初版及失败证据均保留。

实现调用共2次：初始实现1次，评审修补1次，无传输失败。技术接受来自AI流程，不代表人类/教师验收。
