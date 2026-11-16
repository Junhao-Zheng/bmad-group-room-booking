# 课题组活动与会议室预约

软件工程管理课程的本机原型，重点展示 BMAD 需求、架构、故事拆分、敏捷增量、真实人机决策和验证过程。实验 A 的原始对照记录保留；按用户转述的教师安排，实验 B 免做、课堂临时变更不再下发。正式视频和演示依用户要求暂缓。

**当前技术状态（2026-11-15）：** Epic 4 五个新增故事已实现。完整回归为 260 项 Python、414 项 JavaScript，均通过；真实 Chrome 在 1280px 和 390px 视口走通学生申请、导师审批、8 周整批预约、逐场取消、管理员批量停用与撤销。数据库 schema 为 v6。课程教师门禁、真实组员贡献和正式录屏尚无可核验证据，见[逐项课程核对](docs/course-audit.md)。

## 本地运行

需要 Python 3.12.14、SQLite >=3.51.3、可用的 `Asia/Shanghai` 时区和 `uv`。以下命令在本项目目录执行；首次初始化会逐一隐藏输入五个演示账号的口令（至少12字符），不会内置或提交共享口令。

```bash
uv python install 3.12.14
uv sync --frozen --python 3.12.14
export BOOKING_DB_PATH="$PWD/instance/course-demo-v6.sqlite3"
uv run --frozen python -m scripts.init_demo
uv run --frozen python -m scripts.seed_demo_rooms
uv run --frozen waitress-serve --listen=127.0.0.1:8000 --threads=8 --call booking_app:create_app
```

打开 [本机登录页](http://127.0.0.1:8000/login)。合成账号为 `demo_teacher_a`、`demo_teacher_b`（导师），`demo_member_a`、`demo_member_b`（分别绑定对应导师的学生）和 `demo_admin`（管理员）。初始化和房间种子可重复运行，不覆盖已有账号口令或业务记录。`BOOKING_DB_PATH` 在初始化、种子和启动时须一致；不设置时默认 `instance/booking.sqlite3`。本工作区原默认库仍为旧 schema 1，不应直接用当前程序启动或在未备份时覆盖。

可改用权限为 600 的私有 JSON 文件运行 `uv run --frozen python -m scripts.init_demo --credentials-file /absolute/private/users.json`。每名学生须指定 `supervisor_username`；没有学生自行注册或修改导师的 HTTP 入口。私有配置和数据库都不得提交到仓库。

## 当前规则

- 学生提交申请后不占用房间，由本人导师批准后才生效。导师本人可直接预约；管理员不能代导师审批学生申请。
- 普通预约及周期首场须在未来 7 天内结束；每场按半小时选择、同日 30 分钟至 4 小时。一次可选每周同一时段最多 8 周，任何一周冲突则整组暂不批准、零占用，并显示冲突日期。
- 学生对已批准预约提出取消申请后仍占用时段；本人导师须在开始前确认才释放。周期预约获批后逐场取消。管理员说明原因可直接取消未结束预约。
- 管理员可预览维修影响的预约，一次填写原因并确认后，在同一事务批量取消实际重叠的预约并停用。预览后占用变化须重新预览；撤销停用不自动恢复旧预约。停用窗口保持未来 30 天。
- 共享日程显示活动、预约人及所属导师；学生看本人完整记录，导师看本人和自己学生的完整记录，管理员看全部。其他登录者仅看共享日程；历史记录在课程期间不自动清理。系统只协调已登记安排，无法阻止线下未登记的跨导师冲突。

## 验证

```bash
.venv/bin/python -m unittest discover -s tests -q
node --test tests/test_*js.cjs
.venv/bin/python -m scripts.verify_supervised_booking_browser \
  --browser-executable '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome' \
  --output-dir work/rerun/epic-4-browser
```

测试使用临时库和合成账号，不修改默认演示库。新流程证据见[导师身份](docs/evidence/human-review/identity-verification.md)、[申请审批](docs/evidence/human-review/booking-verification.md)、[取消确认](docs/evidence/human-review/cancellation-verification.md)、[周期预约](docs/evidence/human-review/weekly-verification.md)、[批量停用](docs/evidence/human-review/maintenance-verification.md)及[当前版NFR03性能](docs/evidence/human-review/epic4-performance/README.md)。完整历史见[验证索引](docs/verification.md)；旧证据只对应其当时源码。

当前schema v6的真实服务重启检查可运行`.venv/bin/python -m scripts.verify_epic4_restart --output-dir work/rerun/epic-4-restart`；它使用全新临时数据库、独立Waitress进程和真实系统时钟，核对8周审批、取消确认、批量停用重放与撤销后的历史。

## 旧库升级

应用不会自动迁移。当前迁移脚本支持已知 schema 1–5 到 v6；先停服并确认无其他写入进程，在**独立副本**上验证，迁移会用 SQLite backup API 创建新的、权限 600 的迁移前备份。路径须是两个尚未复用的独立文件，不能用源文件或其 sidecar 作备份目标。

```bash
.venv/bin/python -m scripts.backup_db --source /absolute/old.sqlite3 /absolute/private/test-copy.sqlite3
.venv/bin/python -m scripts.migrate_db --source /absolute/private/test-copy.sqlite3 --backup /absolute/private/before-v6.sqlite3
```

旧学生若没有导师归属，迁移不会猜测或补写；管理员须通过受控账号配置另行建立合规关系。迁移保留旧预约、占用、审计及已存在的申请/取消历史；失败事务回滚，不应把“备份文件存在”当作成功迁移。旧 schema 1 独立回退实例及原版说明可从 Git 历史提交 `d585c19` 查看。

## 课程材料

|内容|入口|
|---|---|
|需求与范围|[产品简述](_bmad-output/planning-artifacts/product-brief.md)、[PRD](_bmad-output/planning-artifacts/PRD.md)|
|架构与8项ADR|[架构](_bmad-output/planning-artifacts/architecture.md)|
|故事与状态|[史诗](_bmad-output/planning-artifacts/epics.md)、[Sprint状态](_bmad-output/implementation-artifacts/sprint-status.yaml)|
|两次增量与复盘|[Sprint 1](docs/sprints/sprint-1-review.md)、[Sprint 2](docs/sprints/sprint-2-review.md)、[五指标复盘](retrospective.md)|
|需求到证据|[追踪矩阵](docs/traceability.md)、[验证索引](docs/verification.md)|
|真实人机判断|[决策日志](decision-log.md)、[用户原话索引](docs/evidence/user-inputs.md)|
|实验A与AI使用|[实验结果](docs/experiment-a-results.md)、[AI及贡献声明](docs/ai-use-and-contributions.md)、[三人分工](docs/team-contribution-plan.md)|
|暂缓的正式录屏|[演示准备](docs/demonstration-plan.md)|

本项目是本地课程原型：单 SQLite 写入者、无主动消息通知、无公网部署、无分页。当前版NFR03在7天窗口、规定合成负载下测得200样本P95为16.893ms、0错误；不据此声称生产性能。
