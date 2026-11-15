# 课题组活动与会议室预约

本次交付范围已由用户确认为本机验证与展示的课程原型（D-019），不包含实际大组联网部署。正式视频和演示仍暂缓。

软件工程管理课程原型：以 BMAD 需求、架构、故事、两轮增量和实际验证组织交付。实验 B 按用户转述的教师安排免做，实验 A 的初版、统一评审和局限单独保存。

原直接预约基线的12个故事均已完成技术验收；208项Python与399项JavaScript测试通过。最后一批修补的独立复核与收口验证已完成，最终史诗技术接受；此前的[全新副本安装检查](docs/evidence/delivery/README.md)已通过；人类要求未全部满足，详见下文。

**当前新增待办（2026-11-15）：**用户已要求学生先申请、由其本人导师批准后才占用房间（D-006），预约提前窗口从30天改为7天（D-007）。已获批预约取消须本人导师在开始前确认，理由是仍由老师管理（D-010）。共享日程增加所属导师，便于识别组会组织者及沟通（D-012）。完整详情按学生本人、导师本人及其学生、管理员全部的范围授权（D-013）。维修停用改为一次原因、批量取消冲突预约并设置停用（D-015）。新增每周固定时段连续申请，保留主动查看结果、不新增消息提醒（D-017；第一场在7天内，每周一次，最多8周，后续场次允许超过7天）。账号由管理员统一创建并绑定导师（D-018），导师身份、学生归属及 schema 1→2 显式升级已在故事4.1实现并用临时库验证。审批、直订拦截、7天窗口及其余新增规则尚未实现，以下旧测试和故事完成状态仍对应原直接预约基线，不表示新增需求全部完成。

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
|本人复核后的变更方案（已批准，实施中）|[影响、五个增量及验收计划](_bmad-output/planning-artifacts/sprint-change-proposal-2026-11-15.md)|
|实验 A|[预登记协议](docs/experiments/experiment-a-protocol.md)、[实测结果](docs/experiment-a-results.md)|
|贡献与AI使用|[实际贡献及AI声明](docs/ai-use-and-contributions.md)、[可见会话节选](docs/evidence/conversations/README.md)|
|约10分钟演示（暂缓）|用户要求本轮先不录制视频和演示；[准备记录](docs/demonstration-plan.md)|

人机决策当前23条记录，含4条早期范围记录、17条政策复核及2条实施边界确认。选择、本人理由和AI整理的依据分别记录；D-021/022/023尚无独立个人理由，多项新增功能尚未实现验证，因此不能仅凭数量宣称课程全部达标。AI评审不替代教师M1/M2、真实组员贡献或四周课堂经历。见[决策日志](decision-log.md)及[本人复核清单](docs/human-review-worksheet.md)。

## 功能

成员可查询会议室与共享日程、按时段人数查找空闲房间、创建活动、确认丢失响应的原提交意图、查看个人记录并取消本人尚未开始的预约。管理员可维护房间、保护已有预约容量、安排或撤销停用、说明原因取消未结束预约、查询完整业务和操作记录。

所有时间以北京时间输入/显示；半小时粒度，预约最长4小时、提前30天，停用可跨日。预约和停用互斥。取消/撤销保留历史，重复操作保留首次事实。规则最初由AI拟定。用户已陈述老师安排、微信群通知及跨导师冲突，经澄清最终选择同一大组内各导师或负责人共用系统预约、重叠自动拒绝；此选择尚不代表各导师实际采用；系统只保证已登记记录的一致性，不保证消除外部安排冲突。其余规则与实际使用价值仍待验证。

## 本地运行

固定 Python 3.12.14；其链接的 SQLite 须 ≥3.51.3，启动会检查版本及 Asia/Shanghai 时区。应用依赖由 `uv.lock` 锁定。使用已安装的 `uv`，在本项目目录执行：

```bash
uv python install 3.12.14
uv sync --frozen --python 3.12.14
uv run --frozen python -m scripts.init_demo
uv run --frozen python -m scripts.seed_demo_rooms
uv run --frozen waitress-serve --listen=127.0.0.1:8000 --threads=8 --call booking_app:create_app
```

初始化时以隐藏输入设置五个合成账号的口令（至少12字符）：`demo_teacher_a`、`demo_teacher_b` 为导师；`demo_member_a`、`demo_member_b` 为学生，分别绑定对应导师；`demo_admin` 为管理员。存储角色仍以 `member` 表示学生，导师为 `teacher`。没有内置共享密码，请保存自己的输入；数据库只存 scrypt 哈希。打开 [本机登录页](http://127.0.0.1:8000/login)。重复初始化只补缺失账号，不重置口令、不清业务；房间种子也只补缺失的合成房间。

非交互初始化可运行 `uv run --frozen python -m scripts.init_demo --credentials-file instance/demo.credentials.json`。文件权限必须为600。每个账号包含 `username`、`display_name`、`password`、`role`（`member` / `teacher` / `admin`）；每名学生还必须显式指定 `supervisor_username`，指向本批次或库中已有的导师。导师/管理员不设置此字段。整批验证失败不会部分写入账号。空库演示入口至少需要两名导师、两名学生、一名管理员；已有 schema 2 库可使用只含单个新账号的 `users` 列表追加。已有账号的密码、角色、显示名与归属一律不覆盖；重复配置不会修复错误或空归属。该私有文件及数据库不可提交。默认库为项目根目录的 `instance/booking.sqlite3`；若用 `BOOKING_DB_PATH` 更改路径，初始化和启动必须一致，且须为本机磁盘。

默认仅监听127.0.0.1:8000，Waitress单进程8线程，无debug/reloader。浏览器须使用相同Origin；修改端口时同步配置APP_ORIGIN。普通本地课堂演示无需公网部署。

## 验证与限制

```bash
.venv/bin/python -m unittest discover -s tests -v
node --test tests/test_*js.cjs
```

已实际通过 **208个唯一Python测试、399项JavaScript测试，0跳过**；[最终修补核验](docs/evidence/epic-3-followup/review-fixes/verification.md)。真实HTTP覆盖138项路由权限、7种业务变更和实际停服新PID重启；并发最终完整状态符合互斥/容量约束。NFR03最近一次200个测量样本P95为21.501ms、0错误，负载与限制见验证索引。

浏览器和真实HTTP验证使用独立临时库和合成身份，不改默认演示库。多数规则测试使用固定Clock；最终审计与重启验证使用生产SystemClock，具体以各报告为准。[验证索引](docs/verification.md)提供实际执行结果、完整复跑命令和浏览器工具安装方法；同一应用版本的哈希绑定在对应报告中。历史失败不删除，后续通过记录不覆盖初稿。

本项目面向本地课程演示。单SQLite写入者、半小时粒度、无周期预约/通知/复杂审批、无分页是明确的范围与取舍。房间完整资料编辑采用后提交覆盖，不提供并发编辑版本提示；当前页面保留失败草稿，但跨登录导航不自动恢复。浏览器极大整数编号精度边界及性能负载范围在验证材料中披露。

## 旧库显式升级与账号归属

schema 1 不能直接启动新代码，初始化命令也不会自动升级。先停服并确认没有其他写入进程；首次验证请使用独立副本，保留原库。下列示例仅操作私有临时目录中的副本（路径按实际副本替换），本故事没有升级真实默认库：

```bash
# 将原有库通过 backup API 复制到尚不存在的测试副本，不复制运行中的主文件
.venv/bin/python -m scripts.backup_db --source /absolute/old-copy.sqlite3 /absolute/private/schema1-copy.sqlite3
# 备份目标必须全新；源路径及同名 sidecar、已有文件、链接均不能用作目标
.venv/bin/python -m scripts.migrate_db --source /absolute/private/schema1-copy.sqlite3 --backup /absolute/private/before-schema2.sqlite3
```

迁移用 SQLite backup API 保存一致的 schema 1 快照（权限600），在显式事务内只重建用户表并添加导师约束；保留旧 ID、哈希、会话、预约、占用槽及审计原文。提交前执行完整性、外键及身份触发器定义/挂载检查，迁移事务失败时回滚数据与schema，已成功建立的独立备份保留。错误版本、未知用户表结构/自定义用户索引或触发器、坏外键、冲突备份路径会明确失败；不猜测旧学生归属，全部保持 `NULL`。路径隔离检查在打开SQLite前完成；源库的 `-journal` / `-wal` / `-shm` 路径及解析后的别名均不可作为备份。确认版本1后，会先在事务外将DELETE模式切换到WAL，再检查完整schema并建立备份；因此后续拒绝或事务失败时，数据、schema和版本保留，但WAL设置可能持续存在，也可能尚未产生备份。不要把失败解释为逐字节不变。需要回退时使用下面独立的schema 1流程，不要执行后面的schema 2恢复命令。

管理员通过本机私有配置和初始化命令创建账号；HTTP 没有学生自注册、选择或更换导师的入口。本故事未提供旧学生首次绑定命令，验收使用显式绑定的新账号。导师可以登录但没有管理员权限。**故事4.1仅完成身份基础：旧直接预约业务仍存在，导师审批和学生直订拦截由4.2实现；此阶段不能作为审批业务已启用的证据。** 本次实际输出与首次失败记录见[身份验证记录](docs/evidence/human-review/identity-verification.md)。

## schema 1 独立回退验证

停服并确认无其他写入进程后，在当前项目目录执行。将 `rollback_backup` 替换为已检查的schema 1备份绝对路径。下例归档兼容的变更前代码 `d585c190febd59ea3fd09ec2dd959052937e53c0` 到新的私有临时目录，创建全新恢复库；不会替换、删除或清会话于实际用户库。只有新恢复库清空会话。使用已安装依赖的项目Python，应用模块从旧代码目录读取；独立服务监听8001，按Ctrl+C停止。

```bash
rollback_backup=/absolute/private/before-schema2.sqlite3
rollback_python="$PWD/.venv/bin/python"
rollback_root="$(mktemp -d "${TMPDIR:-/tmp}/grb-schema1-rollback.XXXXXX")"
git archive d585c190febd59ea3fd09ec2dd959052937e53c0 | tar -x -C "$rollback_root"
"$rollback_python" -m scripts.backup_db --source "$rollback_backup" "$rollback_root/restored-schema1.sqlite3"
(
  cd "$rollback_root" || exit 1
  export BOOKING_DB_PATH="$rollback_root/restored-schema1.sqlite3"
  export APP_ORIGIN=http://127.0.0.1:8001 COOKIE_SECURE=false TRUSTED_HOSTS=127.0.0.1
  "$rollback_python" - <<'RESTORED_SCHEMA1'
from pathlib import Path
from booking_app import default_database, check_runtime, db
assert Path(db.__file__).resolve().is_relative_to(Path.cwd())
assert db.SCHEMA_VERSION == 1
check_runtime()
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
print({"restored_copy": path, "schema_version": 1})
RESTORED_SCHEMA1
  if [ "$?" -ne 0 ]; then exit 1; fi
  "$rollback_python" -m waitress --listen=127.0.0.1:8001 --threads=8 --call booking_app:create_app
)
```

这是独立副本回退操作说明，未对真实默认库演练。后续恢复到实际服务路径需另外停服、保存现状并核对路径；不要覆盖唯一备份。

## 数据备份与恢复

启动使用本地文件库、单进程 Waitress 8 线程及 loopback。当前 schema 为 `PRAGMA user_version=2`，缺表或版本不匹配时停止，不自动迁移。以下只读检查同时报告最终解析的数据库绝对路径、schema 与运行时：

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

CLI 的完整性/外键检查只证明 SQLite 结构有效；`schema_version=0` 或仅结构有效的副本不构成本应用兼容的恢复备份。应用恢复必须通过 `schema=2` 和 `db.check_database` 检查。目标同名 `-wal`、`-shm`、`-journal`（含悬空符号链接）已存在时，CLI 会拒绝复制。

被终止或中断、未成功完成 CLI 的副本不是已完成备份；请使用新的目标重试，不以文件存在判断成功。外部独占锁可能使复制持续等待，直到锁释放或操作被中断；CLI 不提供完成时限保证。

以下仅用于 **schema 2备份恢复到schema 2应用**，仅在停止 Waitress 并确认没有其他读写进程后进行：

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
    assert conn.execute("PRAGMA user_version").fetchone()[0] == 2
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
