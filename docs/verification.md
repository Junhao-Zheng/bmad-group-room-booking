# 验证索引

原始初稿、失败日志和各次修补证据保留；PASS只表示对应版本和定义的断言通过。各故事测试规模不能相加，最终Python按unittest唯一ID计数，JS按Node实际测试数量计数。

## 当前Epic 4验收

本机schema v6、合成账号的新增流程分别见[身份](evidence/human-review/identity-verification.md)、[审批](evidence/human-review/booking-verification.md)、[取消](evidence/human-review/cancellation-verification.md)、[8周周期](evidence/human-review/weekly-verification.md)、[批量维护](evidence/human-review/maintenance-verification.md)。[本次网站反馈处理](evidence/feedback-2026-11-17.md)补充了开放时间、人数、列表筛选和导师归属检查。截至2026-11-17，完整回归260项Python、415项JS均通过；真实Chrome桌面1280×900和手机390×844完成申请、审批、逐场取消、批量停用及撤销。当前schema v6的真实Waitress重启验证覆盖周期申请/审批、取消申请/确认及批量维护重放；运行`.venv/bin/python -m scripts.verify_epic4_restart --output-dir work/rerun/epic-4-restart`。当前版NFR-03按[新负载原始证据](evidence/human-review/epic4-performance/README.md)通过，200次测量P95为16.893ms、0错误；下文原208项和21.501ms报告均为旧版本证据。

当前浏览器复跑命令：`.venv/bin/python -m scripts.verify_supervised_booking_browser --browser-executable '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome' --output-dir work/rerun/epic-4-browser`。

## 本地基本回归

在README初始化依赖后运行：

```bash
.venv/bin/python -m unittest discover -s tests -v
node --test tests/test_*js.cjs
```

Python用例需要本地回环连接和POSIX进程组（已测macOS，辅助工具支持macOS/Linux）；应用本身无Node运行依赖。单元级runner故障测试使用明确测试替身，不伪称是真浏览器。实际浏览器证据另行运行。

## 浏览器工具

应用依赖与浏览器测试工具分开。安装Node后，在项目目录运行：

```bash
npm install --prefix work/browser-tools --no-save playwright@1.58.2
```

实际脚本以`--browser-executable`指定已有Chrome/Chromium。若使用Playwright自带浏览器，再执行其安装命令；安装目录不提交Git。所有浏览器验证使用独立临时数据库和合成账号，不连接个人浏览器，不把默认演示数据库当测试库。

## 非功能需求

|需求|标准|实际复跑入口|
|---|---|---|
|NFR-01 一致性|20个不同意图恰1成功19冲突；20同意图同一记录；三种两请求竞争各20轮，核对最终完整状态|`scripts.verify_create_booking_http`、`scripts.verify_replay_intent_http`、`scripts.verify_room_management_http`、`scripts.verify_maintenance_block_http`、`scripts.verify_admin_cancel_http`|
|NFR-02 认证隐私|匿名/过期/退出/成员甲乙/admin直接API矩阵，服务层新鲜身份，Origin/CSRF，精确DTO、纯文本和无凭据业务输出|最终权限矩阵及各故事安全用例；真浏览器和HTTP证据|
|NFR-03 查询性能|10房间1000记录，10认证客户端，20预热、200完整样本，最近秩P95≤1000ms|`scripts.verify_availability_performance`；[当前版结果](evidence/human-review/epic4-performance/performance-result.json)|
|NFR-04 持久追溯|实际停进程、新PID重启，业务/槽/审计/旧成功意图一致，审计失败完全回滚|最终重启报告及各写入故障测试|

性能负载包含4种实际SQL查询和1种人数超容量的空集快速路径（占20%），查询跨度30分钟；不把该结果扩展为最坏4小时查询或生产容量保证。并发客户端屏障证明同时发出请求，不宣称每轮均直接观测服务器锁等待。单独真实锁等待测试另外记录明确同步与时钟边界。

## 故事验证

实验A最初9/9统一判定与后续更广的质量审查分开，见[冻结结果](experiments/run-20261112/README.md)。

|故事|实际验收入口|
|---|---|
|1.1 登录与会话|[认证初次](evidence/story-1.1-verification.md)、[评审后](evidence/story-1.1-post-review-verification.md)、[史诗复盘修补](evidence/epic-1-followup/verification.md)|
|1.2 目录与共享日程|[日程](evidence/story-1.2-verification.md)|
|1.3 可用性|[最终故事验收](evidence/story-1.3-reviewed-verification.md)、[当时性能原始结果](evidence/story-1.3-performance-reviewed/performance-result.json)|
|2.1 创建|[创建及竞争](evidence/story-2.1-verification.md)|
|2.2 原意图确认|[重放](evidence/story-2.2-verification.md)|
|2.3 个人历史|[历史](evidence/story-2.3-verification.md)、[完成后超时测试修正](evidence/history-timeout-fixture-fix/verification.md)|
|2.4 本人取消|[取消](evidence/story-2.4-verification.md)|
|2.5 管理员取消|[整合验收](evidence/story-2.5-verification.md)|
|3.1 房间维护|[维护及容量竞争](evidence/story-3.1-verification.md)|
|3.2 停用与管理查询|[停用](evidence/story-3.2-verification.md)|
|3.3 撤销停用|[整合验收](evidence/story-3.3-verification.md)|
|3.4 审计与重启交接|[审计、真实重启、备份](evidence/story-3.4-verification.md)|

每张故事卡附验收矩阵，评审原文与逐项裁决在`docs/evidence/reviews/`。实际证据在相应run_id下保留，源码哈希对应当时版本；后续版本应看最终验证记录，不能把历史哈希说成当前HEAD。

## 真实HTTP复跑命令

以下脚本启动自己的临时Waitress，不需要预先启动README演示服务。输出到新的目录，避免覆盖已交付证据。固定测试时钟仅用于隔离验证；审计与真实重启脚本使用生产SystemClock。应用没有HTTP改时钟或注入故障接口。

```bash
.venv/bin/python -m scripts.verify_create_booking_http --output-dir work/rerun/create
.venv/bin/python -m scripts.verify_replay_intent_http --output-dir work/rerun/replay
.venv/bin/python -m scripts.verify_member_cancel_http --output-dir work/rerun/member-cancel
.venv/bin/python -m scripts.verify_room_management_http --output-dir work/rerun/rooms
.venv/bin/python -m scripts.verify_maintenance_block_http --output-dir work/rerun/maintenance
.venv/bin/python -m scripts.verify_admin_cancel_http --output-dir work/rerun/admin-cancel
.venv/bin/python -m scripts.verify_block_revoke_http --output-dir work/rerun/revoke
.venv/bin/python -m scripts.verify_audit_http --output-dir work/rerun/audit
.venv/bin/python -m scripts.verify_availability_performance --output-dir work/rerun/performance
```

## 真实浏览器复跑命令

以下为macOS Chrome示例，Linux改成实际可执行文件路径；需要本机相应浏览器及字体。各命令先验证自己的端口可用，不接管正在使用的服务。输出中故障注入页面是受控测试，不能误当作正常使用结果。

```bash
.venv/bin/python -m scripts.verify_auth_browser --replay --booking --availability --schedule --browser-executable '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome' --output-dir work/rerun/member-browser
.venv/bin/python -m scripts.verify_history_browser --browser-executable '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome' --output-dir work/rerun/history-browser
.venv/bin/python -m scripts.verify_member_cancel_browser --browser-executable '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome' --output-dir work/rerun/cancel-browser
.venv/bin/python -m scripts.verify_room_management_browser --browser-executable '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome' --output-dir work/rerun/rooms-browser
.venv/bin/python -m scripts.verify_maintenance_block_browser --browser-executable '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome' --output-dir work/rerun/maintenance-browser
.venv/bin/python -m scripts.verify_admin_cancel_browser --browser-executable '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome' --output-dir work/rerun/admin-cancel-browser
.venv/bin/python -m scripts.verify_block_revoke_browser --browser-executable '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome' --output-dir work/rerun/revoke-browser
```

```bash
.venv/bin/python -m scripts.verify_audit_browser --browser-executable '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome' --output-dir work/rerun/audit-browser
```

3.4首次接受时完整回归为208项唯一Python、313项JS、0跳过，见[父流程最终核验](evidence/story-3.4-review-fixes/parent-final-qa.json)。接受源码提交为`82b4b567f27c788e062a7bc8310d0c660c69d666`。修补后138项路由权限、真实重启与双视口精确显示验证各自保存58项源码哈希并已复算。

初版的[联合NFR与浏览器报告索引](evidence/story-3.4/acceptance-summary.json)仍按原哈希保留，其中NFR03为21.500958ms/200样本/0错误。本次修补仅涉及audit DTO/页面、备份CLI与验证脚本，未改可用性或占用写事务；不把历史报告的全部源码哈希当成当前版本。最终交付另从新副本安装运行，结果单独列明。


## 解释范围

这是本机、合成数据、所列浏览器及规定负载的实测证据，不证明生产稳定性。JS使用Number，超出安全整数的极大数据库ID在管理操作中明确拒绝，API仍按正64位ID合同校验；首版不为这种不现实的演示数据改全部JSON合同。目录中只要含不安全ID就整批拒绝；即使有安全条目，旧选项失效后也不能靠重复刷新同一无效目录恢复，未实现部分目录可用模式。没有人为身份信息、真实口令、Cookie或运行数据库需要交到仓库。

## 最终史诗修补

原修补通过208唯一Python/376 JS，当时独立三镜头因429无报告，记录保留在[历史核验](evidence/epic-3-followup/parent-final-qa.json)。2026-11-13继续独立复核并修补后的最新全量为208唯一Python/399 JS、0跳过，见[本轮核验](evidence/epic-3-followup/review-fixes/verification.md)。真实Chrome双视口验证已提交但响应丢失、等待禁用、失败刷新及重新确认；61项源码哈希已复算。后端与依赖未改，历史138权限/重启/并发/性能和审计浏览器按原报告版本保留。

新增管理复跑：`.venv/bin/python -m scripts.verify_epic3_followup_browser --browser-executable '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome' --output-dir work/rerun/admin-followup`。

## 全新副本交付检查

[实际安装及全量检查](evidence/delivery/README.md)通过：Python3.12.14/SQLite3.53.1，新虚拟环境从uv.lock安装，208唯一Python、376 JS，0skip，真实Waitress初始化/登录/退出验证；原目录虚拟环境和数据库未复制。该报告对应581e3878b4a92942be919deb22f73160a728ae7e；本轮前端/测试已变，未重复安装验证，不声称旧报告覆盖当前全部代码。后端与锁文件未变，当前完整回归另见上节。
