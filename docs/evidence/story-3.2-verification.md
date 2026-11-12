# Story 3.2 验证记录

执行日期：2026-11-12。追踪 FR-18/20/21/22、NFR-01/02/04、ADR-02/03/06/07、UX-DR8/9/10。数据、账号、密码与历史终态均来自隔离测试夹具或真实测试接口操作。本记录是 AI 实施与自动化验证证据，不代表真实成员试用、教师评审或实验 A 结果。

## 最终执行结果

- Python 全量 **153 项通过，无 skip**：[原始输出](story-3.2/python-tests.txt)。新增 14 个独立 `MaintenanceBlockTests`，直接继承 `unittest.TestCase`；全部 153 个测试 ID 唯一，无继承重复计数。
- JavaScript 全量 **176 项通过，无 skip**：[原始输出](story-3.2/javascript-tests.txt)。新增 35 项执行真实 `blocks.js` 处理器，覆盖创建/查询头与正文超时、未知响应、精确 DTO、冲突细节、字段错误、权限、服务失败、确认失效、跨表单焦点，以及创建成功后列表失效仍保留成功事实。
- 真实 HTTP **20 轮×2 个并发请求**，两个独立会话经过单进程 8 线程 Waitress：每轮恰有 **1×201 + 1×409**，最终 **13 轮预约先成功、7 轮停用先成功**。逐轮存储断言保证共同槽互斥、连续完整及一条对应创建审计。[报告](story-3.2/http/http-result.json)、[原始输出](story-3.2/http-run.txt)。
- 新停用/管理查询浏览器 **1280×800、390×844** 全通过：真实登录、四态查询、完整 DTO、未查询/加载/空状态、创建确认/等待、跨表单焦点、CSRF/字段/两类冲突拒绝、服务端已提交但响应丢失、手动核对、失效保留输入、成员直接拒绝、共享日程、退出。[报告](story-3.2/browser/browser-results.json)、[原始输出](story-3.2/browser-run.txt)。已实际查看桌面和手机初始页面截图，截图及宽度断言均无横向页面溢出。
- 既有流程实际浏览器回归： [房间管理](story-3.2/room-regression/browser-results.json)、[登录退出/查询/预约创建/原意图重放](story-3.2/booking-regression/browser-results.json)、[本人取消/槽释放/重复确认](story-3.2/cancel-regression/browser-results.json)。各套均覆盖桌面与手机。
- [最终交叉核验](story-3.2/final-report-check.json)：五份 HTTP/浏览器报告全部 PASS，应用及验证脚本 SHA-256 与当前文件一致；记录测试源码 SHA-256、唯一 Python 测试计数，并确认 8005/8006/8007/8008 验证端口已关闭。

## 验收映射

| 验收项 | 已实际执行的断言 |
| --- | --- |
| AC-3.2-1 | `create_block` 独立命令；room_id 严格 JSON 正整数，不接受 bool/float/数字字符串/越界；时间复用纯解析，只接受固定宽度半小时北京时间。拒绝 start=t、过去、end<=start、超 30 天及不规范时间，允许半小时、精确 end=t+30 天、跨日 30 小时。原因 strip、Unicode 500 码点成功；空白/501/NUL/孤立代理字符失败。201 返回精确 BlockFull，五个撤销字段为 null，不含 cancelled 外部键。存储 user_id 为管理员，booking 分支五字段 NULL；60 个连续槽，与业务同连接一次 block.created、完整纯事实快照、before=null、reason=创建原因。 |
| AC-3.2-2 | 新停用与已有预约/停用分别返回 409 OCCUPANCY_CONFLICT，原全部业务/槽/审计逐字段不变。管理员冲突精确十键，成员预约冲突仅共享七键。相邻成功、跨日长停用成功、预约也不能覆盖停用。20 轮屏障双请求真实 HTTP 每轮一成功一409，逐轮写出原始两条响应及最终存储；无503冒充冲突。 |
| AC-3.2-3 | 管理预约/停用列表精确 Full DTO，仅一层 ok/data、items/total；所有记录 start_at/id 升序，稳定处理同开始时刻。房间/日期/状态组合筛选，空结果200。日期半开相交覆盖跨午夜历史、午夜边界和新建长停用；pending/in_progress/ended/cancelled 或 revoked 四态不重不漏、终态优先、时间等号正确。非法/空 status、坏日期、非法/超长 ID 400；最大合法不存在 room_id 404。查询前后四表无变化。 |
| AC-3.2-4 | 匿名、已退出、精确过期 API 401；成员直接管理写和读403，坏字段不绕过授权优先。服务重新查会话和角色，伪造/陈旧 Actor 无效；写锁后过期拒绝，服务仅取一次 Clock。Origin/CSRF/内容类型直接拒绝。writer 插入前/后故障及 COMMIT 故障全部回滚；真实独立写锁超时503且释放后可主动重试。浏览器冲突展示类型、编号、房间、完整起止、人数/原因，保留输入，纯文本不执行脚本。 |
| 持久化与故障 | 真实停止 Waitress，再用同一文件库重启至失败 writer，全部业务/槽/审计逐字段一致。失败停用500后存储不变；旧预约意图仍200、原ID、replayed=true且无新审计。再次停止重启至正常 writer，原失败停用成功，最终完整槽和一次审计。 |
| 页面与恢复 | 管理列表只有查看；页面与服务均无管理员取消/撤销命令。每个字段有 label，创建前显示时段与原因预览；任意字段 input/change 清确认，未确认不 POST。20秒期限包含正文，重复点击不新增请求；错误保留字段、恢复控件、正确聚焦字段。其他表单获得焦点后完成不抢焦点；成功与列表刷新失败分别反馈；权限失效清完整列表并禁止旧页继续提交。未知结果仅提示主动查询核对，无自动重发。 |

## 原始证据入口

HTTP 最终运行 `2e032fd0031dbddbecb2a4770848aca8`：

- [40 条原始竞争响应](story-3.2/http/runs/2e032fd0031dbddbecb2a4770848aca8/concurrent-responses.jsonl)、[顺序请求与结果](story-3.2/http/runs/2e032fd0031dbddbecb2a4770848aca8/http-steps.json)。同目录 `round-00-storage.json` 至 `round-19-storage.json` 保存每轮最终四表。
- [重启/故障前](story-3.2/http/runs/2e032fd0031dbddbecb2a4770848aca8/before-restart-fault.json)、[重启/故障后](story-3.2/http/runs/2e032fd0031dbddbecb2a4770848aca8/after-restart-fault.json)、[正常重启重试最终存储](story-3.2/http/runs/2e032fd0031dbddbecb2a4770848aca8/final-storage.json)、[真实环境](story-3.2/http/runs/2e032fd0031dbddbecb2a4770848aca8/environment.json)。

管理浏览器最终运行 `a63c69c1bf1104d708a49b9e4e3661a0`：

- [桌面原始响应](story-3.2/browser/runs/a63c69c1bf1104d708a49b9e4e3661a0/network-1280.json)、[手机原始响应](story-3.2/browser/runs/a63c69c1bf1104d708a49b9e4e3661a0/network-390.json)、[前后存储与不变量](story-3.2/browser/runs/a63c69c1bf1104d708a49b9e4e3661a0/storage.json)。新增4条停用与4条创建审计，原夹具预约/停用事实不变，全部槽完整。
- [桌面初始页面](story-3.2/browser/runs/a63c69c1bf1104d708a49b9e4e3661a0/initial-1280.png)、[手机初始页面](story-3.2/browser/runs/a63c69c1bf1104d708a49b9e4e3661a0/initial-390.png)、[手机停用冲突](story-3.2/browser/runs/a63c69c1bf1104d708a49b9e4e3661a0/block-conflict-390.png)、[手机预约冲突](story-3.2/browser/runs/a63c69c1bf1104d708a49b9e4e3661a0/booking-conflict-390.png)。同目录保存创建等待、成功、加载、空结果、字段错误、CSRF拒绝、未知结果和失效截图。

## 环境、失败记录与取证机制

实际运行基线为 macOS 26.6 arm64、Python 3.12.14、SQLite 3.53.1、Flask 3.1.3、Jinja2 3.1.6、Werkzeug 3.1.9、Waitress 3.0.2、Playwright 1.58.2。浏览器使用 `/Applications/Google Chrome.app/Contents/MacOS/Google Chrome`，其实际版本记录在各浏览器报告环境中。不宣称这些是最新版本。

首次使用默认浏览器路径在 `chromium.launch` 阶段失败，未执行页面断言，已保留 [INCOMPLETE 报告](story-3.2/browser/startup-failure.json)与[原始输出](story-3.2/browser-startup-failure.txt)。随后显式使用已安装 Chrome，完整执行通过。初版通过后补齐“创建成功、自动列表刷新失去权限”的反馈与3项处理器断言，再完成最终全量和所有原始验证；初版成功报告分别保存在 browser/http 的 `prior-success-before-feedback-fix.json`，不会用作最终源码证据。

新 runner 复用已验证的 POSIX 进程组、浏览器注册清理和独立 Waitress 进程生命周期。每次先将最终报告写为 INCOMPLETE，使用独立 `runs/<run_id>`；前后比对应用及 runner/helper SHA-256，只有实际断言、停止服务和临时目录清理完成才写 PASS。数据库和随机凭证只在私有临时目录，凭证文件权限600；不写默认演示数据库，不保存 cookie、CSRF、口令或 token 摘要。故障 writer 和固定 Clock 仅在 TESTING 配置中注入，无生产 HTTP 后门。

## 复跑

```bash
.venv/bin/python -m unittest discover -s tests -v
node --test tests/test_*js.cjs
.venv/bin/python -m scripts.verify_maintenance_block_http --output-dir work/maintenance-block-http
.venv/bin/python -m scripts.verify_maintenance_block_browser --output-dir work/maintenance-block-browser
.venv/bin/python -m scripts.verify_room_management_browser --output-dir work/block-room-regression
.venv/bin/python -m scripts.verify_auth_browser --replay --port 8005 --output-dir work/block-booking-regression
.venv/bin/python -m scripts.verify_member_cancel_browser --output-dir work/block-cancel-regression
```

浏览器依赖安装见 README；本次实际浏览器命令均另带 `--browser-executable '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'`。新管理 runner 8008，原房间8007、预约8005、本人取消8006；HTTP随机空闲端口。

Story 3.2 范围内实现与验证完成。未实现管理员取消预约、撤销停用或可执行这两种行为的通用终态函数，未开展实验 A，也未操作 Git/远端。跨登录导航不自动恢复草稿；浏览器大于2^53的数字ID精度沿用既有页面边界，服务端仍严格支持正64位ID。未声称真实用户试用、生产 SLA 或本故事之外的能力。

## 独立评审后最终核验

三层评审及父流程13条逐条分类，归并11项直接修补，0defer。全部修补及定向证据见[修补记录](story-3.2-review-fixes/implementer/verification.md)。

主流程实际重跑全量 **156个唯一Python测试、208项JS**，无skip。20轮真实HTTP预约/停用竞争，预约胜8轮、停用胜12轮；全部最终状态、审计、故障回滚和真实重启通过。新维护浏览器已验证1280/390，主流程另跑既有房间管理、创建重放和本人取消三套浏览器回归，均通过。五份报告的应用及验证源码SHA-256重新计算全部匹配，详见[父流程最终核验](story-3.2-review-fixes/parent-final-qa.json)。初版及失败证据均保留；初版源代码补丁另有可重建快照验证。

实现调用共2次：初始实现1次，评审修补1次，无传输失败。技术接受来自AI流程，不代表人类/教师验收。新增管理组合页的身份联动属于本故事集成；不把每次修改既有rooms.js自动算为3.1完成后返工。
