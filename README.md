# 课题组活动与会议室预约

软件工程管理课程原型：以 BMAD 需求、架构、故事、两轮增量和实际验证组织交付。实验 B 按用户转述的教师安排免做，实验 A 的初版、统一评审和局限单独保存。

12个故事均已完成技术验收；208项Python与376项JavaScript测试通过。最终史诗复盘保留独立复核缺口；视频与全新副本检查的交接状态见课程核对；人类要求未全部满足，详见下文。

## 先看课程材料

|内容|入口|
|---|---|
|课程要求逐项核对与未满足项|[课程核对](docs/course-audit.md)|
|问题、假设与需求|[产品简述](_bmad-output/planning-artifacts/product-brief.md)、[PRD](_bmad-output/planning-artifacts/PRD.md)|
|技术取舍与规则|[架构及8项ADR](_bmad-output/planning-artifacts/architecture.md)、[16条项目规则](project-context.md)|
|3个史诗、12个故事、验收与状态|[史诗与验收](_bmad-output/planning-artifacts/epics.md)、[当前状态](_bmad-output/implementation-artifacts/sprint-status.yaml)|
|两轮增量|[Sprint 1](docs/sprints/sprint-1-review.md)、[Sprint 2](docs/sprints/sprint-2-review.md)|
|需求到实际验证|[追踪矩阵](docs/traceability.md)、[验证索引](docs/verification.md)|
|人机决策与过程复盘|[真实人工决策](decision-log.md)、[五指标复盘](retrospective.md)|
|实验 A|[预登记协议](docs/experiments/experiment-a-protocol.md)、[实测结果](docs/experiment-a-results.md)|
|贡献与AI使用|[实际贡献及AI声明](docs/ai-use-and-contributions.md)、[可见会话节选](docs/evidence/conversations/README.md)|
|约10分钟演示|[视频](docs/demonstration/course-demo.mp4)、[讲稿与字幕](docs/demonstration/README.md)|

人类决策目前仅有4条真实范围记录、0次技术否决，尚未满足讲义的至少15条及5次人工否决/实质修改。范围记录能否计分仍由教师判断。AI评审、合成演示和压缩迭代不冒充真实用户访谈、教师M1/M2、学生分工或四周课堂经历。可用[本人复核清单](docs/human-review-worksheet.md)补充真实判断；待填问题不是已经发生的决策。

## 功能

成员可查询会议室与共享日程、按时段人数查找空闲房间、创建活动、确认丢失响应的原提交意图、查看个人记录并取消本人尚未开始的预约。管理员可维护房间、保护已有预约容量、安排或撤销停用、说明原因取消未结束预约、查询完整业务和操作记录。

所有时间以北京时间输入/显示；半小时粒度，预约最长4小时、提前30天，停用可跨日。预约和停用互斥。取消/撤销保留历史，重复操作保留首次事实。当前规则由AI在用户授权下拟定，真实课题组现状仍待验证。

## 本地运行

固定 Python 3.12.14；其链接的 SQLite 须 ≥3.51.3，启动会检查版本及 Asia/Shanghai 时区。应用依赖由 `uv.lock` 锁定。使用已安装的 `uv`，在本项目目录执行：

```bash
uv python install 3.12.14
uv sync --frozen --python 3.12.14
uv run --frozen python -m scripts.init_demo
uv run --frozen python -m scripts.seed_demo_rooms
uv run --frozen waitress-serve --listen=127.0.0.1:8000 --threads=8 --call booking_app:create_app
```

初始化时以隐藏输入设置 `demo_member_a`、`demo_member_b`、`demo_admin` 三个合成账号的口令（至少12字符），前两者为成员，最后一个为管理员。没有内置共享密码，请保存自己的输入；数据库只存 scrypt 哈希。打开 [本机登录页](http://127.0.0.1:8000/login)。重复初始化只补缺失账号，不重置口令、不清业务；房间种子也只补缺失的合成房间。

非交互初始化可运行 `uv run --frozen python -m scripts.init_demo --credentials-file instance/demo.credentials.json`。文件权限必须为600，结构为 `{"users":[{"username":"…","display_name":"…","password":"…","role":"member或admin"}]}`，至少两名成员、一名管理员。该私有文件及数据库不可提交。默认库为项目根目录的 `instance/booking.sqlite3`；若用 `BOOKING_DB_PATH` 更改路径，初始化和启动必须一致，且须为本机磁盘。

默认仅监听127.0.0.1:8000，Waitress单进程8线程，无debug/reloader。浏览器须使用相同Origin；修改端口时同步配置APP_ORIGIN。普通本地课堂演示无需公网部署。

## 验证与限制

```bash
.venv/bin/python -m unittest discover -s tests -v
node --test tests/test_*js.cjs
```

已实际通过 **208个唯一Python测试、376项JavaScript测试，0跳过**；[最终修补核验](docs/evidence/epic-3-followup/verification.md)。真实HTTP覆盖138项路由权限、7种业务变更和实际停服新PID重启；并发最终完整状态符合互斥/容量约束。NFR03最近一次200个测量样本P95为21.501ms、0错误，负载与限制见验证索引。

浏览器和真实HTTP验证使用独立临时库和合成身份，不改默认演示库。多数规则测试使用固定Clock；最终审计与重启验证使用生产SystemClock，具体以各报告为准。[验证索引](docs/verification.md)提供实际执行结果、完整复跑命令和浏览器工具安装方法；同一应用版本的哈希绑定在对应报告中。历史失败不删除，后续通过记录不覆盖初稿。

本项目面向本地课程演示。单SQLite写入者、半小时粒度、无周期预约/通知/复杂审批、无分页是明确的范围与取舍。房间完整资料编辑采用后提交覆盖，不提供并发编辑版本提示；当前页面保留失败草稿，但跨登录导航不自动恢复。浏览器极大整数编号精度边界及性能负载范围在验证材料中披露。

## 数据备份与恢复

启动使用本地文件库、单进程 Waitress 8 线程及 loopback。最终 schema 为 `PRAGMA user_version=1`，缺表或版本不匹配时停止，不自动迁移。以下只读检查同时报告最终解析的数据库绝对路径、schema 与运行时：

```bash
.venv/bin/python - <<'CHECK_DB'
from booking_app import default_database, check_runtime, db
check_runtime()
path = default_database()
db.check_database(path)
with db.read_transaction(path) as conn:
    print({"database": path, "schema_version": conn.execute("PRAGMA user_version").fetchone()[0],
           "journal_mode": conn.execute("PRAGMA journal_mode").fetchone()[0]})
CHECK_DB
```

备份可以在服务运行中执行。指定一个**尚不存在的独立目标文件**，使用 SQLite `Connection.backup` 读取一致快照，包括已提交 WAL；不复制运行中的主文件。CLI 在完成后检查 `integrity_check` 与 `foreign_key_check`，报告时间/路径/schema，目标权限为 600；源路径、已有文件和符号链接目标不会被覆盖。目标目录请使用本地部署者私有目录：

```bash
mkdir -m 700 -p backups
.venv/bin/python -m scripts.backup_db backups/booking-2026-11-12.sqlite3
# 或显式指定源（初始化、服务与备份须指向同一个实际文件）
.venv/bin/python -m scripts.backup_db --source /absolute/local/booking.sqlite3 backups/booking-manual.sqlite3
```

CLI 的完整性/外键检查只证明 SQLite 结构有效；`schema_version=0` 或仅结构有效的副本不构成本应用兼容的恢复备份。应用恢复必须通过 `schema=1` 和 `db.check_database` 检查。目标同名 `-wal`、`-shm`、`-journal`（含悬空符号链接）已存在时，CLI 会拒绝复制。

被终止或中断、未成功完成 CLI 的副本不是已完成备份；请使用新的目标重试，不以文件存在判断成功。外部独占锁可能使复制持续等待，直到锁释放或操作被中断；CLI 不提供完成时限保证。

恢复仅在停止 Waitress 并确认没有其他读写进程后进行：

1. 用上述 backup CLI 备份当前库至新的回退文件，再校验准备恢复的副本。保留当前文件及停服后的同名 `-wal`、`-shm` 于同一个私有回退目录；不可把旧 sidecar 留在新库旁。不要在运行时删除 WAL。
2. 将已检查副本通过 backup CLI 写至已腾空的原数据库路径。副本来自本 CLI 时是自包含文件，无需携带 sidecar。确认路径、权限 600 和目录权限 700；不要覆盖唯一回退副本。
3. 使用下列命令核验 schema/完整性，重新启用 WAL 并清空会话。所有用户须重新登录，预约/停用/审计/成功意图历史不改写。
4. 按原 Waitress 命令启动，核对房间、预约、停用、槽和审计数量/关键字段、槽关联与新登录。失败则再停服，将失败的新库及其 sidecar 单独保存，再按步骤 2—3 用回退备份恢复，重新验证后启动。

```bash
# 仅停服且已将已检查副本恢复至 BOOKING_DB_PATH 后执行
.venv/bin/python - <<'RESTORED_DB'
from booking_app import default_database, db
path = default_database()
conn = db.connect(path)
try:
    assert conn.execute("PRAGMA user_version").fetchone()[0] == 1
    assert conn.execute("PRAGMA integrity_check").fetchall()[0][0] == "ok"
    assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
    assert conn.execute("PRAGMA journal_mode=WAL").fetchone()[0] == "wal"
finally:
    conn.close()
db.check_database(path)
with db.write_transaction(path) as conn:
    conn.execute("DELETE FROM sessions")
RESTORED_DB
```


备份一致性已经实测；停服恢复和回退是交接步骤，没有冒充已经进行的灾难演练。

## 过程真实性与第三方来源

Git提交、状态事件、实现调用和完成后返工均按实际发生保存。独立AI上下文不是人类组员；精确模型标识不可核验，不能猜填。实验A报告明确同模型配置继承、AI操作者、指令隔离及任务不完全等价的局限。

本次工具为Codex桌面宿主、Python 3.12.14、SQLite 3.53.1、Flask 3.1.3、Jinja2 3.1.6、Werkzeug 3.1.9、Waitress 3.0.2、Node v26.8.1、Playwright 1.58.2及Chrome 157.0.8103.51；见[实测版本](docs/evidence/tool-versions.json)。

BMAD Method 6.12.1已保存在仓库，无需重装覆盖。来源与MIT许可见[第三方说明](docs/third-party-notices.md)。教师原讲义、真实凭证、运行数据库、备份和安装目录不在仓库内。
