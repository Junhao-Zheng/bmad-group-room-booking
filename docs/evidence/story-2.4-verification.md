# Story 2.4 验证记录

执行日期：2026-11-12。覆盖 FR-14/21/22，NFR-01/02/04，ADR-03/06/07，UX-DR6/9/10。全部账号、预约和用途是合成验证数据；以下记录是实际 AI 实施与自动化运行结果，不是课题组试用、教师评审或实验 A 结果。

## 结果与范围

- Python 全量 **119 项通过、无 skip**：[原始输出](story-2.4-tests.txt)。新增 8 个 `MemberCancelTests` 测试直接继承 `unittest.TestCase`，未继承已有测试类来重复计数。
- JavaScript 全量 **71 项通过、无 skip**：[原始输出](story-2.4-js-tests.txt)。其中新增 17 项执行真实 history.js 处理器，覆盖确认、请求格式、头/正文超时、网络/JSON/不完整响应、403/404/409/500、控件恢复、无自动重试、失效、列表刷新失败与跨表单焦点。此前 54 项保留。
- 真实 HTTP：**20 个独立登录会话和 CookieJar** 经屏障同时请求同一预约取消，**20×200**、响应元数据一致；最终 **1 预约、0 槽、1 创建审计、1 成员取消审计**。全部响应及最终存储有断言，没有用锁超时替代成功。[结果](story-2.4-http/http-result.json)、[输出](story-2.4-http-run.txt)。
- 真实 Chromium：Chrome **157.0.8103.51**、Playwright **1.58.2**，**1280×800、390×844** 均通过，页面 scrollWidth 等于视口宽度、无页面脚本错误。[结果](story-2.4-browser/browser-results.json)、[输出](story-2.4-browser-run.txt)。
- 原个人历史四态筛选、详情、纯文本、空态、拒绝/失效及键盘流程回归通过：[历史回归](story-2.4-history-regression/browser-results.json)。登录退出、共享日程、可用性、预约创建冲突、提交响应丢失重放与新意图流程回归通过：[既有预约回归](story-2.4-replay-regression/browser-results.json)。

## 验证器清理缺陷与返工

第二次全量复核中，已复用的 Story 2.3 `stop_process_group` 在 timeout 清理分支的 `killpg(group_id, 0)` 抛出 `PermissionError`，导致当次 **116 项中 1 项错误**；[原始失败](story-2.4-tests-cleanup-failure.txt)完整保留，未把它写成成功。随后[原定向 3 项复验](story-2.4-cleanup-recheck.txt)通过，但不能据此否认缺陷。

[真实快速退出探针](story-2.4-cleanup-probe.txt)执行 100 次本 runner 自己启动的进程组终止，其中 92 次复现 PermissionError；每次立即记录的该组成员都仅为 Z 状态，`poll()` 得到 -15，无实际存活成员。这证明存在僵尸退出窗口的错误判定；首次全量失败瞬间的成员未额外采样，因此不冒称已直接测得首次现场。

修补仅涉及既有 `scripts/verify_history_browser.py` 的信号助手：收到 PermissionError 后成功枚举组内状态，仅当没有任何非 Z 成员时判定退出；若有存活成员或枚举失败，仍抛错，不能产生 PASS。父流程已将此登记为 Story 2.3 完成后返工。新增 3 项回归分别检查 20 次真实快速退出、活组权限错误不可吞掉、枚举失败不可视为清理成功；原 detached Chromium 超时/失败与无关 sentinel 保护仍通过。[修补定向输出](story-2.4-cleanup-fixed-tests.txt)和[最终全量 119 项](story-2.4-tests.txt)保存原始结果。新取消浏览器、原历史浏览器及 HTTP runner 已在修补后实际复跑，结果中的 helper SHA-256 与当前文件一致。

## 验收矩阵

| 验收 | 实际断言与证据 |
| --- | --- |
| AC-2.4-1 | 本人待开始预约确认后返回精确 BookingFull、200 cancelled，cancel_reason 为 null，取消时刻使用统一 Clock、操作者为当前数据库身份。完整历史/intent/request_payload 保持，所有所属槽删除，唯一 booking.cancelled_by_member 审计含完整 before/after。测试捕获事务连接并断言 writer 收到同一对象。浏览器逐字段核对取消时刻、操作者、原因、列表状态；前后业务存储校验通过。 |
| AC-2.4-2 | 首次 t=start−1 成功，t=start、start+1、结束等号拒绝 409；管理员本人入口同样遵循开始期限。已经取消的本人记录在 start/end 及以后仍返回原时刻/操作者/原因，writer 零调用；已有合成管理员取消原因也不覆盖。HTTP 重启后使用总是抛错的 writer，重复取消及旧成功 intent 重放仍 200 且 cancelled。 |
| AC-2.4-3 | 成员/管理员他人、已取消他人、不存在、最大合法不存在 ID 和 block ID 均返回同一 404 正文；先限定所有权再幂等，不泄露完整数据。Origin/CSRF 在服务前拒绝；匿名/退出/精确会话过期先 401；严格空对象和 ID 错误 400。所有拒绝前后存储不变。 |
| AC-2.4-4 | 审计 INSERT 前和 INSERT 后故障均完整回滚预约/槽/审计；真实独立 Waitress 进程审计故障后存储逐字段等于原快照。恢复正常 writer 后可取消并重新预约同槽；重启保留取消记录和原 intent。 |
| 并发与持久化 | 20 个真正独立登录会话并发取消全部返回同一编号及相同元数据，最终一次转换/一次取消审计；实际停止并启动服务器后，重复请求和原意图重放仍保持取消事实。成员/admin 竞争留给 2.5，未声称完成。 |
| 页面确认与恢复 | 未勾选确认时零 POST；真实 CSRF 403 后详情不变、确认框/按钮可操作。服务成功后故意截断浏览器响应，页面保留原记录并仅手动重试同 ID，数据库仍只一次取消。成功自动刷新个人列表，重新进入首页可用性 DOM 和共享日程查询立即无该占用，原时段可新建。已开始/已结束解释不能取消，旧页面会话失效清空敏感数据。成功时焦点保持在已聚焦的退出表单。 |

## 原始证据

- 新取消浏览器运行 `4b0edd1b2b234d52adfa35a10147884f`，时间 `2026-11-12T11:25:46.066458+00:00` 至 `2026-11-12T11:25:54.110008+00:00`。结果文件记录所有应用文件/runner/helper SHA-256，前后指纹一致；复用 `verify_history_browser` 的进程组/Chromium 注册与强制回收逻辑，清理完成后才置 PASS。
- [桌面原始响应](story-2.4-browser/runs/4b0edd1b2b234d52adfa35a10147884f/cancel-network-1280.jsonl)、[手机原始响应](story-2.4-browser/runs/4b0edd1b2b234d52adfa35a10147884f/cancel-network-390.jsonl)、[浏览器最终存储](story-2.4-browser/runs/4b0edd1b2b234d52adfa35a10147884f/storage.json)。最终 **11 条历史记录、9 槽、6 审计**；原夹具 9 条中只有 103/104 发生真实成员取消，另外两条新建后取消；四次取消、两次创建各自一次审计，其他记录逐字段不变。
- [桌面成功](story-2.4-browser/runs/4b0edd1b2b234d52adfa35a10147884f/cancel-success-1280.png)、[手机成功](story-2.4-browser/runs/4b0edd1b2b234d52adfa35a10147884f/cancel-success-390.png)、[手机拒绝](story-2.4-browser/runs/4b0edd1b2b234d52adfa35a10147884f/cancel-rejected-390.png)、[加载](story-2.4-browser/runs/4b0edd1b2b234d52adfa35a10147884f/cancel-loading-390.png)、[响应未知](story-2.4-browser/runs/4b0edd1b2b234d52adfa35a10147884f/cancel-response-unknown-390.png)、[手动确认](story-2.4-browser/runs/4b0edd1b2b234d52adfa35a10147884f/cancel-retry-confirmed-390.png)、[会话失效](story-2.4-browser/runs/4b0edd1b2b234d52adfa35a10147884f/cancel-session-expired-390.png)。桌面与手机截图经 AI 视觉检查，长标题/用途和确认区域正常换行，无横向溢出。
- HTTP 运行 `4d2bf31f24ba1214893ce90928446243`：[全部并发响应](story-2.4-http/runs/4d2bf31f24ba1214893ce90928446243/concurrent-responses.jsonl)、[竞争后存储](story-2.4-http/runs/4d2bf31f24ba1214893ce90928446243/after-race.json)、[故障前](story-2.4-http/runs/4d2bf31f24ba1214893ce90928446243/before-fault.json)、[故障后](story-2.4-http/runs/4d2bf31f24ba1214893ce90928446243/after-fault.json)、[重启/故障/重放/复用响应](story-2.4-http/runs/4d2bf31f24ba1214893ce90928446243/http-steps.json)、[最终存储](story-2.4-http/runs/4d2bf31f24ba1214893ce90928446243/final-storage.json)、[环境](story-2.4-http/runs/4d2bf31f24ba1214893ce90928446243/environment.json)。最终重新预约后为 2 预约、4 槽、3 审计。
- 历史回归运行 `bc6674f0d81e60363292310453a4b2a5`；既有预约回归运行 `25e92d9e96d97a738692418ae85143bc`，各总结果的 artifact_directory 指向独立产物。早期已经成功的取消运行也保留，最终总结果绑定包含不完整响应和焦点修补的最新代码。

[最终证据核对](story-2.4-final-qa.json)记录 119 个唯一 Python 测试标识、71 项 JS、6 项清理定向测试、四份 PASS 报告的全部源码/辅助脚本哈希核对，以及 51 个 JSON/JSONL 证据文件的敏感凭证键扫描。

## 复跑与剩余边界

```bash
.venv/bin/python -m unittest discover -s tests -v
node --test tests/test_*js.cjs
.venv/bin/python -m scripts.verify_member_cancel_http --output-dir work/member-cancel-http
.venv/bin/python -m scripts.verify_member_cancel_browser --output-dir work/member-cancel-browser
.venv/bin/python -m scripts.verify_history_browser --output-dir work/cancel-history-regression
.venv/bin/python -m scripts.verify_auth_browser --replay --port 8005 --output-dir work/cancel-replay-regression
```

本机三条浏览器命令加 `--browser-executable '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'`。Python 3.12.14、SQLite 3.53.1、Flask 3.1.3、Jinja2 3.1.6、Werkzeug 3.1.9、Waitress 3.0.2，单进程/8线程，固定 Clock 仅测试注入。所有验证使用独立临时库和随机临时凭证；原始证据不含密码、cookie、CSRF 或会话摘要，不操作演示库。未进行 Git 或远端操作。

本故事规定验收完成。管理员取消、成员/admin 竞争、停用撤销与实验 A 首次实现仍属后续故事，未实现通用终态命令。Sprint 1 成员闭环是在 2026-11-12 的实际压缩 AI 迭代形成，不能写成四周团队开发或虚构站会/课堂记录；本证据也不是人类或教师验收。

## 独立评审修补后最终结果

三层评审共16条，逐条分类后全部直接修补，0 defer。主流程实际全量复验 **121个唯一Python测试、86项JS，无skip**；[Python](story-2.4-review-fixes/python-all.txt)、[JS](story-2.4-review-fixes/js-all.txt)。

详情ID及原值校验、畸形信封的未知结果反馈、POST失效与后续GET失效分支、成功事实保留、键盘焦点、pending空态和筛选回归均已补齐。并发runner完整收集worker响应/脱敏异常并保存存储后判失败，新增首worker异常验证；僵尸组PermissionError成功恢复分支有确定性验证。

[新取消浏览器](story-2.4-review-fixes/browser/browser-results.json)1280/390通过，增加真实键盘拒绝/成功/Shift+Tab以及共享日程真实房间日期控件与DOM释放断言。[历史浏览器](story-2.4-review-fixes/history/browser-results.json)和[创建重放回归](story-2.4-review-fixes/replay/browser-results.json)同样通过。主流程重跑[20独立会话取消/故障/重启/复用](story-2.4-review-fixes/http/http-result.json)通过。

[父流程最终核验](story-2.4-review-fixes/parent-final-qa.json)逐一重新计算四份PASS报告所绑定的应用与验证源码哈希，全部匹配。原初稿、失败与各阶段结果保留，不用本次成绩覆盖原始记录。

实现调用共4次：最初2次传输失败且未改动，第3次完成实现并修补实际观察到的2.3清理返工，第4次处理本轮评审。实际生产代码阶段2次；传输故障单列，不当作产品缺陷。
