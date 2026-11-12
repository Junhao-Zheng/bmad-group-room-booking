# Story 3.4 实施与联合验证

实施完成，待主流程独立评审。依据 FR-21/22、NFR-01—04、ADR-07/08、UX-DR8/9/10。所有结果来自本次实际执行；没有 Git 或远端操作，没有写入真实演示库。人工课程材料和录屏由主流程整理。

## 变更

- `services.audit_events` 在短只读事务内重新认证管理员、以同一次 Clock 取时；对象类型严格限定 room/booking/block，北京日按事件时间半开过滤，`occurred_at,id` 均降序，不分页。
- `dto.audit_event` 精确白名单，before/after 解析为对象/null，并核验各类快照键和基本类型。损坏数据整体安全 500；成员 403，过期/退出/匿名 401。
- `/admin` 新增操作记录筛选、加载/空/错误/失效反馈，长内容可展开，用户文本全部 `textContent`，表格局部横滚。复用 `admin-auth-lost`；失效清结果、阻止晚到响应恢复敏感数据。
- `scripts.backup_db` 通过 `Connection.backup` 保存一致副本，独立目标 0600、不覆盖源或已有目标，完成完整性/外键检查。README 提供路径/schema 检查、loopback 启动、备份、停服恢复、清会话、旧 WAL/SHM 隔离和回退步骤。

## AC 证据

| 验收 | 实际结果 | 原始证据 |
| --- | --- | --- |
| AC-3.4-1 | 类型/北京日期过滤、时间/ID倒序、完整actor快照/action/target/前后值/原因；成员403；损坏JSON安全500 | [Python tests](python-tests.log)、[HTTP](http/result.json)、[Browser](browser/result.json) |
| AC-3.4-2 | 7种真实动作全部出现，重复意图/取消/撤销/同值更新审计不变；全部快照仅业务键，无认证凭据 | [HTTP operations](http/runs/9341bc2356e9503b58ad28ab7f754333/operations.json)、[audit unit/handler tests](js-tests.log) |
| AC-3.4-3 | Waitress PID 74169 完全停止后启动 PID 74181，1房间/5记录/6槽/10审计逐字段及关联哈希完全相同；3个旧会话仍可用，原已取消预约意图返回同一ID，审计仍10 | [restart](http/runs/9341bc2356e9503b58ad28ab7f754333/restart.json)、[before](http/runs/9341bc2356e9503b58ad28ab7f754333/before-restart.json)、[after](http/runs/9341bc2356e9503b58ad28ab7f754333/after-restart.json)、[replay](http/runs/9341bc2356e9503b58ad28ab7f754333/replay-after-restart.json) |
| AC-3.4-4 | schema=1，实际DB绝对路径/启动命令/Python/SQLite/依赖/OS/CPU/内存已保存；backup API实测包含提交WAL、排除未提交事务，拒绝源/已有目标，副本检查通过 | [environment](http/runs/9341bc2356e9503b58ad28ab7f754333/environment.json)、[backup](http/runs/9341bc2356e9503b58ad28ab7f754333/backup.json)、[tests](python-tests.log)、[README](../../../README.md) |

## 四项 NFR 联合复核

| NFR | 本次真实复跑 |
| --- | --- |
| NFR-01 | [20成员同槽](nfr-create/create-http-result.json)：1×201、19×409；[20同意图](nfr-replay/replay-http-result.json)：1×201、19×200且同ID；[预约/降容量20轮](nfr-room/http-result.json)、[预约/停用20轮](nfr-block/http-result.json)、[本人/管理员取消20轮](nfr-admin-cancel/http-result.json)均通过，保存全部响应及最终数据库断言。 |
| NFR-02 | [全路由权限矩阵](http/runs/9341bc2356e9503b58ad28ab7f754333/permissions.json)共138个断言，覆盖匿名/到期/退出/成员甲/乙/admin、全部HTML/API/静态路由；成功业务路径另由operations及浏览器验证。全量测试覆盖Origin/CSRF、所有权、XSS纯文本、精确白名单及安全错误日志。 |
| NFR-03 | [性能](nfr-performance/performance-result.json)：10房间、1000预约、10认证客户端、20预热+200测量完整样本；0错误/0错误结果，最近秩P95=21.501ms ≤1000ms。保留原先各次证据，本次新增完整复跑；负载仍为已登记30分钟查询（80%SQL、20%人数1001快路径），不宣称4小时/长停用最坏性能。 |
| NFR-04 | 新真实Waitress重启/旧会话/取消后旧意图重放通过。上述HTTP回归保存审计失败前后完整业务/槽/审计回滚；admin取消还验证writer插入前/后及COMMIT失败。备份一致性另由4项backup测试与热库副本比对验证。 |

## 浏览器与全量检查

- 全量 **201 Python tests、296 JavaScript tests** 全部通过，无 skip。新功能新增9项Python测试和14项实际JS处理器回归，覆盖正文超时、手动恢复、错误响应、精确DTO、纯文本和失效后晚到响应。
- [audit Chromium](browser/result.json)：1280×800、390×844，正常/过滤/空/加载/错误恢复/退出后失效/成员403、登录退出，页面无横溢出；Chrome 157.0.8103.51，Playwright 1.58.2。截图已查看，表格横滚限制在结果区。
- 既有真实浏览器流程均通过两个视口：[房间](regression-room/browser-results.json)、[停用创建](regression-block/browser-results.json)、[停用撤销](regression-revoke/browser-result.json)、[本人取消](regression-member/browser-results.json)、[管理员取消](regression-admin/browser-results.json)、[登录/共享查询/预约创建与可靠重放](regression-booking/browser-results.json)。
- 新HTTP/浏览器runner按独立run目录保存，先INCOMPLETE后PASS；最终报告保存前后未变化源码指纹及真实启动/进程清理记录。汇总 [acceptance-summary.json](acceptance-summary.json) 直接读取上述结果并保存摘要哈希。

## 失败保留与边界

初次新HTTP runner两次在验证器自身失败：导入token摘要函数名错误、到期夹具未同时调整created_at而触发CHECK；均已修正并完成全路由复跑。新浏览器初次将退出URL错误匹配为不含查询参数的/login，已改为实际/login?logged_out=1并通过。新验证器早期复用环境助手时继承了性能脚本invocation与固定Clock标签，最终报告已显式记录本runner命令及production SystemClock，完成重跑。早期独立run与INCOMPLETE结果保留。

既有browser runner首次默认Playwright Chromium不可用而在startup失败；未作为产品缺陷，原失败结果/命令日志保留，显式传入已安装Chrome后全部通过。测试用户密码/会话原文仅在临时内存或0600临时文件，临时库与凭证已清理；证据仅保留合成业务事实。成功意图key仅在数据库事实证据中保存SHA-256，不混入审计快照。

没有声称执行灾难恢复演练、真实成员试用、教师M1/M2批准或人工验收。恢复/回退为可执行运维说明；录屏及人工材料不属于此子任务。
